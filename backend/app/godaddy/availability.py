"""Domain availability + price, behind one interface.

The real method is NOT chosen yet (gddy CLI / Domains API / OTE / RDAP — see
PROGRESS.md). `GoDaddyAvailabilityChecker` is a stub to fill in.
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Quote:
    domain: str
    available: bool
    price_usd: float | None = None  # first-year price, only when available


class AvailabilityChecker(Protocol):
    def check(self, domains: list[str]) -> list[Quote]: ...


class FakeAvailabilityChecker:
    """Deterministic: explicit `prices` win; otherwise ~half of names are 'available'
    with a stable price per TLD. `taken` are always unavailable."""

    TLD_PRICES = {"in": 8.99, "co.in": 6.99, "com": 11.99, "shop": 2.99, "store": 3.99, "online": 1.99}

    def __init__(self, prices: dict[str, float] | None = None, taken: set[str] | None = None):
        self.prices = dict(prices or {})
        self.taken = set(taken or ())
        self.calls: list[list[str]] = []

    def check(self, domains: list[str]) -> list[Quote]:
        self.calls.append(list(domains))
        out = []
        for d in domains:
            if d in self.taken:
                out.append(Quote(d, False))
            elif d in self.prices:
                out.append(Quote(d, True, self.prices[d]))
            else:
                tld = d.split(".", 1)[1] if "." in d else ""
                free = int(hashlib.sha256(d.encode()).hexdigest(), 16) % 2 == 0
                out.append(Quote(d, free and tld in self.TLD_PRICES, self.TLD_PRICES.get(tld) if free else None))
        return out


class GoDaddyAvailabilityChecker:
    """TODO(real): implement with the method recorded in PROGRESS.md
    (GoDaddy Domains API `GET /v1/domains/available?domain=` in prod needs 50+ domains or
    spend; alternatives: `gddy` CLI, OTE, or RDAP for availability + a fixed price table)."""

    def check(self, domains: list[str]) -> list[Quote]:
        raise NotImplementedError("Real availability check not chosen yet (see PROGRESS.md: Real integration TODO)")
