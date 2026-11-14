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
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.planner import DKIM_PENDING
from app.config import Settings
from app.godaddy.client import PurchaseNotSupported
from app.integrations import Integrations
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


def write_change(ctx: Ctx, ch: dict, after: list[dict] | None = None) -> None:
    assert_can_write(ctx, ch["zone"], ch["name"])
    if latest_backup(ctx.session, ctx.plan) is None:
        raise StepFailed("Stopped: we couldn't save a copy of your settings first, so nothing was changed.",
                         "no DnsBackup for this plan")
    records = after if after is not None else ch["after"]
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

def step_backup_dns(ctx: Ctx) -> str:
    records = ctx.integ.godaddy.get_records(ctx.plan.zone)
    b = DnsBackup(business_id=ctx.business.id, plan_id=ctx.plan.id, domain=ctx.plan.zone,
                  records_json=json.dumps(records))
    ctx.session.add(b)
    ctx.session.commit()
    return f"Saved {len(records)} settings."


def step_point_site(ctx: Ctx) -> str:
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
    if ctx.integ.mailbox.find(ctx.plan.mailbox) is None:
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
        if want in ctx.integ.dns.resolve(host, "A"):
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

