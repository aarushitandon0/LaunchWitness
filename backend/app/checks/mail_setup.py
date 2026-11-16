"""The email setup of ANY domain, read from public DNS only (S11b).

Two rules run through this file:
- **Never guess.** The email service is detected from the domain's own mail-server names (one table, `SERVICES`).
  If we don't recognise it, we say so and give no values at all.
- **"Not sure" beats wrong.** Every finding says how sure we are: `seen` (we read it), `not_seen` (we looked and
  it wasn't there), `couldnt_check` (our lookup failed, or it can't be looked up at all). A lookup that failed
  on our side is never reported as something missing on theirs.

A finding is a dict: check, ok (True good / False a real problem / None a note or "not sure"), plain (no record
names or values), detail (technical), sure, code (stable id, used by tests and the matrix), steps (the
service's own instructions; we only explain, we never change anything on an outside domain).
"""

import ipaddress
import re
from dataclasses import dataclass, field

from app.checks.dns_resolver import DnsResolver, lookup, txt_value

SEEN, NOT_SEEN, COULDNT = "seen", "not_seen", "couldnt_check"
SPF_LOOKUP_LIMIT, SPF_VOID_LIMIT = 10, 2  # RFC 7208 section 4.6.4
SPF_MAX_DEPTH = 10  # nested include/redirect levels we follow
SPF_MAX_QUERIES = 30  # DNS questions one SPF walk may ask, whatever the record says


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    mx: tuple[str, ...]  # a mail-server name that is, or ends with, one of these belongs to this service
    spf: tuple[str, ...]  # include: targets that mean "this service may send"
    spf_line: str  # the line the service itself documents
    mx_doc: str  # the mail servers the service itself documents
    where: str  # where the owner changes it, in the service's own words
    dkim: tuple[str, ...] = ()  # documented / usual signing labels (selectors); () = it can't be looked up
    dkim_how: str = ""
    note: str = ""


