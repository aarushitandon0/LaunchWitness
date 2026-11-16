"""Checker (code only): proves a finished launch works (SPEC §6).

Checks: site points to the server (asked of the AUTHORITATIVE nameservers via
`integ.dns`), site opens over HTTPS with a valid certificate, email settings
(MX, SPF, DKIM, DMARC of the domain the order mailbox is on, compared with the
mail provider table; read-only), and a real test order arrives. Each result is
stored as a CheckResult row and an AuditEvent. Launch steps are not a check:
the report shows them separately.
"""

import json
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urljoin

from sqlmodel import Session, select

from app import audit, proof
from app.agents.executor import Ctx
from app.agents.planner import DKIM_PENDING
from app.agents.reader import Profile
from app.checks.dns_resolver import lookup
from app.mail.providers import provider_for
from app.models import CheckResult, Order, Outbox, utcnow
from app.sites.orders import order_recipients


@dataclass
class Outcome:
    check: str
    passed: bool
    plain: str  # one line for the seller
    detail: str = ""  # technical
    waiting: bool = False  # passed as far as we can see, but delivery still needs the owner's "Yes, I got it"
    unfinished: bool = False  # we couldn't complete it (our lookup failed, or time ran out): not passed, not her fault
    keeps_breaking: bool = False  # fixed several times today and broken again: automatic fixing has stopped


class CouldntCheck(Exception):
    """Something on OUR side failed, so the check has no answer. Never a failure of the shop."""


OUR_SIDE = ("We couldn't look this up just now. The problem is on our side, not yours, and nothing about your shop has "
            "changed. We'll check again on the next round.")
OUT_OF_TIME = "This check couldn't finish in time, so we don't know yet. We'll try again on the next round."


def dns_values(ctx: Ctx, name: str, rtype: str) -> list[str]:
    """One DNS answer for a check. A lookup that failed on our side raises, so it can't be read as "missing"."""
    got = lookup(ctx.integ.dns, name, rtype)
    if got.status == "error":
        raise CouldntCheck(f"{rtype} {name}: our lookup failed")
    return list(got.values)


def practice_world(ctx: Ctx) -> bool:
    return bool(ctx.integ.fake or ctx.business.practice)


def evidence(ctx: Ctx, check: str, step: str, **fields) -> None:
    if ctx.abandoned:  # S13 B: the watchdog gave up on this check; its late answers aren't proof of this run
        return
    proof.add(ctx.session, business=ctx.business, run_id=ctx.run_id, check=check, step=step,
              practice=practice_world(ctx), **fields)


def dns_server(ctx: Ctx) -> str:
    return getattr(ctx.integ.dns, "last_server", "") or ("pretend nameserver" if ctx.integ.fake else "")


def shop_web(ctx: Ctx) -> proof.ShopWeb:
    """How the checker reaches the shop like a customer: in-process for practice, else over the internet
    to the shop's own host only (SSRF-guarded)."""
    factory = getattr(ctx.integ, "shop_web", None)
    if factory is not None:
        return factory(ctx)
    if practice_world(ctx):
        return proof.PracticeShopWeb(ctx.session, ctx.settings, ctx.integ.mailer, ctx.business, ctx.plan.site_host)
    return proof.real_shop_web(ctx.plan.site_host)


def _txt(values: list[str]) -> list[str]:
    return [v.strip('"') for v in values]


def check_site_points(ctx: Ctx) -> Outcome:
    host, want = ctx.plan.site_host, ctx.settings.server_ip
    got = dns_values(ctx, host, "A")
    ok = want in got
    evidence(ctx, "site_points", "dns_answer", answer=f"A {host} = {', '.join(got) or 'nothing'}",
             server=dns_server(ctx), source="authoritative nameserver")
    return Outcome("site_points", ok, "Your address leads to your website." if ok else
                   "Your address doesn't lead to your website yet.", f"A {host} = {got or 'nothing'}; want {want}")


