"""Public DNS lookups (dnspython) for launch checks."""

from typing import Protocol

import dns.exception
import dns.resolver


class DnsResolver(Protocol):
    def resolve(self, name: str, rtype: str) -> list[str]: ...


class RealDnsResolver:
    def __init__(self, nameservers: list[str] | None = None, timeout: float = 5.0):
        self._r = dns.resolver.Resolver()
        if nameservers:
            self._r.nameservers = nameservers
        self._r.lifetime = timeout

    def resolve(self, name: str, rtype: str) -> list[str]:
        try:
            answer = self._r.resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout):
            return []
        return [r.to_text() for r in answer]


class FakeDnsResolver:
    def __init__(self, records: dict[tuple[str, str], list[str]] | None = None):
        self.records = dict(records or {})

    def set(self, name: str, rtype: str, values: list[str]) -> None:
        self.records[(name.lower().rstrip("."), rtype.upper())] = values

    def resolve(self, name: str, rtype: str) -> list[str]:
        return list(self.records.get((name.lower().rstrip("."), rtype.upper()), []))