# Patterns as each service documents them (checked against live DNS where docs/CHECKS_MATRIX.md says so).
SERVICES: tuple[Service, ...] = (
    Service("google", "Google Workspace (Gmail)", ("google.com", "googlemail.com"), ("_spf.google.com",),
            "v=spf1 include:_spf.google.com ~all", "smtp.google.com (priority 1)",
            "Google Admin console → Apps → Google Workspace → Gmail", ("google",),
            "In the Google Admin console open Apps → Google Workspace → Gmail → Authenticate email, create the "
            "key, add the record it shows you, then press Start authentication."),
    Service("microsoft", "Microsoft 365 (Outlook)", ("protection.outlook.com", "mx.microsoft"),
            ("spf.protection.outlook.com", "secureserver.net"),
            "v=spf1 include:spf.protection.outlook.com -all",
            "the one name shown for your domain in the Microsoft 365 admin center (it ends in mail.protection.outlook.com)",
            "Microsoft 365 admin center → Settings → Domains", ("selector1", "selector2"),
            "In the Microsoft Defender portal open Email & collaboration → Policies → Email authentication → DKIM, "
            "choose your domain, add the two records it shows you, then switch signing on.",
            note="Microsoft 365 bought through GoDaddy uses include:secureserver.net instead; both are accepted."),
    Service("zoho", "Zoho Mail", ("zoho.com", "zohomail.com"), ("zoho.com", "zohomail.com", "one.zoho.com"),
            "v=spf1 include:zohomail.com ~all", "mx.zoho.com (10), mx2.zoho.com (20), mx3.zoho.com (50)",
            "Zoho Mail Admin Console → Domains", ("zmail", "zoho"),
            "In the Zoho Mail Admin Console open Domains → your domain → Email Configuration → DKIM, add a "
            "selector, add the record it shows you, then press Verify."),
    Service("zoho_in", "Zoho Mail (India)", ("zoho.in", "zohomail.in"), ("zoho.in", "zohomail.in"),
            "v=spf1 include:zoho.in ~all", "mx.zoho.in (10), mx2.zoho.in (20), mx3.zoho.in (50)",
            "Zoho Mail Admin Console → Domains", ("zmail", "zoho"),
            "In the Zoho Mail Admin Console open Domains → your domain → Email Configuration → DKIM, add a "
            "selector, add the record it shows you, then press Verify."),
    Service("secureserver", "GoDaddy Professional Email", ("secureserver.net",), ("secureserver.net",),
            "v=spf1 include:secureserver.net -all", "smtp.secureserver.net (0), mailstore1.secureserver.net (10)",
            "GoDaddy → My Products → Email → your domain's DNS",
            dkim_how="GoDaddy sets up signing for Professional Email itself; ask GoDaddy support to confirm it is on."),
    Service("titan", "Titan Email", ("titan.email",), ("spf.titan.email",),
            "v=spf1 include:spf.titan.email ~all", "mx1.titan.email (10), mx2.titan.email (20)",
            "Titan's control panel → Domain verification", ("titan1",),
            "In Titan's control panel open Configure DKIM, add the record it shows you, then press Verify."),
    Service("hostinger", "Hostinger Email", ("hostinger.com", "hostinger.in"), ("_spf.mail.hostinger.com",),
            "v=spf1 include:_spf.mail.hostinger.com ~all", "mx1.hostinger.com (5), mx2.hostinger.com (10)",
            "Hostinger hPanel → Emails → your domain → DNS settings",
            ("hostingermail-a", "hostingermail-b", "hostingermail-c"),
            "In hPanel open Emails → your domain → DNS settings → Custom DKIM and add the three records it shows you."),
    Service("cloudflare", "Cloudflare Email Routing", ("mx.cloudflare.net",), ("_spf.mx.cloudflare.net",),
            "v=spf1 include:_spf.mx.cloudflare.net ~all",
            "route1.mx.cloudflare.net, route2.mx.cloudflare.net, route3.mx.cloudflare.net",
            "Cloudflare dashboard → Email → Email Routing", ("cf2024-1",),
            "Cloudflare adds the signing record itself when Email Routing is switched on (Email → Email Routing → "
            "Settings); press \"Add records automatically\" if it is missing.",
            note="Email Routing only forwards incoming email to another inbox; it doesn't send."),
)
BY_KEY = {s.key: s for s in SERVICES}
OUR_SELECTORS = ("titan1", "mail")  # the signing labels LaunchWitness itself plans (mail/providers.py)
UNKNOWN_STEPS = ("We don't recognise the email service this address uses, so we won't guess its settings. "
                 "Ask that service for its exact values and where to enter them.")


@dataclass(frozen=True)
class Detected:
    key: str  # a Service key, or "null_mx" | "no_mx" | "unknown" | "mixed" | "couldnt_check"
    label: str
    service: Service | None = None
    hosts: tuple[str, ...] = ()


def mx_host(value: str) -> str:
    return value.split()[-1].rstrip(".").lower() if value.split() else ""


def service_for_host(host: str) -> Service | None:
    for s in SERVICES:
        if any(host == suffix or host.endswith("." + suffix) for suffix in s.mx):
            return s
    return None


def detect(mx_values: list[str] | tuple[str, ...]) -> Detected:
    """Which email service receives this domain's mail, from its mail-server names alone."""
    hosts = tuple(mx_host(v) for v in mx_values)
    if not hosts:
        return Detected("no_mx", "no email service")
    if all(h == "" for h in hosts):  # RFC 7505 "null MX": `0 .`
        return Detected("null_mx", "no email (switched off on purpose)")
    real = tuple(h for h in hosts if h)
    services = [service_for_host(h) for h in real]
    found = {s.key: s for s in services if s is not None}
    if len(found) == 1 and all(services):
        s = next(iter(found.values()))
        return Detected(s.key, s.label, s, real)
    if found:  # two known services, or a known one next to a stranger
        names = sorted(s.label for s in found.values()) + ([] if all(services) else ["another service"])
        return Detected("mixed", " and ".join(names[:2]), None, real)
    return Detected("unknown", "an email service we don't recognise", None, real)


def finding(check: str, ok: bool | None, plain: str, detail: str, sure: str, code: str, steps: str = "") -> dict:
    return {"check": check, "ok": ok, "plain": plain, "detail": detail[:600], "sure": sure, "code": code,
            "steps": steps, "action": "explain" if ok is not True and steps else "none"}