HTTPS_BACKOFF = (5, 10, 20, 40, 45)  # seconds: up to 2 minutes while a new certificate is being issued


def check_https(ctx: Ctx) -> Outcome:
    url = f"https://{ctx.plan.site_host}/"
    for i in range(len(HTTPS_BACKOFF) + 1):
        r = ctx.integ.http.fetch(url)
        if r.ok and r.cert_valid:
            break
        if i < len(HTTPS_BACKOFF):
            ctx.integ.sleep(HTTPS_BACKOFF[i])
    ok = r.ok and r.cert_valid
    detail = f"status={r.status} cert_valid={r.cert_valid} {r.error}".strip()
    if not ok:
        plain = ("Your website's security certificate isn't working yet." if not r.cert_valid else
                 "Your website didn't open.")
        return Outcome("https", False, plain, detail)
    page = shop_web(ctx).get(url)
    if proof.marker(ctx.business) not in page.html:  # a parked page with a valid certificate is not her shop
        return Outcome("https", False, "Your address opens a page, but it isn't your shop.",
                       f"{detail}; shop marker missing (page status {page.status})")
    cert_end = ctx.integ.http.cert_expires(ctx.plan.site_host)
    evidence(ctx, "https", "http_response", status_code=r.status, cert_not_after=cert_end, server=page.server,
             source=url, answer="shop page with its lw-shop marker")
    return Outcome("https", True, "Your website opens securely (the padlock shows).", detail)


def mail_zone(ctx: Ctx) -> str:
    """The domain whose mail settings matter for this shop's orders: the seller's own domain on
    an own-name launch, else the domain the order mailbox is on (the app's)."""
    return ctx.plan.zone if ctx.plan.mode == "full" else ctx.plan.mailbox.rsplit("@", 1)[-1].lower()


def check_email_mx(ctx: Ctx) -> Outcome:
    zone, provider = mail_zone(ctx), provider_for(ctx.settings)
    got = dns_values(ctx, zone, "MX")
    hosts = {v.split()[-1].rstrip(".").lower() for v in got}
    ok = all(h in hosts for _, h in provider.mx)
    return Outcome("email_mx", ok, "Emails to your address reach your mailbox." if ok else
                   "Emails sent to your address can't reach your mailbox.",
                   f"MX {zone} = {got or 'nothing'}; expected {provider.label}")


def check_email_spf(ctx: Ctx) -> Outcome:
    zone, provider = mail_zone(ctx), provider_for(ctx.settings)
    got = _txt(dns_values(ctx, zone, "TXT"))
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
        txt = _txt(dns_values(ctx, f"{name}.{zone}", "TXT"))
        seen[name] = (any(v.startswith("v=DKIM1") and "p=" in v for v in txt)
                      or bool(dns_values(ctx, f"{name}.{zone}", "CNAME")))
    ok = bool(seen) and all(seen.values())
    return Outcome("email_dkim", ok, "Your emails are signed so customers can trust them." if ok else
                   "Your emails aren't signed, so they may land in spam.",
                   f"signing records on {zone}: {seen or 'none found'}")


def check_email_dmarc(ctx: Ctx) -> Outcome:
    zone = mail_zone(ctx)
    got = _txt(dns_values(ctx, f"_dmarc.{zone}", "TXT"))
    ok = any(v.startswith("v=DMARC1") for v in got)
    return Outcome("email_dmarc", ok, "Fake emails in your name will be treated as spam." if ok else
                   "Order emails could land in spam: a protection setting is missing.",
                   f"TXT _dmarc.{zone} = {got or 'nothing'}")


TEST_CUSTOMER = {"customer_name": "LaunchWitness test", "customer_phone": "0000000000",
                 "note": "Automatic test order from your launch check. No action needed."}


