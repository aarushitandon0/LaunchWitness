"""Fetch a URL over HTTPS and report status + certificate validity (for launch checks)."""

import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.config import Settings


@dataclass(frozen=True)
class ProbeResult:
    ok: bool  # HTTP 2xx/3xx over HTTPS with a valid certificate
    status: int | None
    cert_valid: bool
    body_snippet: str = ""
    error: str = ""


class HttpProbe(Protocol):
    def fetch(self, url: str) -> ProbeResult: ...
    def cert_expires(self, host: str) -> datetime | None:
        """End date of the HTTPS certificate served for `host` (None if it can't be read)."""
        ...


class RealHttpProbe:
    def __init__(self, timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport)

    def fetch(self, url: str) -> ProbeResult:
        try:
            r = self._http.get(url)
        except httpx.ConnectError as e:
            cert_bad = isinstance(e.__cause__, ssl.SSLError) or "CERTIFICATE" in str(e).upper()
            return ProbeResult(False, None, not cert_bad, error=type(e).__name__)
        except httpx.HTTPError as e:
            return ProbeResult(False, None, False, error=type(e).__name__)
        https = urlsplit(str(r.url)).scheme == "https"
        return ProbeResult(https and r.status_code < 400, r.status_code, https, r.text[:2000])

    def cert_expires(self, host: str) -> datetime | None:
        """TODO(real): verify against a real Caddy-served host."""
        try:
            from app.checks.safe_fetch import tls_context

            ctx = tls_context()
            with socket.create_connection((host, 443), timeout=10) as raw, ctx.wrap_socket(raw, server_hostname=host) as tls:
                not_after = tls.getpeercert().get("notAfter")
        except (OSError, ssl.SSLError):
            return None
        return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC) if not_after else None


class FakeHttpProbe:
    """Practice mode: a site 'is up with a valid certificate' when its host is in the
    fake DNS and not listed in `broken_cert` / `down`."""

    def __init__(self, settings: Settings | None = None):
        self.down: set[str] = set()
        self.broken_cert: set[str] = set()
        self.calls: list[str] = []
        self.cert_end: dict[str, datetime] = {}  # host -> certificate end (default: 80 days from now)

    def cert_expires(self, host: str) -> datetime | None:
        if host in self.down or host in self.broken_cert:
            return None
        return self.cert_end.get(host) or datetime.now(UTC) + timedelta(days=80)

    def fetch(self, url: str) -> ProbeResult:
        self.calls.append(url)
        host = urlsplit(url).hostname or ""
        if host in self.down:
            return ProbeResult(False, None, True, error="ConnectTimeout")
        if host in self.broken_cert:
            return ProbeResult(False, None, False, error="certificate verify failed")
        return ProbeResult(True, 200, True, "<html>ok</html>")
