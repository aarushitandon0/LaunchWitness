"""GoDaddy REST API wrapper (Domains + DNS). OTE sandbox by default.

DNS writes are always scoped to ONE (type, name) pair (`set_records` /
`delete_records`), never a whole-zone replace, so a launch can't wipe records
it didn't plan. Purchases are not implemented in the real client: they are done
by the owner on godaddy.com, and any future code path must go through
`app.safety.spend_guard.authorize_purchase` first.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from app.config import Settings
from app.godaddy.ratelimit import LIMITER

BASE_URLS = {
    "ote": "https://api.ote-godaddy.com",
    "prod": "https://api.godaddy.com",
}

DnsRecord = dict  # {"type": "A", "name": "@", "data": "1.2.3.4", "ttl": 600, "priority"?: 10}


class PurchaseNotSupported(RuntimeError):
    pass


class AppZoneWriteRefused(RuntimeError):
    """A write to the app's own domain that is not an A record for one shop name."""


def assert_zone_write(app_domain: str, domain: str, rtype: str, name: str) -> None:
    """Hard guard, inside the client itself: on the app's own domain (which also carries the app's
    website and email), code may only write an A record for one shop name. Never @, *, www, a
    reserved name, MX, TXT, CNAME or any mail record, whatever the caller asks for."""
    from app.sites.hosts import slug_problem

    if domain.lower().rstrip(".") != app_domain.lower().rstrip("."):
        return
    if rtype.upper() != "A" or slug_problem(name) is not None:
        raise AppZoneWriteRefused(f"refused {rtype} {name} on {domain}: only A records for shop names may be written")


class GoDaddy(Protocol):
    env: str

    def check_availability(self, domain: str) -> dict: ...
    def is_owned(self, domain: str) -> bool: ...
    def get_records(self, domain: str) -> list[DnsRecord]: ...
    def set_records(self, domain: str, rtype: str, name: str, records: list[DnsRecord]) -> None: ...
    def delete_records(self, domain: str, rtype: str, name: str) -> None: ...
    def purchase_domain(self, domain: str, price_usd: float) -> dict: ...
    def domain_expires(self, domain: str) -> datetime | None: ...


class GoDaddyClient:
    """Real client. `env` comes from GODADDY_ENV; prod only when set explicitly."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.env = settings.godaddy_env
        self.app_domain = settings.app_domain
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
            # S13: one shared per-process limit on GoDaddy calls (waits, never fails)
            event_hooks={"request": [lambda _req: LIMITER.acquire()]},
        )

    def check_availability(self, domain: str) -> dict:
        r = self._http.get("/v1/domains/available", params={"domain": domain})
        r.raise_for_status()
        return r.json()

    def is_owned(self, domain: str) -> bool:
        """True only if the domain is in this GoDaddy account AND its status is ACTIVE."""
        r = self._http.get(f"/v1/domains/{domain}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return str(r.json().get("status", "")).upper() == "ACTIVE"

    def get_records(self, domain: str) -> list[DnsRecord]:
        r = self._http.get(f"/v1/domains/{domain}/records")
        r.raise_for_status()
        return r.json()

    def set_records(self, domain: str, rtype: str, name: str, records: list[DnsRecord]) -> None:
        """Replace all records of one type+name (PUT /v1/domains/{d}/records/{type}/{name})."""
        assert_zone_write(self.app_domain, domain, rtype, name)
        body = [{k: v for k, v in rec.items() if k not in ("type", "name")} for rec in records]
        r = self._http.put(f"/v1/domains/{domain}/records/{rtype}/{name}", json=body)
        r.raise_for_status()

    def delete_records(self, domain: str, rtype: str, name: str) -> None:
        assert_zone_write(self.app_domain, domain, rtype, name)
        r = self._http.delete(f"/v1/domains/{domain}/records/{rtype}/{name}")
        if r.status_code != 404:
            r.raise_for_status()

    def purchase_domain(self, domain: str, price_usd: float) -> dict:
        raise PurchaseNotSupported("Domains are bought by the owner on godaddy.com; the app only adopts them.")

    def domain_expires(self, domain: str) -> datetime | None:
        """Registration end date from GET /v1/domains/{domain} ("expires"). TODO(real): verify field on prod."""
        r = self._http.get(f"/v1/domains/{domain}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        value = r.json().get("expires")
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class FakeGoDaddyClient:
    """In-memory stand-in for tests and practice mode."""

    def __init__(self, available: dict[str, float] | None = None, env: str = "ote", owned: set[str] | None = None,
                 app_domain: str = ""):
        self.env = env
        self.app_domain = app_domain  # same write guard as the real client
        self.available = dict(available or {})  # domain -> price in USD
        self.owned: set[str] = set(owned or ())
        self.zones: dict[str, list[DnsRecord]] = {}
        self.calls: list[tuple] = []
        self.fail_next: dict[str, int] = {}  # method name -> number of upcoming calls that raise
        self.expires: dict[str, datetime] = {}  # domain -> registration end (default: a year from now)
        self.limiter = None  # tests: a RateLimiter, used like the real client's

    def _maybe_fail(self, method: str) -> None:
        if self.limiter is not None:
            self.limiter.acquire()
        if self.fail_next.get(method, 0) > 0:
            self.fail_next[method] -= 1
            raise RuntimeError(f"fake {method} failure")

    def check_availability(self, domain: str) -> dict:
        self.calls.append(("check_availability", domain))
        if domain in self.available and domain not in self.owned:
            return {"domain": domain, "available": True, "price_usd": self.available[domain]}
        return {"domain": domain, "available": False}

    def is_owned(self, domain: str) -> bool:
        self.calls.append(("is_owned", domain))
        return domain in self.owned

    def get_records(self, domain: str) -> list[DnsRecord]:
        self.calls.append(("get_records", domain))
        self._maybe_fail("get_records")
        return [dict(r) for r in self.zones.get(domain, [])]

    def set_records(self, domain: str, rtype: str, name: str, records: list[DnsRecord]) -> None:
        assert_zone_write(self.app_domain, domain, rtype, name)
        self.calls.append(("set_records", domain, rtype, name))
        self._maybe_fail("set_records")
        keep = [r for r in self.zones.get(domain, []) if not (r["type"] == rtype and r["name"] == name)]
        self.zones[domain] = keep + [{**dict(r), "type": rtype, "name": name} for r in records]

    def delete_records(self, domain: str, rtype: str, name: str) -> None:
        assert_zone_write(self.app_domain, domain, rtype, name)
        self.calls.append(("delete_records", domain, rtype, name))
        self.zones[domain] = [r for r in self.zones.get(domain, []) if not (r["type"] == rtype and r["name"] == name)]

    def purchase_domain(self, domain: str, price_usd: float) -> dict:
        self.calls.append(("purchase_domain", domain, price_usd))
        self.owned.add(domain)
        return {"domain": domain, "price_usd": price_usd, "order_id": f"fake-{len(self.owned)}"}

    def domain_expires(self, domain: str) -> datetime | None:
        if domain not in self.owned:
            return None
        return self.expires.get(domain) or datetime.now(UTC) + timedelta(days=365)

    def writes(self) -> list[tuple]:
        return [c for c in self.calls if c[0] in ("set_records", "delete_records")]
