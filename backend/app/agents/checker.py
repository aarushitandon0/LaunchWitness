"""Checker (code only): proves a finished launch works (SPEC §6).

Checks: site points to the server (asked of the AUTHORITATIVE nameservers via
`integ.dns`), site opens over HTTPS with a valid certificate, email settings
(MX, SPF, DKIM, DMARC of the domain the order mailbox is on, compared with the
mail provider table; read-only), and a real test order arrives. Each result is
stored as a CheckResult row and an AuditEvent. Launch steps are not a check:
the report shows them separately.
"""

import json
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import Session

from app import audit
from app.agents.executor import Ctx
from app.agents.planner import DKIM_PENDING
from app.agents.reader import Profile
from app.mail.providers import provider_for
from app.models import CheckResult, utcnow
from app.sites.orders import place_order


@dataclass
class Outcome:
    check: str
    passed: bool
    plain: str  # one line for the seller
    detail: str = ""  # technical


def _txt(values: list[str]) -> list[str]:
    return [v.strip('"') for v in values]


def check_site_points(ctx: Ctx) -> Outcome:
    host, want = ctx.plan.site_host, ctx.settings.server_ip
    got = ctx.integ.dns.resolve(host, "A")
    ok = want in got
    return Outcome("site_points", ok, "Your address leads to your website." if ok else
                   "Your address doesn't lead to your website yet.", f"A {host} = {got or 'nothing'}; want {want}")


def check_https(ctx: Ctx) -> Outcome:
    r = ctx.integ.http.fetch(f"https://{ctx.plan.site_host}/")
    ok = r.ok and r.cert_valid
    plain = ("Your website opens securely (the padlock shows)." if ok else
             "Your website's security certificate isn't working yet." if not r.cert_valid else
             "Your website didn't open.")
    return Outcome("https", ok, plain, f"status={r.status} cert_valid={r.cert_valid} {r.error}".strip())


def mail_zone(ctx: Ctx) -> str:
    """The domain whose mail settings matter for this shop's orders: the seller's own domain on
    an own-name launch, else the domain the order mailbox is on (the app's)."""
    return ctx.plan.zone if ctx.plan.mode == "full" else ctx.plan.mailbox.rsplit("@", 1)[-1].lower()


def check_email_mx(ctx: Ctx) -> Outcome:
    zone, provider = mail_zone(ctx), provider_for(ctx.settings)
    got = ctx.integ.dns.resolve(zone, "MX")
    hosts = {v.split()[-1].rstrip(".").lower() for v in got}
    ok = all(h in hosts for _, h in provider.mx)
    return Outcome("email_mx", ok, "Emails to your address reach your mailbox." if ok else
                   "Emails sent to your address can't reach your mailbox.",
                   f"MX {zone} = {got or 'nothing'}; expected {provider.label}")


def check_email_spf(ctx: Ctx) -> Outcome:
    zone, provider = mail_zone(ctx), provider_for(ctx.settings)
    got = _txt(ctx.integ.dns.resolve(zone, "TXT"))
    ok = any(v.startswith("v=spf1") and provider.spf_include in v for v in got)
    return Outcome("email_spf", ok, "Your mailbox is allowed to send email for you." if ok else
                   "Your emails may land in spam: the sending permission is missing.",
                   f"TXT {zone} = {got or 'nothing'}; expected {provider.spf_include}")


def dkim_names(ctx: Ctx, zone: str) -> list[str]:
    """Signing record names: the ones this launch planned, else whatever the live zone has."""
    names = [c["name"] for c in ctx.changes if c["name"].endswith("._domainkey")]
    if not names:
        try:
            names = sorted({r["name"] for r in ctx.integ.godaddy.get_records(zone) if r["name"].endswith("._domainkey")})
        except Exception:  # can't list the zone (not ours): fall back to the provider's usual names
            names = []
    return names or [f"{sel}._domainkey" for sel in provider_for(ctx.settings).dkim_selectors]


def check_email_dkim(ctx: Ctx) -> Outcome:
    zone = mail_zone(ctx)
    names, seen = dkim_names(ctx, zone), {}
    for name in names:
        txt = _txt(ctx.integ.dns.resolve(f"{name}.{zone}", "TXT"))
        seen[name] = (any(v.startswith("v=DKIM1") and "p=" in v for v in txt)
                      or bool(ctx.integ.dns.resolve(f"{name}.{zone}", "CNAME")))
    ok = bool(seen) and all(seen.values())
    return Outcome("email_dkim", ok, "Your emails are signed so customers can trust them." if ok else
                   "Your emails aren't signed, so they may land in spam.",
                   f"signing records on {zone}: {seen or 'none found'}")


