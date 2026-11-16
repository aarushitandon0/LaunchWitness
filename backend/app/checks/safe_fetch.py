"""Fetch web pages for checks without letting anyone aim us at internal addresses (SSRF guard).

Rules, for every hop (redirects included):
- https only, port 443 only, a hostname (never an IP literal);
- the host must pass the caller's `allow` test (the checker allows only the shop's own host);
- every address the name resolves to must be public (no loopback, private, link-local, ...);
- the connection goes to the address we checked (pinned), with the hostname for TLS (SNI) and
  the Host header, so a DNS answer can't change between the check and the request;
- at most 3 redirects.
"""

import ipaddress
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.sites.hosts import HOSTNAME

MAX_REDIRECTS = 3
MAX_BODY = 300_000


MAX_SECONDS = 20  # for one whole page, however slowly it arrives
now = time.monotonic


class TooSlow(Exception):
    """The page kept us waiting longer than MAX_SECONDS."""


def read_capped(r: httpx.Response) -> bytes:
    """At most MAX_BODY bytes and MAX_SECONDS of the body, read as it arrives: a page that never
    ends (or drips a byte at a time) can't fill our memory or hold a check open."""
    deadline, got, size = now() + MAX_SECONDS, [], 0
    for chunk in r.iter_bytes():
        got.append(chunk)
        size += len(chunk)
        if size >= MAX_BODY:
            break
        if now() > deadline:
            raise TooSlow
    return b"".join(got)[:MAX_BODY]


class Refused(Exception):
    """The address isn't one we're allowed to fetch. The message is plain English."""


class PrivateAddress(Refused):
    """The name points inside a private network."""


class NotHttps(Refused):
    """The address (or a redirect) is plain http, another port, or carries a password."""


def tls_context() -> ssl.SSLContext:
    """The same trusted authorities the page fetch (httpx) uses, so the two looks can't disagree about a
    certificate. The system's own list can lack an authority that the fetch trusts (seen on Windows)."""
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


class TooManyRedirects(Refused):
    """More than MAX_REDIRECTS hops (usually a loop)."""


@dataclass
class TlsSeen:
    """What the secure handshake showed. kind: ok | expired | not_yet_valid | wrong_host | self_signed |
    untrusted | bad_cert | no_tls | timeout | refused"""
    kind: str
    not_after: datetime | None = None
    detail: str = ""


TLS_VERIFY_KINDS = {9: "not_yet_valid", 10: "expired", 18: "self_signed", 19: "untrusted", 20: "untrusted",
                    21: "untrusted", 62: "wrong_host"}  # OpenSSL X509_V_ERR_* codes


def tls_kind(e: Exception) -> str:
    """Why a secure handshake failed, in one word."""
    if isinstance(e, ssl.SSLCertVerificationError):
        return TLS_VERIFY_KINDS.get(e.verify_code, "bad_cert")
    if isinstance(e, TimeoutError):
        return "timeout"
    if isinstance(e, ssl.SSLError):
        return "no_tls"  # something answered on the secure port, but not with a working secure connection
    return "refused"


@dataclass
class Page:
    status: int | None
    html: str
    url: str
    error: str = ""
    server: str = ""  # the address we connected to
    cert_valid: bool = True
    kind: str = ""  # why there is no status: timeout | refused | cert | error
    seconds: float = 0.0  # how long the whole answer took (all hops)
    hsts: bool = False  # the answer carried Strict-Transport-Security
    hops: int = 0  # redirects followed


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return True


def system_resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return sorted({info[4][0] for info in infos})


def check_host(host: str, allow: Callable[[str], bool], resolve: Callable[[str], list[str]],
               allow_private: bool = False) -> str:
    """The pinned address for `host`, or Refused."""
    host = (host or "").lower().rstrip(".")
    if not host or is_ip_literal(host) or not HOSTNAME.match(host) or "." not in host:
        raise Refused("That isn't a web address we can check.")
    if not allow(host):
        raise Refused("That address isn't one we check.")
    ips = resolve(host)
    if not ips:
        raise Refused("That address doesn't lead anywhere yet.")
    for ip in ips:
        if not allow_private and not ipaddress.ip_address(ip).is_global:
            raise PrivateAddress("That address points to a private network, so we won't open it.")
    return ips[0]


