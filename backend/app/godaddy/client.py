"""GoDaddy REST API wrapper (Domains + DNS). OTE sandbox by default.

Purchases are NOT implemented here in M0; when added they must go through
`app.safety.spend_guard.authorize_purchase` first.
"""

from typing import Protocol

import httpx

from app.config import Settings

BASE_URLS = {
    "ote": "https://api.ote-godaddy.com",
    "prod": "https://api.godaddy.com",
}

DnsRecord = dict  # {"type": "A", "name": "@", "data": "1.2.3.4", "ttl": 600}


class GoDaddy(Protocol):
    env: str

    def check_availability(self, domain: str) -> dict: ...
    def get_records(self, domain: str) -> list[DnsRecord]: ...
    def replace_records(self, domain: str, records: list[DnsRecord]) -> None: ...


class GoDaddyClient:
    """Real client. `env` comes from GODADDY_ENV; prod only when set explicitly."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.env = settings.godaddy_env
        if self.env == "prod":
            key, secret = settings.godaddy_api_key, settings.godaddy_api_secret
        else:
            key, secret = settings.godaddy_ote_api_key, settings.godaddy_ote_api_secret
        self.base_url = BASE_URLS[self.env]
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"sso-key {key.get_secret_value()}:{secret.get_secret_value()}",
                "Accept": "application/json",
            },
            timeout=20.0,
            transport=transport,
        )

    def check_availability(self, domain: str) -> dict:
        r = self._http.get("/v1/domains/available", params={"domain": domain})
        r.raise_for_status()
        return r.json()

    def get_records(self, domain: str) -> list[DnsRecord]:
        r = self._http.get(f"/v1/domains/{domain}/records")
        r.raise_for_status()
        return r.json()

    def replace_records(self, domain: str, records: list[DnsRecord]) -> None:
        r = self._http.put(f"/v1/domains/{domain}/records", json=records)
        r.raise_for_status()


class FakeGoDaddyClient:
    """In-memory stand-in for tests and local dev."""

    def __init__(self, available: dict[str, float] | None = None, env: str = "ote"):
        self.env = env
        self.available = available or {}  # domain -> price in USD
        self.zones: dict[str, list[DnsRecord]] = {}
        self.calls: list[tuple] = []

    def check_availability(self, domain: str) -> dict:
        self.calls.append(("check_availability", domain))
        if domain in self.available:
            return {"domain": domain, "available": True, "price_usd": self.available[domain]}
        return {"domain": domain, "available": False}

    def get_records(self, domain: str) -> list[DnsRecord]:
        self.calls.append(("get_records", domain))
        return [dict(r) for r in self.zones.get(domain, [])]

    def replace_records(self, domain: str, records: list[DnsRecord]) -> None:
        self.calls.append(("replace_records", domain))
        self.zones[domain] = [dict(r) for r in records]
