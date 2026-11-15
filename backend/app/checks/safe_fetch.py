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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.sites.hosts import HOSTNAME

MAX_REDIRECTS = 3
MAX_BODY = 300_000


class Refused(Exception):
    """The address isn't one we're allowed to fetch. The message is plain English."""


@dataclass
class Page:
    status: int | None
    html: str
    url: str
    error: str = ""
    server: str = ""  # the address we connected to
    cert_valid: bool = True


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
            raise Refused("That address points to a private network, so we won't open it.")
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
        for _hop in range(MAX_REDIRECTS + 1):
            u = urlsplit(url)
            if u.scheme != "https" or u.port not in (None, 443) or u.username or u.password:
                raise Refused("We only open secure (https) web addresses.")
            host = (u.hostname or "").lower()
            ip = check_host(host, self.allow, self.resolve, self.allow_private)
            target = f"https://{'[' + ip + ']' if ':' in ip else ip}{u.path or '/'}{'?' + u.query if u.query else ''}"
            try:
                r = self._http.request(method, target, data=data, headers={"Host": host},
                                       extensions={"sni_hostname": host})
            except httpx.ConnectError as e:
                bad_cert = isinstance(e.__cause__, ssl.SSLError) or "CERTIFICATE" in str(e).upper()
                return Page(None, "", url, error=type(e).__name__, server=ip, cert_valid=not bad_cert)
            except httpx.HTTPError as e:
                return Page(None, "", url, error=type(e).__name__, server=ip)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                if r.status_code in (301, 302, 303):
                    method, data = "GET", None
                continue
            return Page(r.status_code, r.text[:MAX_BODY], url, server=ip)
        raise Refused("That address sends us round in circles (too many redirects).")

    def cert_not_after(self, host: str) -> datetime | None:
        """End date of the certificate `host` serves, read from the pinned public address."""
        ip = check_host(host, self.allow, self.resolve, self.allow_private)
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((ip, 443), timeout=10) as raw, ctx.wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert().get("notAfter")
        except (OSError, ssl.SSLError):
            return None
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC) if not_after else None
