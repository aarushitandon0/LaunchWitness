"""Executor (code only): runs an APPROVED plan's steps in order.

Guards, checked on every DNS write (`write_change`):
1. a DnsBackup for this plan exists (taken by the backup step, before the first write);
2. the zone is in the app's database for THIS business: the seller's own
   `Business.domain`, or APP_DOMAIN but only for the business's own subdomain label;
3. writes are scoped to one (type, name), never a whole-zone replace.
Purchases go through the spend guard. Every step writes an AuditEvent. The step
log lives in `Plan.steps_json` (the UI polls it). A failed/blocked plan can be
resumed: finished steps are skipped.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.planner import DKIM_PENDING
from app.checks.dns_resolver import points_here
from app.config import Settings
from app.godaddy.client import PurchaseNotSupported
from app.integrations import Integrations
from app.mail.providers import mx_hosts, provider_for
from app.models import Approval, Business, DnsBackup, Plan, utcnow
from app.safety.spend_guard import PurchaseBlocked, authorize_purchase, mark_used

DNS_POLLS = 10
DNS_POLL_SECONDS = 30
MAILBOX_CREATE_TRIES = 3
MAILBOX_POLLS = 12
MAILBOX_POLL_SECONDS = 10


class StepFailed(Exception):
    """`message` is plain English for the seller; `detail` is technical."""

    status = "failed"

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message, self.detail = message, detail


class StepBlocked(StepFailed):
    status = "blocked"


class DomainRefused(StepFailed):
    status = "failed"


@dataclass
class Ctx:
    session: Session
    settings: Settings
    integ: Integrations
    plan: Plan
    business: Business
    run_id: int | None = None  # the CheckRun that check results belong to
    # S13 B: monitoring doesn't wait for the inbox (it looks again in a later short pass)
    inbox_wait: bool = True
    pending_inbox: list = field(default_factory=list)  # test orders to look for in that later pass
    abandoned: bool = False  # the watchdog stopped waiting for this check: it must not write proof any more

    @property
    def changes(self) -> list[dict]:
        return json.loads(self.plan.dns_json)


# ---------- guards ----------

def assert_can_write(ctx: Ctx, zone: str, name: str) -> None:
    """Refuse any DNS write outside this business's own domain/subdomain (re-read from DB)."""
    ctx.session.refresh(ctx.business)
    b, app_domain = ctx.business, ctx.settings.app_domain.lower()
    zone = zone.lower()
    ok = (
        zone == ctx.plan.zone.lower()
        and (
            (zone == app_domain and b.subdomain is not None and name == b.subdomain)
            or (zone != app_domain and b.domain is not None and zone == b.domain.lower())
        )
    )
    if not ok:
        audit.record(ctx.session, actor="executor", action="dns_write", target=f"{name} @ {zone}", result="refused",
                     business_id=b.id, detail="zone/name not owned by this business in the app database")
        raise DomainRefused(f"Stopped: this launch may only change settings for {ctx.plan.site_host}. Nothing was changed.",
                            f"refused write to {name} on {zone}")


def latest_backup(session: Session, plan: Plan) -> DnsBackup | None:
    return session.exec(select(DnsBackup).where(DnsBackup.plan_id == plan.id).order_by(DnsBackup.id.desc())).first()


OTHER_MAIL = ("This name already gets its email through another service, and it works. We left its email "
              "settings exactly as they are, so nothing was changed.")


def mail_write_decision(ctx: Ctx, ch: dict, records: list[dict]) -> str:
    """Read the LIVE zone before writing a mail setting. "write" | "keep" (theirs is fine, skip),
    or raise: working mail of another service is never replaced (by a launch or by the Doctor)."""
    if ch["type"] not in ("MX", "TXT"):
        return "write"
    live = [r for r in ctx.integ.godaddy.get_records(ch["zone"]) if r["type"] == ch["type"] and r["name"] == ch["name"]]
    if not live:
        return "write"
    provider = provider_for(ctx.settings)
    if ch["type"] == "MX":
        if mx_hosts(live) == mx_hosts(records):
            return "keep"
        if mx_hosts(live) <= {h for _p, h in provider.mx}:
            return "write"  # ours, but incomplete
        raise StepFailed(OTHER_MAIL, f"live MX {sorted(mx_hosts(live))} is not {provider.key}")
    if ch["name"] == "@":
        spf = [str(r.get("data", "")) for r in live if str(r.get("data", "")).lower().startswith("v=spf1")]
        if spf and not any(provider.spf_include in v for v in spf):
            raise StepFailed(OTHER_MAIL, f"live SPF {spf} does not include {provider.spf_include}")
        return "keep" if spf else "write"  # a line that already names us may also name her other senders: leave it
    return "keep" if {str(r.get("data", "")) for r in live} != {str(r.get("data", "")) for r in records} else "write"