OUR_SIDE = "We couldn't read this just now (the problem was on our side, not theirs). Please try again in a few minutes."


def mail_domain(host: str, dns: DnsResolver) -> str:
    """The domain whose email settings apply to `host`: itself if it has mail servers or is a domain of its own,
    else the nearest parent that is (so a shop on shop.example.com is judged by example.com's email)."""
    zone = host.removeprefix("www.")
    own = lookup(dns, zone, "MX")
    if own.values or own.status in ("nxdomain", "error"):
        return zone
    labels = zone.split(".")
    for i in range(len(labels) - 1):
        name = ".".join(labels[i:])
        if lookup(dns, name, "CNAME").values:  # an alias answers for its target: it isn't a domain of its own
            continue
        if lookup(dns, name, "NS").values:
            return name
    return zone


# ---------- mail servers (MX) ----------

def mx_finding(domain: str, dns: DnsResolver) -> tuple[dict, Detected]:
    got = lookup(dns, domain, "MX")
    if got.status == "error":
        return finding("email_mx", None, OUR_SIDE, f"MX {domain}: lookup failed", COULDNT, "mx_couldnt_check"), \
            Detected("couldnt_check", "")
    d = detect(got.values)
    detail = f"MX {domain} = {', '.join(got.values) or 'nothing'}"
    steps = mx_steps(d)
    if d.key == "no_mx":
        return finding("email_mx", False, "This address has no mail servers listed, so emails sent to it will almost "
                       "certainly not arrive.", detail, NOT_SEEN, "mx_none", steps), d
    if d.key == "null_mx":
        return finding("email_mx", False, "This address says it doesn't accept email.", detail, SEEN, "mx_null",
                       "This is a deliberate setting. If you do want email here, choose an email service and replace "
                       "this setting with the mail servers that service gives you."), d
    literal = [h for h in d.hosts if _is_ip(h)]
    if literal:
        return finding("email_mx", False, "Its mail server is listed as a bare number instead of a name, which mail "
                       "services refuse.", detail, SEEN, "mx_ip_literal", steps), d
    alias, dead, unsure = [], [], False
    for h in dict.fromkeys(d.hosts):
        if lookup(dns, h, "CNAME").values:
            alias.append(h)
            continue
        a, aaaa = lookup(dns, h, "A"), lookup(dns, h, "AAAA")
        if a.values or aaaa.values:
            continue
        if "error" in (a.status, aaaa.status):
            unsure = True
        else:
            dead.append(h)
    if dead and len(dead) == len(set(d.hosts)):
        return finding("email_mx", False, "Its mail servers are listed by names that don't exist, so emails to it "
                       "can't be delivered.", f"{detail}; no address for {', '.join(dead)}", SEEN, "mx_unresolvable",
                       steps), d
    if dead:
        return finding("email_mx", None, "One of its mail servers is listed by a name that doesn't exist. Emails "
                       "still have another way in.", f"{detail}; no address for {', '.join(dead)}", SEEN,
                       "mx_partly_unresolvable", steps), d
    if alias:
        return finding("email_mx", None, "Its mail server name is an alias for another name. The rules for email "
                       "don't allow that, and some mail services refuse it.",
                       f"{detail}; CNAME at {', '.join(alias)}", SEEN, "mx_cname", steps), d
    if d.key == "mixed":
        return finding("email_mx", None, f"Emails to this address are split between two different email services "
                       f"({d.label}), so some may go to the wrong one.", detail, SEEN, "mx_mixed", UNKNOWN_STEPS), d
    if unsure:
        return finding("email_mx", None, "It lists mail servers, but we couldn't confirm they exist just now (the "
                       "problem was on our side).", detail, COULDNT, "mx_couldnt_check"), d
    if d.key == "unknown":
        return finding("email_mx", True, "Emails to this address have somewhere to go (an email service we don't "
                       "recognise).", detail, SEEN, "mx_ok_unknown"), d
    return finding("email_mx", True, f"Emails to this address have somewhere to go: {d.label}.", detail, SEEN,
                   "mx_ok"), d


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def mx_steps(d: Detected) -> str:
    if d.service is None:
        return UNKNOWN_STEPS
    return f"{d.service.label}'s own mail servers are: {d.service.mx_doc}. Set them in {d.service.where}."