def check_email_dmarc(ctx: Ctx) -> Outcome:
    zone = mail_zone(ctx)
    got = _txt(ctx.integ.dns.resolve(f"_dmarc.{zone}", "TXT"))
    ok = any(v.startswith("v=DMARC1") for v in got)
    return Outcome("email_dmarc", ok, "Fake emails in your name will be treated as spam." if ok else
                   "Order emails could land in spam: a protection setting is missing.",
                   f"TXT _dmarc.{zone} = {got or 'nothing'}")


def check_test_order(ctx: Ctx) -> Outcome:
    """Place a test order through the same code and to the same people as a customer's order,
    then look in the inbox we can read for THIS run's random code (never an older email)."""
    profile = Profile.model_validate_json(ctx.business.profile_json)
    first = next((x for x in profile.products if not x.addon), profile.products[0])
    data = {"customer_name": "LaunchWitness test", "customer_phone": "0000000000",
            "note": "Automatic test order from your launch check. No action needed.",
            "items": [{"name": first.name, "qty": 1, "price_inr": first.price_inr}], "total_inr": first.price_inr}
    started, nonce = utcnow(), secrets.token_hex(8)
    order = place_order(ctx.session, ctx.integ.mailer, ctx.settings, business=ctx.business, profile=profile,
                        data=data, is_test=True, nonce=nonce)
    if order.email_status != "sent":
        return Outcome("test_order", False, "We couldn't send a test order email.", f"order #{order.id} email failed")
    for i in range(3):
        if ctx.integ.inbox.find(subject_contains=nonce, since=started - timedelta(minutes=2)):
            return Outcome("test_order", True, "A test order arrived in your inbox.",
                           f"order #{order.id} code {nonce} found")
        if i < 2:
            ctx.integ.sleep(20)
    return Outcome("test_order", False, "A test order was sent but hasn't arrived in your inbox.",
                   f"order #{order.id} code {nonce} not found in {ctx.plan.mailbox}")


def check_settings_match(ctx: Ctx) -> Outcome:
    """Monitoring (daily): every setting the launch wrote still has the value it wrote."""
    current = {}
    for zone in {c["zone"] for c in ctx.changes}:
        for r in ctx.integ.godaddy.get_records(zone):
            current.setdefault((zone, r["type"], r["name"]), set()).add(str(r.get("data", "")))
    changed = []
    for c in ctx.changes:
        want = {str(r.get("data", "")) for r in c["after"]}
        have = current.get((c["zone"], c["type"], c["name"]), set())
        ok = bool(have) if (c["deferred"] or DKIM_PENDING in want) else want <= have
        if not ok:
            changed.append(f"{c['type']} {c['name']}")
    ok = not changed
    return Outcome("settings_match", ok, "Your settings are the same as at launch." if ok else
                   "Some of your settings changed since launch.", f"changed: {changed}" if changed else "all match")


CHECKS = {
    "site_points": check_site_points,
    "https": check_https,
    "email_mx": check_email_mx,
    "email_spf": check_email_spf,
    "email_dkim": check_email_dkim,
    "email_dmarc": check_email_dmarc,
    "test_order": check_test_order,
    "settings_match": check_settings_match,  # monitoring only
}
LAUNCH_CHECKS = ["site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc", "test_order"]
TITLES = {
    "site_points": "Your address leads to your website",
    "https": "Your website opens securely",
    "email_mx": "Emails reach your mailbox",
    "email_spf": "Your mailbox may send email for you",
    "email_dkim": "Your emails are signed",
    "email_dmarc": "Protection against fake emails in your name",
    "test_order": "A test order reached your inbox",
    "settings_match": "Your settings are unchanged since launch",
}


def checks_for(ctx: Ctx) -> list[str]:
    return list(LAUNCH_CHECKS)  # the same proof for every launch; only the allowed fixes differ by mode


def run_check(ctx: Ctx, name: str, attempt: int = 0) -> Outcome:
    try:
        out = CHECKS[name](ctx)
    except Exception as e:  # a check that crashes is a failed check, never a crash of the launch
        out = Outcome(name, False, "We couldn't complete this check.", f"{type(e).__name__}: {e}"[:300])
    save(ctx.session, ctx, out, attempt)
    return out


def save(session: Session, ctx: Ctx, out: Outcome, attempt: int) -> None:
    session.add(CheckResult(business_id=ctx.business.id, plan_id=ctx.plan.id, run_id=ctx.run_id, check=out.check, passed=out.passed,
                            detail=json.dumps({"plain": out.plain, "detail": out.detail}), attempt=attempt))
    session.commit()
    audit.record(session, actor="checker", action=f"check_{out.check}", target=ctx.plan.site_host,
                 result="pass" if out.passed else "fail", business_id=ctx.business.id,
                 detail=f"attempt {attempt}: {out.detail}"[:500])


def run_all(ctx: Ctx) -> list[Outcome]:
    return [run_check(ctx, name) for name in checks_for(ctx)]
