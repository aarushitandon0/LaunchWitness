"""Public DNS lookups (dnspython) for launch checks."""

import re
from dataclasses import dataclass
from typing import Protocol

import dns.exception
import dns.resolver


class DnsResolver(Protocol):
    def resolve(self, name: str, rtype: str) -> list[str]: ...


@dataclass(frozen=True)
class Answer:
    """One lookup, with HOW it ended. "error" means OUR lookup failed (timeout, no nameserver answered):
    it says nothing about the name, so a check must answer "couldn't check", never "missing"."""
    status: str  # "ok" | "nodata" (the name exists, no such record) | "nxdomain" (no such name) | "error"
    values: tuple[str, ...] = ()


def lookup(dns_: DnsResolver, name: str, rtype: str) -> Answer:
    """`Answer` from any resolver: its own `lookup` if it has one, else `resolve` (empty = no such record)."""
    own = getattr(dns_, "lookup", None)
    try:
        if own is not None:
            return own(name, rtype)
        values = dns_.resolve(name, rtype)
    except Exception:  # a resolver that breaks is a failure on our side
        return Answer("error")
    return Answer("ok", tuple(values)) if values else Answer("nodata")


def txt_value(text: str) -> str:
    """A TXT answer as one string: DNS splits long values into quoted pieces (`"abc" "def"` -> `abcdef`)."""
    parts = re.findall(r'"([^"]*)"', text)
    return "".join(parts) if parts else text.strip()


class RealDnsResolver:
    def __init__(self, nameservers: list[str] | None = None, timeout: float = 5.0):
        self._r = dns.resolver.Resolver()
        if nameservers:
            self._r.nameservers = nameservers
        self._r.lifetime = timeout

    def resolve(self, name: str, rtype: str) -> list[str]:
        try:
            answer = self._r.resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
            return []
        return [r.to_text() for r in answer]

    def lookup(self, name: str, rtype: str) -> Answer:
        try:
            answer = self._r.resolve(name, rtype)
        except dns.resolver.NXDOMAIN:
            return Answer("nxdomain")
        except dns.resolver.NoAnswer:
            return Answer("nodata")
        except dns.exception.DNSException:  # timeout, SERVFAIL, no nameserver reachable: our lookup failed
            return Answer("error")
        return Answer("ok", tuple(r.to_text() for r in answer))

    def exists(self, name: str) -> bool | None:
        """False only for NXDOMAIN (the name doesn't exist at all); None when DNS didn't answer."""
        try:
            self._r.resolve(name, "A")
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except dns.resolver.NoAnswer:
            return True  # the name exists, it just has no A record
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            return None


class FakeDnsResolver:
    def __init__(self, records: dict[tuple[str, str], list[str]] | None = None):
        self.records = dict(records or {})
        self.errors: set[str] = set()  # names whose lookups fail on OUR side (tests)
        self.queries: list[tuple[str, str]] = []

    def lookup(self, name: str, rtype: str) -> Answer:
        n, t = name.lower().rstrip("."), rtype.upper()
        self.queries.append((n, t))
        if n in self.errors or "*" in self.errors:
            return Answer("error")
        values = self.records.get((n, t), [])
        if values:
            return Answer("ok", tuple(values))
        return Answer("nodata" if any(k == n for k, _t in self.records) else "nxdomain")

    def set(self, name: str, rtype: str, values: list[str]) -> None:
        self.records[(name.lower().rstrip("."), rtype.upper())] = values

    def resolve(self, name: str, rtype: str) -> list[str]:
        return list(self.records.get((name.lower().rstrip("."), rtype.upper()), []))

    def exists(self, name: str) -> bool | None:
        n = name.lower().rstrip(".")
        return any(key == n and values for (key, _t), values in self.records.items())


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


class AuthoritativeResolver:
    """Asks the zone's OWN nameservers (found from its NS records), not a cache, and remembers which
    server answered (`last_server`), so a check can say exactly where its answer came from."""

    def __init__(self, timeout: float = 5.0, finder=None, query=None):
        self.timeout = timeout
        self._finder = finder or RealDnsResolver(timeout=timeout)  # only to FIND the nameservers
        self._query = query or self._udp
        self.last_server = ""

    def _udp(self, name: str, rtype: str, ip: str) -> list[str]:
        import dns.message
        import dns.query
        import dns.rdatatype

        resp = dns.query.udp(dns.message.make_query(name, rtype), ip, timeout=self.timeout)
        want = dns.rdatatype.from_text(rtype)
        return [r.to_text() for rrset in resp.answer if rrset.rdtype == want for r in rrset]

    def nameservers(self, name: str) -> tuple[str, list[str]]:
        labels = name.lower().rstrip(".").split(".")
        for i in range(len(labels) - 1):
            zone = ".".join(labels[i:])
            ns = self._finder.resolve(zone, "NS")
            if ns:
                return zone, sorted(n.rstrip(".") for n in ns)
        return "", []

    def lookup(self, name: str, rtype: str) -> Answer:
        """ "error" when no nameserver could be found or none answered: that is our failure to look, not an answer."""
        _zone, ns = self.nameservers(name)
        for host in ns:
            for ip in self._finder.resolve(host, "A"):
                try:
                    answer = self._query(name, rtype, ip)
                except Exception:  # try the next nameserver
                    continue
                self.last_server = f"{host} ({ip})"
                return Answer("ok", tuple(answer)) if answer else Answer("nodata")
        self.last_server = ""
        return Answer("error")

    def resolve(self, name: str, rtype: str) -> list[str]:
        return list(self.lookup(name, rtype).values)