# ---------- sending permission (SPF) ----------

MECH = re.compile(r"^([+\-~?]?)(all|include|a|mx|ptr|ip4|ip6|exists)(?:([:/])(.*))?$", re.I)
MODIFIER = re.compile(r"^([a-z][a-z0-9_.\-]*)=(.*)$", re.I)


def spf_records(values) -> list[str]:
    texts = [txt_value(v) for v in values]
    return [t for t in texts if t.lower() == "v=spf1" or t.lower().startswith("v=spf1 ")]


@dataclass
class SpfSeen:
    lookups: int = 0
    voids: int = 0
    queries: int = 0
    includes: set[str] = field(default_factory=set)
    problems: list[tuple[str, str]] = field(default_factory=list)  # (code, technical detail)
    unsure: bool = False  # one of OUR lookups failed, or a macro we can't expand: counts are "at least"
    all: str = ""  # the qualifier of the final `all` ("+", "-", "~", "?"), "" if there is none


def spf_syntax(record: str) -> str:
    """The first term that isn't valid SPF, or ""."""
    for term in record.split()[1:]:
        m = MECH.match(term)
        if m:
            _q, name, sep, arg = m.group(1), m.group(2).lower(), m.group(3), m.group(4) or ""
            if name == "all" and sep:
                return term
            if name in ("include", "exists") and (sep != ":" or not arg):
                return term
            if name in ("ip4", "ip6"):
                try:
                    net = ipaddress.ip_network(arg, strict=False)
                except ValueError:
                    return term
                if sep != ":" or net.version != int(name[2]):
                    return term
            continue
        if not MODIFIER.match(term):
            return term
    return ""


def spf_walk(domain: str, record: str, dns: DnsResolver, seen: SpfSeen | None = None, stack: tuple[str, ...] = (),
             top: bool = True) -> SpfSeen:
    """Count the DNS lookups an SPF check of `record` costs (include, a, mx, ptr, exists, redirect), following
    includes and redirects, with a depth cap, a total-question cap and loop protection."""
    seen = seen or SpfSeen()
    stack = stack + (domain.lower(),)
    bad = spf_syntax(record)
    if bad:
        seen.problems.append(("spf_syntax", f"can't read {bad!r} in the SPF of {domain}"))
        return seen
    redirect, has_all = "", False
    for term in record.split()[1:]:
        m = MECH.match(term)
        if m is None:
            mod = MODIFIER.match(term)
            if mod and mod.group(1).lower() == "redirect":
                redirect = mod.group(2).lower().rstrip(".")
            continue
        qualifier, name, arg = m.group(1) or "+", m.group(2).lower(), (m.group(4) or "")
        if name == "all":
            has_all = True
            if top:
                seen.all = qualifier
            break  # everything after `all` is ignored
        if name in ("ip4", "ip6"):
            continue
        seen.lookups += 1
        target = (arg.split("/")[0] if m.group(3) == ":" else "").lower().rstrip(".") or domain
        if "%" in target:  # a macro: its value depends on the sender, so we can't follow it
            seen.unsure = True
            continue
        if name == "include":
            _follow(target, dns, seen, stack, "include")
        elif name in ("a", "mx"):
            _void(dns, seen, target, "A" if name == "a" else "MX")
    if redirect and not has_all:
        seen.lookups += 1
        if "%" in redirect:
            seen.unsure = True
        else:
            _follow(redirect, dns, seen, stack, "redirect", top)
    return seen


def _ask(dns: DnsResolver, seen: SpfSeen, name: str, rtype: str):
    if seen.queries >= SPF_MAX_QUERIES:
        seen.unsure = True
        return None
    seen.queries += 1
    got = lookup(dns, name, rtype)
    if got.status == "error":
        seen.unsure = True
        return None
    return got


def _void(dns: DnsResolver, seen: SpfSeen, name: str, rtype: str) -> None:
    got = _ask(dns, seen, name, rtype)
    if got is not None and not got.values:
        seen.voids += 1