def write_change(ctx: Ctx, ch: dict, after: list[dict] | None = None) -> None:
    assert_can_write(ctx, ch["zone"], ch["name"])
    if shared_address(ctx):
        audit.record(ctx.session, actor="executor", action="dns_write", target=f"{ch['type']} {ch['name']} @ {ch['zone']}",
                     result="refused", business_id=ctx.business.id, detail="DNS_MODE=wildcard: the app writes no DNS")
        raise StepFailed("This shop's address is looked after by our team, so we changed nothing.",
                         "DNS_MODE=wildcard: no DNS writes")
    if latest_backup(ctx.session, ctx.plan) is None:
        raise StepFailed("Stopped: we couldn't save a copy of your settings first, so nothing was changed.",
                         "no DnsBackup for this plan")
    records = after if after is not None else ch["after"]
    if mail_write_decision(ctx, ch, records) == "keep":
        audit.record(ctx.session, actor="executor", action="dns_write", target=f"{ch['type']} {ch['name']} @ {ch['zone']}",
                     result="kept", business_id=ctx.business.id, detail="a working value is already there; left as it is")
        return
    if ch["type"] == "TXT" and ch["name"] == "@":  # the write replaces every TXT there: carry over what is live now
        have = {str(r.get("data", "")) for r in records}
        records = [r for r in ctx.integ.godaddy.get_records(ch["zone"]) if r["type"] == "TXT" and r["name"] == "@"
                   and str(r.get("data", "")) not in have and not str(r.get("data", "")).lower().startswith("v=spf1")
                   ] + list(records)
    ctx.integ.godaddy.set_records(ch["zone"], ch["type"], ch["name"], records)
    audit.record(ctx.session, actor="executor", action="dns_write", target=f"{ch['type']} {ch['name']} @ {ch['zone']}",
                 result="ok", business_id=ctx.business.id, detail=json.dumps([r.get("data") for r in records])[:500])


def restore_change(ctx: Ctx, ch: dict) -> None:
    """Put one (type, name) back exactly as it was in the plan's backup (delete if it didn't exist)."""
    backup = latest_backup(ctx.session, ctx.plan)
    if backup is None:
        raise StepFailed("There's no saved copy to undo from.", "no DnsBackup")
    assert_can_write(ctx, ch["zone"], ch["name"])
    before = [r for r in json.loads(backup.records_json) if r["type"] == ch["type"] and r["name"] == ch["name"]]
    if before:
        ctx.integ.godaddy.set_records(ch["zone"], ch["type"], ch["name"], before)
    else:
        ctx.integ.godaddy.delete_records(ch["zone"], ch["type"], ch["name"])
    audit.record(ctx.session, actor="executor", action="dns_restore", target=f"{ch['type']} {ch['name']} @ {ch['zone']}",
                 result="ok", business_id=ctx.business.id, detail=f"from backup #{backup.id}")


# ---------- steps ----------

def shared_address(ctx: Ctx) -> bool:
    """DNS_MODE=wildcard and a shop on our own domain: its address already exists, so nothing is read or written."""
    return ctx.settings.dns_mode == "wildcard" and ctx.plan.zone.lower() == ctx.settings.app_domain.lower()


def step_backup_dns(ctx: Ctx) -> str:
    if shared_address(ctx):
        return "Nothing to save: this launch changes no settings."
    records = ctx.integ.godaddy.get_records(ctx.plan.zone)
    b = DnsBackup(business_id=ctx.business.id, plan_id=ctx.plan.id, domain=ctx.plan.zone,
                  records_json=json.dumps(records))
    ctx.session.add(b)
    ctx.session.commit()
    return f"Saved {len(records)} settings."


def step_point_site(ctx: Ctx) -> str:
    if shared_address(ctx):
        return "Your address already leads to our server."
    for ch in ctx.changes:
        if ch["type"] == "A":
            write_change(ctx, ch)
    return "Done."


