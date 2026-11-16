"""Fetch a URL over HTTPS and report status + certificate validity (for launch checks)."""

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
    """The checker's own look at a shop over HTTPS. Every request goes through `SafeWeb` (S11b): only the host
    being checked is allowed, redirects to any other host or to plain http are refused, the address must be
    public, and the page is capped in size and time. A fresh fetcher per call, so nothing is shared between runs."""

    def __init__(self, timeout: float = 10.0, transport: httpx.BaseTransport | None = None, resolve=None,
                 allow_private: bool = False):
        self.timeout, self._transport, self._resolve, self._allow_private = timeout, transport, resolve, allow_private

    def _web(self, host: str):
        from app.checks.safe_fetch import SafeWeb

        kw = {"resolve": self._resolve} if self._resolve else {}
        return SafeWeb(lambda h: h == host, timeout=self.timeout, transport=self._transport,
                       allow_private=self._allow_private, **kw)

    def fetch(self, url: str) -> ProbeResult:
        from app.checks.safe_fetch import Refused

        try:
            page = self._web((urlsplit(url).hostname or "").lower()).get(url)
        except Refused as e:
            return ProbeResult(False, None, True, error=f"refused: {e}"[:150])
        if page.status is None:
            return ProbeResult(False, None, page.cert_valid, error=page.error)
        return ProbeResult(page.status < 400, page.status, True, page.html[:2000])

    def cert_expires(self, host: str) -> datetime | None:
        from app.checks.safe_fetch import Refused

        try:
            return self._web(host.lower()).tls_look(host).not_after
        except Refused:
            return None


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