def _follow(target: str, dns: DnsResolver, seen: SpfSeen, stack: tuple[str, ...], kind: str, top: bool = False) -> None:
    seen.includes.add(target)
    if target in stack:
        seen.problems.append(("spf_loop", f"{kind} of {target} goes round in a circle: {' -> '.join(stack + (target,))}"))
        return
    if len(stack) >= SPF_MAX_DEPTH:
        seen.problems.append(("spf_too_deep", f"more than {SPF_MAX_DEPTH} levels of include at {target}"))
        return
    got = _ask(dns, seen, target, "TXT")
    if got is None:
        return
    records = spf_records(got.values)
    if not got.values:
        seen.voids += 1
    if len(records) != 1:
        seen.problems.append(("spf_include_broken", f"{kind} target {target} has {len(records)} SPF records"))
        return
    spf_walk(target, records[0], dns, seen, stack, top=top and kind == "redirect")


SPF_TEXT = {
    "spf_multiple": "It has more than one sending-permission line. Mail services treat that as an error, so "
                    "neither line counts and its emails may land in spam.",
    "spf_syntax": "Its sending-permission line has a mistake in it, so mail services can't read it.",
    "spf_too_many_lookups": "Its sending-permission line makes mail services look up too many other names "
                            "({n}; the limit is 10), so they give up and treat it as broken.",
    "spf_too_many_voids": "Its sending-permission line refers to {n} names that don't exist (the limit is 2), so "
                          "mail services may treat it as broken.",
    "spf_loop": "Its sending-permission line refers back to itself in a circle, so mail services treat it as broken.",
    "spf_too_deep": "Its sending-permission line is nested too deeply to follow, so mail services treat it as broken.",
    "spf_include_broken": "Its sending-permission line refers to another name that has no working "
                          "sending-permission line of its own, so mail services treat it as broken.",
    "spf_plus_all": "Its sending-permission line allows every server in the world to send as this address, so it "
                    "protects nothing.",
    "spf_neutral_all": "Its sending-permission line takes no position on other servers, so it protects nothing.",
    "spf_no_all": "Its sending-permission line doesn't say what to do with other servers, so it protects very little.",
    "spf_missing": "It doesn't say which servers may send its email, so its emails may land in spam.",
    "spf_ok_hard": "It says which servers may send its email, and tells mail services to refuse all others.",
    "spf_ok_soft": "It says which servers may send its email, and tells mail services to treat all others as suspicious.",
    "spf_unsure": "It has a sending-permission line, but we couldn't follow everything it refers to just now, so we "
                  "can't say whether it is within the limits.",
}


def spf_steps(d: Detected, code: str) -> str:
    one = "Keep exactly one line that starts with v=spf1: merge the services you send from into it and delete the others."
    if code == "spf_multiple":
        return one
    if d.service is None:
        if d.key in ("null_mx", "no_mx"):
            return "If this address never sends email, the usual line is: v=spf1 -all"
        return UNKNOWN_STEPS
    base = f"{d.service.label}'s own line is: {d.service.spf_line}  (set it in your domain's DNS settings)."
    if code in ("spf_too_many_lookups", "spf_too_many_voids", "spf_include_broken", "spf_loop", "spf_too_deep"):
        return "Remove the services you no longer send from, so fewer names are referred to. " + base
    return base + (f" {d.service.note}" if d.service.note else "")


def covers(service: Service, include: str) -> bool:
    """`include` is one of the service's own names, or sits under one (spf.zoho.com counts for zoho.com)."""
    return any(include == own or include.endswith("." + own) for own in service.spf)