def check_test_order(ctx: Ctx) -> Outcome:
    """Order from the shop like a customer: open the public page, find the order form, post it with a
    one-time test code, then record each hop separately. Delivery is proven only by finding the email in
    an inbox we can read, or by the owner tapping "Yes, I got it"; a mail server's "accepted" is not delivery."""
    url = f"https://{ctx.plan.site_host}/"
    web = shop_web(ctx)
    profile = Profile.model_validate_json(ctx.business.profile_json)
    page = web.get(url)
    form = proof.find_order_form(page.html) if page.status == 200 else None
    if form is None:
        return Outcome("test_order", False, "We couldn't open your order form for a test order.",
                       f"GET {url}: status {page.status} {page.error}".strip())
    index = next((i for i, x in enumerate(profile.products) if not x.addon), 0)
    field = f"qty_{index}"
    if field not in form.qty_fields:
        return Outcome("test_order", False, "We couldn't find an item to order on your page.", f"{field} not in form")
    ticket = proof.new_ticket(ctx.session, ctx.business, ctx.run_id)
    started = utcnow()
    fields = {**form.hidden, **TEST_CUSTOMER, field: "1", "lw_test": ticket.nonce}
    sent = web.post(urljoin(url, form.action), fields)
    ctx.session.refresh(ticket)
    order = ctx.session.get(Order, ticket.order_id) if ticket.order_id else None
    if sent.status != 200 or order is None:
        return Outcome("test_order", False, "Your order form didn't accept a test order.",
                       f"POST {form.action}: status {sent.status} {sent.error}".strip())
    evidence(ctx, "test_order", "form_post", status_code=sent.status, nonce=ticket.nonce, source=web.source,
             server=sent.server, answer=f"order {order.ref}")
    sent_row = ctx.session.exec(select(Outbox).where(Outbox.key == f"order:{order.id}")).first()
    if order.email_status == "queued":  # S13: held back by our daily send budget (or not tried yet): our side
        return Outcome("test_order", False, "Your order form works. Our test email is waiting its turn to be sent, "
                       "so we'll finish this check on the next round.",
                       f"order {order.ref}: test email queued ({sent_row.last_error if sent_row else 'not tried'})",
                       unfinished=True)
    if order.email_status != "sent" or sent_row is None or sent_row.status != "sent":
        return Outcome("test_order", False, "Your order form works, but we couldn't send the order email.",
                       f"order {order.ref}: mail server refused or unreachable"
                       f"{f' ({sent_row.last_error})' if sent_row and sent_row.last_error else ''}")
    fake = ctx.integ.fake
    # the outbox's real send result: the Message-ID the mail server accepted, and which try it was
    evidence(ctx, "test_order", "smtp_accepted", message_id=sent_row.message_id, nonce=ticket.nonce,
             server="pretend mail server" if fake else ctx.settings.smtp_host, source="our mail server",
             answer=f"outbox {sent_row.id}, try {sent_row.attempts}")
    recipients = [r.lower() for r in order_recipients(ctx.session, ctx.settings, ctx.business)]
    readable = fake or ctx.settings.imap_user.lower() in recipients
    if not readable:  # her own inbox: only she can prove it arrived
        return Outcome("test_order", True, "The mail server accepted a test order for you. Tap “Yes, I got it” "
                       "in that email to prove it reached your inbox.", f"order {order.ref} code {ticket.nonce}",
                       waiting=True)
    tries = 3 if ctx.inbox_wait else 1
    for i in range(tries):
        if ctx.integ.inbox.find(subject_contains=ticket.nonce, since=started - timedelta(minutes=2)):
            evidence(ctx, "test_order", "imap_seen", nonce=ticket.nonce,
                     server="pretend inbox" if fake else ctx.settings.imap_host, source=ctx.settings.imap_user)
            return Outcome("test_order", True, "A test order reached your inbox.",
                           f"order {order.ref} code {ticket.nonce} found")
        if i < tries - 1:
            ctx.integ.sleep(20)
    if not ctx.inbox_wait:  # S13 B (monitoring): "accepted" is recorded; "seen" is looked for in a later short pass
        ctx.pending_inbox.append({"nonce": ticket.nonce, "since": (started - timedelta(minutes=2)).isoformat(),
                                  "ref": order.ref})
        return Outcome("test_order", True, "The mail server accepted a test order for you. We'll look for it in "
                       "the inbox again in a minute.", f"order {order.ref} code {ticket.nonce}: accepted, "
                       "inbox looked at once, looking again later", waiting=True)
    return Outcome("test_order", False, "A test order was sent but hasn't arrived in your inbox.",
                   f"order {order.ref} code {ticket.nonce} not found in {ctx.settings.imap_user}")


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


