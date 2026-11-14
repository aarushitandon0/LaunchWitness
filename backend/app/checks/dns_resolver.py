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


def record_text(rec: dict) -> str:
    """GoDaddy record dict -> the text a DNS lookup would return."""
    if rec["type"] == "MX":
        return f"{rec.get('priority', 10)} {rec['data']}."
    if rec["type"] == "TXT":
        return f'"{rec["data"]}"'
    if rec["type"] in ("CNAME", "NS"):
        return rec["data"].rstrip(".") + "."
    return rec["data"]


class ZoneBackedResolver:
    """Fake *authoritative* DNS that answers from a FakeGoDaddyClient's zones,
    so practice-mode launches can be 'proven' end to end. `hide` lets tests and
    the demo fault simulate a record that hasn't spread yet / went missing."""

    def __init__(self, godaddy):
        self.godaddy = godaddy
        self.hide: set[tuple[str, str]] = set()

    def resolve(self, name: str, rtype: str) -> list[str]:
        fqdn, rtype = name.lower().rstrip("."), rtype.upper()
        if (fqdn, rtype) in self.hide:
            return []
        for zone, records in self.godaddy.zones.items():
            if fqdn == zone:
                label = "@"
            elif fqdn.endswith("." + zone):
                label = fqdn[: -len(zone) - 1]
            else:
                continue
            return [record_text(r) for r in records if r["type"] == rtype and r["name"] == label]
        return []