def step_get_domain(ctx: Ctx) -> str:
    domain, cost = ctx.plan.zone, ctx.plan.total_cost_usd
    if ctx.integ.godaddy.is_owned(domain):
        return f"{domain} is in your GoDaddy account — using it."
    try:
        approval = authorize_purchase(ctx.session, ctx.settings, business_id=ctx.business.id, action="buy_domain",
                                      target=domain, cost_usd=cost, actor="executor")
    except PurchaseBlocked as e:
        raise StepBlocked(
            f"Stopped before buying {domain}. Buying is switched off on this server, so nothing was bought and "
            f"no settings were changed. You can buy {domain} on godaddy.com yourself, then press Resume — "
            "we'll use the domain you own.",
            e.reason,
        ) from e
    try:
        ctx.integ.godaddy.purchase_domain(domain, cost)
    except PurchaseNotSupported as e:
        raise StepBlocked(f"Please buy {domain} on godaddy.com, then press Resume.", str(e)) from e
    mark_used(ctx.session, approval)
    return f"Bought {domain}."


def step_use_app_mailbox(ctx: Ctx) -> str:
    address = ctx.plan.mailbox
    try:
        found = ctx.integ.mailbox.find(address)
    except NotImplementedError:
        # S17: the real GoDaddy mailbox client isn't built yet. The app's OWN inbox needs no provider lookup:
        # signing in to it proves it exists and works (nothing is sent).
        if address != ctx.settings.smtp_user or not hasattr(ctx.integ.mailer, "login_test"):
            raise
        result = ctx.integ.mailer.login_test()
        if not result.startswith("ok"):
            raise StepFailed("We couldn't open the LaunchWitness inbox, so we can't receive your orders yet.",
                             f"app mailbox {address}: {result}") from None
        return f"Orders will arrive at {address}."
    if found is None:
        raise StepFailed("The LaunchWitness inbox isn't set up yet, so we can't receive your orders.",
                         f"app mailbox {ctx.plan.mailbox} not found")
    return f"Orders will arrive at {ctx.plan.mailbox}."


def step_setup_mailbox(ctx: Ctx) -> str:
    """Create or adopt; retry creation on failure; poll until ready. Never undone."""
    mb, address, sleep = ctx.integ.mailbox, ctx.plan.mailbox, ctx.integ.sleep
    adopted = mb.find(address) is not None
    if not adopted:
        last = ""
        for attempt in range(1, MAILBOX_CREATE_TRIES + 1):
            try:
                mb.create(address)
                break
            except Exception as e:  # provider busy etc.: retry with backoff
                last = f"{type(e).__name__}: {e}"
                audit.record(ctx.session, actor="executor", action="mailbox_create", target=address, result="retry",
                             business_id=ctx.business.id, detail=f"attempt {attempt}: {last}"[:300])
                sleep(2**attempt)
        else:
            raise StepFailed("The email service is busy and couldn't create your mailbox. Press Resume to try again.",
                             last)
    for _ in range(MAILBOX_POLLS):
        if mb.status(address) == "ready":
            return f"{'Using' if adopted else 'Created'} {address}; it's ready."
        sleep(MAILBOX_POLL_SECONDS)
    raise StepFailed("Your mailbox is still being set up. This can take a few minutes — press Resume to keep waiting.",
                     f"{address} not ready after {MAILBOX_POLLS} polls")


def step_email_records(ctx: Ctx) -> str:
    for ch in ctx.changes:
        if ch["type"] == "A":
            continue
        after = ch["after"]
        if ch["deferred"] or any(r.get("data") == DKIM_PENDING for r in after):
            name, value = ctx.integ.mailbox.dkim(ctx.plan.zone)
            if name != ch["name"]:
                raise StepFailed("The email service gave an unexpected signing setting. Nothing more was changed.",
                                 f"DKIM name {name} != planned {ch['name']}")
            after = [{**r, "data": value} for r in after]
        write_change(ctx, ch, after)
    return "Email settings added."