def outcome_of(ctx: Ctx, name: str) -> Outcome:
    try:
        return CHECKS[name](ctx)
    except CouldntCheck as e:
        return Outcome(name, False, OUR_SIDE, str(e), unfinished=True)
    except Exception as e:  # a check that crashes is a failed check, never a crash of the launch
        return Outcome(name, False, "We couldn't complete this check.", f"{type(e).__name__}: {e}"[:300])


def run_check(ctx: Ctx, name: str, attempt: int = 0) -> Outcome:
    out = outcome_of(ctx, name)
    save(ctx.session, ctx, out, attempt)
    return out


WATCHDOG_TEXT = ("This check took too long, so we stopped waiting for it. We don't know yet; we'll try again on the "
                 "next round.")


def run_check_watched(engine, ctx: Ctx, name: str, seconds: float) -> Outcome:
    """S13 B: a per-check watchdog. The check runs in its own thread with its OWN database session and copies of
    the shop's rows, so if it overruns we can stop waiting safely: it's marked "couldn't finish" (never passed),
    and the late thread can't write proof (ctx.abandoned). Python can't stop a thread: the late call keeps going
    until its own timeout, but nobody waits for it."""
    import threading

    from app.models import Business, Plan

    own = Session(engine)
    wctx = Ctx(own, ctx.settings, ctx.integ, own.get(Plan, ctx.plan.id), own.get(Business, ctx.business.id),
               run_id=ctx.run_id, inbox_wait=ctx.inbox_wait)
    box: dict = {}

    def work():
        try:
            box["out"] = outcome_of(wctx, name)
        finally:
            own.close()

    t = threading.Thread(target=work, name=f"check-{name}-{ctx.business.id}", daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive() or "out" not in box:
        wctx.abandoned = True
        out = Outcome(name, False, WATCHDOG_TEXT, f"no answer within {seconds:.0f}s: stopped waiting", unfinished=True)
    else:
        out = box["out"]
        ctx.pending_inbox.extend(wctx.pending_inbox)
    save(ctx.session, ctx, out, 0)
    return out


def save(session: Session, ctx: Ctx, out: Outcome, attempt: int) -> None:
    session.add(CheckResult(business_id=ctx.business.id, plan_id=ctx.plan.id, run_id=ctx.run_id, check=out.check, passed=out.passed,
                            detail=json.dumps({"plain": out.plain, "detail": out.detail, "waiting": out.waiting,
                                               **({"unfinished": True} if out.unfinished else {})}),
                            attempt=attempt))
    if out.check.startswith("email_") and out.passed:
        evidence(ctx, out.check, "dns_answer", answer=out.detail[:200], server=dns_server(ctx),
                 source="authoritative nameserver")
    session.commit()
    audit.record(session, actor="checker", action=f"check_{out.check}", target=ctx.plan.site_host,
                 result="pass" if out.passed else "fail", business_id=ctx.business.id,
                 detail=f"attempt {attempt}: {out.detail}"[:500])


def run_all(ctx: Ctx) -> list[Outcome]:
    return [run_check(ctx, name) for name in checks_for(ctx)]