def spf_finding(domain: str, dns: DnsResolver, d: Detected) -> dict:
    got = lookup(dns, domain, "TXT")
    if got.status == "error":
        return finding("email_spf", None, OUR_SIDE, f"TXT {domain}: lookup failed", COULDNT, "spf_couldnt_check")
    records = spf_records(got.values)
    detail = "; ".join(records)

    def out(ok, code, sure=SEEN, extra="", **fmt):
        return finding("email_spf", ok, SPF_TEXT[code].format(**fmt), (detail + (f" ({extra})" if extra else "")),
                       sure, code, "" if ok else spf_steps(d, code))

    if not records:
        return out(False, "spf_missing", NOT_SEEN)
    if len(records) > 1:
        return out(False, "spf_multiple", extra=f"{len(records)} records")
    seen = spf_walk(domain, records[0], dns)
    counts = f"{seen.lookups} lookups, {seen.voids} empty"
    for code in ("spf_syntax", "spf_loop", "spf_too_deep"):
        hit = next((p for p in seen.problems if p[0] == code), None)
        if hit:
            return out(False, code, extra=hit[1])
    if seen.lookups > SPF_LOOKUP_LIMIT:
        return out(False, "spf_too_many_lookups", extra=counts, n=seen.lookups)
    broken = next((p for p in seen.problems if p[0] == "spf_include_broken"), None)
    if broken:
        return out(False, "spf_include_broken", extra=broken[1])
    if seen.voids > SPF_VOID_LIMIT:
        return out(False, "spf_too_many_voids", extra=counts, n=seen.voids)
    if seen.all == "+":
        return out(False, "spf_plus_all", extra=counts)
    if seen.all == "?":
        return out(False, "spf_neutral_all", extra=counts)
    if seen.unsure:
        return out(None, "spf_unsure", COULDNT, extra=f"at least {counts}")
    if seen.all == "":
        return out(None, "spf_no_all", extra=counts)
    if d.service is not None and not any(covers(d.service, inc) for inc in seen.includes):
        return finding("email_spf", None, f"It has a sending-permission line, but we didn't see {d.service.label} named "
                       f"in it. If this address sends email through {d.service.label}, those emails may land in spam.",
                       f"{detail} ({counts}; expected include:{d.service.spf[0]})", NOT_SEEN, "spf_not_covering",
                       spf_steps(d, "spf_not_covering"))
    return out(True, "spf_ok_hard" if seen.all == "-" else "spf_ok_soft", extra=counts)


# ---------- protection against fake email (DMARC) ----------

DMARC_STEPS = ("Add one line at the name _dmarc under your domain. A safe start is: v=DMARC1; p=none; "
               "rua=mailto:<an address you read>. Once the reports look right, change p=none to p=quarantine.")


def dmarc_tags(record: str) -> dict[str, str] | None:
    tags = {}
    for part in record.split(";"):
        if not part.strip():
            continue
        if "=" not in part:
            return None
        k, v = part.split("=", 1)
        tags[k.strip().lower()] = v.strip()
    return tags


def dmarc_finding(domain: str, dns: DnsResolver) -> dict:
    labels = domain.split(".")
    names = [".".join(labels[i:]) for i in range(max(len(labels) - 1, 1))]  # the domain, then its parents
    for i, name in enumerate(names):
        got = lookup(dns, f"_dmarc.{name}", "TXT")
        if got.status == "error":
            return finding("email_dmarc", None, OUR_SIDE, f"TXT _dmarc.{name}: lookup failed", COULDNT,
                           "dmarc_couldnt_check")
        records = [t for t in (txt_value(v) for v in got.values) if t.lower().replace(" ", "").startswith("v=dmarc1")]
        if records:
            return _dmarc_judge(records, name, inherited=i > 0)
    return finding("email_dmarc", False, "It isn't protected against fake emails in its name.",
                   f"TXT _dmarc.{domain} = nothing", NOT_SEEN, "dmarc_missing", DMARC_STEPS)


def _dmarc_judge(records: list[str], name: str, inherited: bool) -> dict:
    detail = f"TXT _dmarc.{name} = " + "; ".join(records)
    if len(records) > 1:
        return finding("email_dmarc", False, "It has more than one fake-email protection line, so mail services "
                       "ignore them all.", detail, SEEN, "dmarc_multiple",
                       "Keep exactly one line that starts with v=DMARC1 at _dmarc and delete the others.")
    tags = dmarc_tags(records[0])
    policy = (tags or {}).get("sp" if inherited and "sp" in (tags or {}) else "p", "").lower()
    if tags is None or tags.get("v", "").upper() != "DMARC1" or policy not in ("none", "quarantine", "reject"):
        return finding("email_dmarc", False, "Its fake-email protection line has a mistake in it, so mail services "
                       "ignore it.", detail, SEEN, "dmarc_syntax", DMARC_STEPS)
    reports = " Reports about it are sent to an address its owner chose." if tags.get("rua") else ""
    parent = " (the rule is set on its parent name)" if inherited else ""
    if policy == "none":
        return finding("email_dmarc", None, "It only watches for fake emails in its name (monitoring only): fake mail "
                       f"in its name still gets through{parent}.{reports}", detail, SEEN, "dmarc_none",
                       "When the reports look right, change p=none to p=quarantine in the line at _dmarc.")
    what = "sent to spam" if policy == "quarantine" else "refused"
    return finding("email_dmarc", True, f"It is protected against fake emails in its name: they are {what}{parent}."
                   f"{reports}", detail, SEEN, f"dmarc_{policy}")


