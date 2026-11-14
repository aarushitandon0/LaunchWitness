"""Checker (code only): proves a finished launch works (SPEC §6).

Checks: site points to the server (asked of the AUTHORITATIVE nameservers via
`integ.dns`), site opens over HTTPS with a valid certificate, email settings
(MX, SPF, DKIM, DMARC — full launches only; sandbox uses the app mailbox), a
real test order arrives, and the launch finished cleanly. Each result is stored
as a CheckResult row and an AuditEvent.
"""

import json
from dataclasses import dataclass

from sqlmodel import Session

from app import audit
from app.agents.executor import Ctx
from app.agents.planner import DKIM_PENDING
from app.agents.reader import Profile
from app.godaddy.email import TITAN_MX
from app.models import CheckResult
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


def check_email_mx(ctx: Ctx) -> Outcome:
    got = ctx.integ.dns.resolve(ctx.plan.zone, "MX")
    hosts = {v.split()[-1].rstrip(".") for v in got}
    ok = all(h in hosts for _, h in TITAN_MX)
    return Outcome("email_mx", ok, "Emails to your address reach your mailbox." if ok else
                   "Emails sent to your address can't reach your mailbox.", f"MX = {got or 'nothing'}")


def check_email_spf(ctx: Ctx) -> Outcome:
    got = _txt(ctx.integ.dns.resolve(ctx.plan.zone, "TXT"))
    ok = any(v.startswith("v=spf1") and "include:spf.titan.email" in v for v in got)
    return Outcome("email_spf", ok, "Your mailbox is allowed to send email for you." if ok else
                   "Your emails may land in spam: the sending permission is missing.", f"TXT @ = {got or 'nothing'}")


def check_email_dkim(ctx: Ctx) -> Outcome:
    name = next((c["name"] for c in ctx.changes if c["name"].endswith("._domainkey")), "titan1._domainkey")
    got = _txt(ctx.integ.dns.resolve(f"{name}.{ctx.plan.zone}", "TXT"))
    ok = any(v.startswith("v=DKIM1") and "p=" in v for v in got)
    return Outcome("email_dkim", ok, "Your emails are signed so customers can trust them." if ok else
                   "Your emails aren't signed, so they may land in spam.", f"TXT {name} = {got or 'nothing'}")


def check_email_dmarc(ctx: Ctx) -> Outcome:
    got = _txt(ctx.integ.dns.resolve(f"_dmarc.{ctx.plan.zone}", "TXT"))
    ok = any(v.startswith("v=DMARC1") for v in got)
    return Outcome("email_dmarc", ok, "Fake emails in your name will be treated as spam." if ok else
                   "Order emails could land in spam: a protection setting is missing.", f"TXT _dmarc = {got or 'nothing'}")


def check_test_order(ctx: Ctx) -> Outcome:
    """Place a real order through the seller's order code, then look for it in the demo inbox."""
    profile = Profile.model_validate_json(ctx.business.profile_json)
    first = next((x for x in profile.products if not x.addon), profile.products[0])
    data = {"customer_name": "LaunchWitness test", "customer_phone": "0000000000",
            "note": "Automatic test order from your launch check. No action needed.",
            "items": [{"name": first.name, "qty": 1, "price_inr": first.price_inr}], "total_inr": first.price_inr}
    order = place_order(ctx.session, ctx.integ.mailer, business=ctx.business, profile=profile, data=data,
                        mail_to=ctx.plan.mailbox, is_test=True)
    if order.email_status != "sent":
        return Outcome("test_order", False, "We couldn't send a test order email.", f"order #{order.id} email failed")
    for i in range(3):
        if ctx.integ.inbox.find(subject_contains=f"(#{order.id})"):
            return Outcome("test_order", True, "A test order arrived in your inbox.", f"order #{order.id} found")
        if i < 2:
            ctx.integ.sleep(20)
    return Outcome("test_order", False, "A test order was sent but hasn't arrived in your inbox.",
                   f"order #{order.id} not found in {ctx.plan.mailbox}")


def check_launch_clean(ctx: Ctx) -> Outcome:
    steps = json.loads(ctx.plan.steps_json)
    bad = [s["title"] for s in steps if s["status"] not in ("done", "skipped")]
    ok = ctx.plan.status == "done" and not bad
    return Outcome("launch_clean", ok, "Every launch step finished." if ok else
                   "Some launch steps didn't finish.", f"plan {ctx.plan.status}; unfinished: {bad}")


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
    "launch_clean": check_launch_clean,
    "settings_match": check_settings_match,  # monitoring only
}
LAUNCH_CHECKS = ["site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc", "test_order",
                 "launch_clean"]
SANDBOX_CHECKS = ["site_points", "https", "test_order", "launch_clean"]
TITLES = {
    "site_points": "Your address leads to your website",
    "https": "Your website opens securely",
    "email_mx": "Emails reach your mailbox",
    "email_spf": "Your mailbox may send email for you",
    "email_dkim": "Your emails are signed",
    "email_dmarc": "Protection against fake emails in your name",
    "test_order": "A test order reached your inbox",
    "launch_clean": "Every launch step finished",
    "settings_match": "Your settings are unchanged since launch",
}


def checks_for(ctx: Ctx) -> list[str]:
    return list(LAUNCH_CHECKS) if ctx.plan.mode == "full" else list(SANDBOX_CHECKS)


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