class SafeWeb:
    def __init__(self, allow: Callable[[str], bool], *, resolve: Callable[[str], list[str]] = system_resolve,
                 timeout: float = 10.0, transport: httpx.BaseTransport | None = None, allow_private: bool = False):
        self.allow, self.resolve, self.allow_private = allow, resolve, allow_private
        self._http = httpx.Client(timeout=timeout, transport=transport, follow_redirects=False)
        self.source = "https"

    def get(self, url: str) -> Page:
        return self._request("GET", url)

    def post(self, url: str, fields: dict[str, str]) -> Page:
        return self._request("POST", url, fields)

    def _request(self, method: str, url: str, data: dict | None = None) -> Page:
        started = now()
        for hop in range(MAX_REDIRECTS + 1):
            u = urlsplit(url)
            if u.scheme != "https" or u.port not in (None, 443) or u.username or u.password:
                raise NotHttps("We only open secure (https) web addresses.")
            host = (u.hostname or "").lower()
            ip = check_host(host, self.allow, self.resolve, self.allow_private)
            target = f"https://{'[' + ip + ']' if ':' in ip else ip}{u.path or '/'}{'?' + u.query if u.query else ''}"
            try:
                with self._http.stream(method, target, data=data, headers={"Host": host, "Accept-Encoding": "identity"},
                                       extensions={"sni_hostname": host}) as r:
                    status, location = r.status_code, r.headers.get("location")
                    redirect = status in (301, 302, 303, 307, 308) and bool(location)
                    body = b"" if redirect else read_capped(r)
                    encoding = r.encoding or "utf-8"
                    hsts = "strict-transport-security" in r.headers
            except TooSlow:
                return Page(None, "", url, error="TooSlow", server=ip, kind="timeout", seconds=now() - started)
            except httpx.TimeoutException as e:
                return Page(None, "", url, error=type(e).__name__, server=ip, kind="timeout", seconds=now() - started)
            except httpx.ConnectError as e:
                bad_cert = isinstance(e.__cause__, ssl.SSLError) or "CERTIFICATE" in str(e).upper()
                return Page(None, "", url, error=type(e).__name__, server=ip, cert_valid=not bad_cert,
                            kind="cert" if bad_cert else "refused", seconds=now() - started)
            except httpx.HTTPError as e:
                return Page(None, "", url, error=type(e).__name__, server=ip, kind="error", seconds=now() - started)
            if redirect:
                url = urljoin(url, location)
                if status in (301, 302, 303):
                    method, data = "GET", None
                continue
            try:
                html = body.decode(encoding, errors="replace")
            except LookupError:  # a charset name we don't know
                html = body.decode("utf-8", errors="replace")
            return Page(status, html[:MAX_BODY], url, server=ip, seconds=now() - started, hsts=hsts, hops=hop)
        raise TooManyRedirects("That address sends us round in circles (too many redirects).")

    def tls_look(self, host: str) -> TlsSeen:
        """Open a secure connection to the pinned public address and say what the certificate check showed."""
        ip = check_host(host, self.allow, self.resolve, self.allow_private)
        try:
            ctx = tls_context()
            with socket.create_connection((ip, 443), timeout=8) as raw, ctx.wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert().get("notAfter")
        except (OSError, ssl.SSLError) as e:
            return TlsSeen(tls_kind(e), detail=f"{type(e).__name__}: {getattr(e, 'verify_message', '') or e}"[:200])
        end = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC) if not_after else None
        return TlsSeen("ok", end)

    def http_first(self, host: str) -> tuple[str, str]:
        """What plain http (no padlock) does with a visitor: ONE request to the pinned public address, no body
        read, nothing followed. ("redirects_https" | "redirects_http" | "serves" | "error" | "closed" | "timeout", detail)"""
        ip = check_host(host, self.allow, self.resolve, self.allow_private)
        try:
            with self._http.stream("GET", f"http://{'[' + ip + ']' if ':' in ip else ip}/",
                                   headers={"Host": host, "Accept-Encoding": "identity"}) as r:
                status, location = r.status_code, r.headers.get("location", "")
        except httpx.TimeoutException:
            return "timeout", ""
        except httpx.HTTPError as e:
            return "closed", type(e).__name__
        if status in (301, 302, 303, 307, 308) and location:
            to = urlsplit(urljoin(f"http://{host}/", location))
            return ("redirects_https" if to.scheme == "https" else "redirects_http"), (to.hostname or "")
        return ("serves" if status < 400 else "error"), str(status)

    def cert_not_after(self, host: str) -> datetime | None:
        """End date of the certificate `host` serves, read from the pinned public address."""
        ip = check_host(host, self.allow, self.resolve, self.allow_private)
        try:
            ctx = tls_context()
            with socket.create_connection((ip, 443), timeout=10) as raw, ctx.wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert().get("notAfter")
        except (OSError, ssl.SSLError):
            return None
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC) if not_after else None
