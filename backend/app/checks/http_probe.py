"""Fetch a URL over HTTPS and report status + certificate validity (for launch checks)."""

import ssl
from dataclasses import dataclass
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


class FakeHttpProbe:
    """Practice mode: a site 'is up with a valid certificate' when its host is in the
    fake DNS and not listed in `broken_cert` / `down`."""

    def __init__(self, settings: Settings | None = None):
        self.down: set[str] = set()
        self.broken_cert: set[str] = set()
        self.calls: list[str] = []

    def fetch(self, url: str) -> ProbeResult:
        self.calls.append(url)
        host = urlsplit(url).hostname or ""
        if host in self.down:
            return ProbeResult(False, None, True, error="ConnectTimeout")
        if host in self.broken_cert:
            return ProbeResult(False, None, False, error="certificate verify failed")
        return ProbeResult(True, 200, True, "<html>ok</html>")