def step_wait_dns(ctx: Ctx) -> str:
    host, want = ctx.plan.site_host, ctx.settings.server_ip
    for i in range(DNS_POLLS):
        # Every nameserver must agree before the shop is turned on: turning it on is what lets Caddy ask
        # Let's Encrypt for a certificate, and Let's Encrypt may ask any one of them (5 failures an hour at most).
        if points_here(ctx.integ.dns, host, want):
            return f"{host} now points to your website."
        if i < DNS_POLLS - 1:
            ctx.integ.sleep(DNS_POLL_SECONDS)
    raise StepFailed("The internet hasn't picked up the new address yet. This can take up to an hour — "
                     "press Resume to keep waiting.", f"A {host} != {want} after {DNS_POLLS} polls")


def step_go_live(ctx: Ctx) -> str:
    ctx.business.status = "live"
    ctx.session.add(ctx.business)
    ctx.session.commit()
    return f"Your website is on at {ctx.plan.site_host}."


STEPS: dict[str, Callable[[Ctx], str]] = {
    "backup_dns": step_backup_dns,
    "point_site": step_point_site,
    "get_domain": step_get_domain,
    "use_app_mailbox": step_use_app_mailbox,
    "setup_mailbox": step_setup_mailbox,
    "email_records": step_email_records,
    "wait_dns": step_wait_dns,
    "go_live": step_go_live,
}


# ---------- runner ----------

def has_launch_approval(session: Session, plan: Plan) -> bool:
    return session.exec(select(Approval).where(Approval.plan_id == plan.id, Approval.action == "launch")).first() is not None


def _save_steps(session: Session, plan: Plan, steps: list[dict]) -> None:
    plan.steps_json = json.dumps(steps)
    session.add(plan)
    session.commit()


def run_plan(engine: Engine, settings: Settings, integ: Integrations, plan_id: int) -> str:
    """Run (or resume) a plan. Returns the final plan status."""
    with Session(engine) as session:
        plan = session.get(Plan, plan_id)
        if plan is None:
            return "missing"
        business = session.get(Business, plan.business_id)
        if not has_launch_approval(session, plan):
            audit.record(session, actor="executor", action="run_plan", target=f"plan:{plan.id}", result="refused",
                         business_id=plan.business_id, detail="no owner approval")
            return plan.status
        ctx = Ctx(session, settings, integ, plan, business)
        plan.status = "running"
        steps = json.loads(plan.steps_json)
        _save_steps(session, plan, steps)
        audit.record(session, actor="executor", action="run_plan", target=f"plan:{plan.id}", result="started",
                     business_id=business.id)

        for st in steps:
            if st["status"] in ("done", "skipped"):
                continue
            st.update(status="running", message="", started_at=utcnow().isoformat(), finished_at=None)
            _save_steps(session, plan, steps)
            if integ.fake and settings.practice_step_seconds > 0:  # pretend world only: let the steps be seen
                import time

                time.sleep(min(settings.practice_step_seconds, 10))
            try:
                message = STEPS[st["kind"]](ctx)
            except StepFailed as e:
                st.update(status=e.status, message=e.message, finished_at=utcnow().isoformat())
                plan.status = e.status
                _save_steps(session, plan, steps)
                audit.record(session, actor="executor", action=f"step_{st['kind']}", target=plan.site_host,
                             result=e.status, business_id=business.id, detail=(e.detail or e.message)[:500])
                return plan.status
            except Exception as e:  # unexpected: stop safely, keep details for the log
                st.update(status="failed", finished_at=utcnow().isoformat(),
                          message="Something went wrong while talking to GoDaddy. We stopped here; press Resume to try again.")
                plan.status = "failed"
                _save_steps(session, plan, steps)
                audit.record(session, actor="executor", action=f"step_{st['kind']}", target=plan.site_host,
                             result="failed", business_id=business.id, detail=f"{type(e).__name__}: {e}"[:500])
                return plan.status
            st.update(status="done", message=message, finished_at=utcnow().isoformat())
            _save_steps(session, plan, steps)
            audit.record(session, actor="executor", action=f"step_{st['kind']}", target=plan.site_host, result="ok",
                         business_id=business.id, detail=message[:500])

        plan.status = "done"
        _save_steps(session, plan, steps)
        audit.record(session, actor="executor", action="run_plan", target=f"plan:{plan.id}", result="ok",
                     business_id=business.id)
        return plan.status


def reset_for_resume(session: Session, plan: Plan) -> None:
    steps = json.loads(plan.steps_json)
    for st in steps:
        if st["status"] in ("failed", "blocked", "running"):
            st.update(status="pending", message="")
    plan.status = "approved"
    _save_steps(session, plan, steps)