# ---------- signing (DKIM) ----------

def selectors_for(d: Detected) -> tuple[str, ...]:
    """Only the detected service's own labels (plus ours, for the two services LaunchWitness itself sets up).
    An unrecognised service gets none: we don't guess."""
    if d.service is None:
        return ()
    return tuple(dict.fromkeys(d.service.dkim + (OUR_SELECTORS if d.service.key in ("secureserver", "titan") else ())))


def _has_key(values) -> bool:
    return any(re.search(r"(^|;)\s*p=", txt_value(v)) for v in values)


def dkim_finding(domain: str, dns: DnsResolver, d: Detected) -> dict:
    """A signing key can only be fetched by its label. We try the service's documented labels; anything else is
    "couldn't check", never "missing"."""
    how = d.service.dkim_how if d.service is not None else UNKNOWN_STEPS
    if d.key in ("null_mx", "no_mx"):
        return finding("email_dkim", None, "This address isn't set up for email, so there is no email signing to "
                       "check.", "no mail servers", SEEN, "dkim_not_applicable")
    tried, half = [], []
    if _has_key(lookup(dns, f"lw-no-such-label._domainkey.{domain}", "TXT").values):
        # a catch-all answers for ANY label, so an answer for a label we know proves nothing
        return finding("email_dkim", None, "We couldn't check whether its emails are signed: a signing key can only "
                       "be looked up by its private label, and we don't know this address's.",
                       "a wildcard answers for every label", COULDNT, "dkim_couldnt_check", how)
    for sel in selectors_for(d):
        name = f"{sel}._domainkey.{domain}"
        tried.append(sel)
        txt = [txt_value(v) for v in lookup(dns, name, "TXT").values]
        alias = [v.rstrip(".") for v in lookup(dns, name, "CNAME").values]
        if not txt and alias:
            txt = [txt_value(v) for v in lookup(dns, alias[0], "TXT").values]
        key = next((t for t in txt if re.search(r"(^|;)\s*p=", t)), None)
        if key is not None and re.search(r"(^|;)\s*p=\s*(;|$)", key):
            return finding("email_dkim", None, "It has a signing key for its emails, but the key has been switched "
                           "off (withdrawn).", f"{name}: empty p=", SEEN, "dkim_revoked", how)
        if key is not None:
            return finding("email_dkim", True, "Its emails can be signed: we found a signing key.",
                           f"{name}: key found", SEEN, "dkim_found")
        if alias:
            half.append(f"{name} -> {alias[0]} (no key there)")
    if half:
        return finding("email_dkim", None, "Signing is set up for its emails, but the key it points to isn't "
                       "published. Signing may not be switched on yet.", "; ".join(half), NOT_SEEN, "dkim_half", how)
    tried_text = f"tried: {', '.join(tried)}" if tried else "no known label to try"
    return finding("email_dkim", None, "We couldn't check whether its emails are signed: a signing key can only be "
                   "looked up by its private label, and we don't know this address's.", tried_text, COULDNT,
                   "dkim_couldnt_check", how)


# ---------- all of it ----------

def mail_findings(host: str, dns: DnsResolver) -> list[dict]:
    domain = mail_domain(host, dns)
    mx, d = mx_finding(domain, dns)
    out = [mx, spf_finding(domain, dns, d), dkim_finding(domain, dns, d), dmarc_finding(domain, dns)]
    for f in out:  # provider_label only for a service we recognise ("Your email runs on Google Workspace")
        f["domain"], f["provider"], f["provider_label"] = domain, d.key, d.label if d.service else ""
    return out
