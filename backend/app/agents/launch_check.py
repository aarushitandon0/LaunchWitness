"""One round of checks for a launched business (code): optional demo fault, the
checks, the Doctor on each failure (fixed playbook, max 3 attempts), days left
on the certificate and domain, and a CheckRun row the report reads.

Used after a launch finishes, by "Run checks now", and by monitoring.
"""

import json
import smtplib
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.checker import Outcome, checks_for, run_check
from app.agents.claude_client import Claude
from app.agents.doctor import repair
from app.agents.executor import Ctx, StepFailed, assert_can_write
from app.agents.playbook import fixes_for
from app.checks.http_probe import ProbeResult
from app.config import Settings
from app.integrations import Integrations
from app.models import Business, CheckRun, Plan, utcnow
from app.safety.access import run_by_team

DEMO_FAULTS = {"dmarc": ("TXT", "_dmarc"), "mx": ("MX", "@")}
STAGED_FAULTS = ("a_record", "smtp_login", "cert")  # S11: for the investigating Doctor


STALE_RUN = timedelta(minutes=15)  # a "running" row older than this lost its worker


class NotLaunched(Exception):
    pass


class AlreadyChecking(Exception):
    """A check run for this business is in progress: monitoring and "Run checks now" never overlap."""


@dataclass
class RunSummary:
    run_id: int
    passed: bool
    failed: list[Outcome]  # final failures after any repair


def latest_launched_plan(session: Session, business_id: int) -> Plan | None:
    """The finished launch that counts: for a real shop, never a practice plan."""
    b = session.get(Business, business_id)
    if b is None:
        return None
    return session.exec(select(Plan).where(Plan.business_id == business_id, Plan.status == "done",
                                           Plan.practice == b.practice).order_by(Plan.id.desc())).first()


def running_check(session: Session, business_id: int) -> CheckRun | None:
    return session.exec(select(CheckRun).where(CheckRun.business_id == business_id, CheckRun.status == "running")
                        .order_by(CheckRun.id.desc())).first()


def start_run(session: Session, business_id: int, plan_id: int, trigger: str) -> CheckRun:
    """The ONE way a check run starts (launch, "Run checks now", monitoring). Refuses while
    another run for the same business is in progress; a run stuck for 15 minutes is closed as failed."""
    current = running_check(session, business_id)
    if current is not None:
        started = current.started_at if current.started_at.tzinfo else current.started_at.replace(tzinfo=UTC)
        if utcnow() - started < STALE_RUN:
            raise AlreadyChecking(business_id)
        current.status, current.passed, current.finished_at = "done", False, utcnow()
        session.add(current)
        audit.record(session, actor="checker", action="check_run", target=f"run:{current.id}", result="failed",
                     business_id=business_id, detail="closed: no result after 15 minutes")
    run = CheckRun(business_id=business_id, plan_id=plan_id, trigger=trigger)
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


class RefusedMailer:
    """Staged fault: a mail service that refuses our sign-in. Used for ONE practice check run only."""

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> str:
        raise smtplib.SMTPAuthenticationError(535, b"staged fault: sign-in refused")

    def login_test(self) -> str:
        return "login refused: the mail service did not accept our sign-in"


class StagedCertProbe:
    """Staged fault: the shop's certificate isn't working until it is asked for again (`staged_heal`,
    called by the playbook's retry_certificate). Used for ONE practice check run only."""

    def __init__(self, inner, host: str):
        self.inner, self.host, self.broken = inner, host, True

    def staged_heal(self) -> None:
        self.broken = False

    def fetch(self, url: str) -> ProbeResult:
        if self.broken and (urlsplit(url).hostname or "") == self.host:
            return ProbeResult(False, None, False, error="certificate verify failed")
        return self.inner.fetch(url)

    def cert_expires(self, host: str):
        return None if self.broken and host == self.host else self.inner.cert_expires(host)


def fault_allowed(session: Session, settings: Settings, b: Business, fault: str) -> str:
    """"" when the team may stage `fault` on this shop, else the plain reason why not."""
    pretend = b.practice or settings.use_fakes
    if fault in ("smtp_login", "cert") and not pretend:
        return "This fault can only be staged on a practice shop (we never break a real shop's mail or padlock)."
    if fault == "a_record" and not pretend and not run_by_team(session, b.id):
        return "On the real internet this fault can only be staged on a shop the team runs itself."
    return ""


def stage_fault(ctx: Ctx, fault: str) -> str | None:
    """S11: three faults the investigating Doctor is shown on. Only ever on a practice shop, or (the address
    record only) on a shop the team runs. Each is audited as staged."""
    why = fault_allowed(ctx.session, ctx.settings, ctx.business, fault)
    if why:
        audit.record(ctx.session, actor="admin", action="demo_fault", target=fault, result="skipped",
                     business_id=ctx.business.id, detail=why[:300])
        return None
    if fault == "a_record":
        name = next((c["name"] for c in ctx.changes if c["type"] == "A"), None)
        if name is None:
            return None
        try:
            assert_can_write(ctx, ctx.plan.zone, name)
        except StepFailed:
            return None
        ctx.integ.godaddy.delete_records(ctx.plan.zone, "A", name)
        detail = f"A {name} @ {ctx.plan.zone} removed"
    elif fault == "smtp_login":
        ctx.integ = replace(ctx.integ, mailer=RefusedMailer())
        detail = "mail sign-in refused for this check run (pretend)"
    else:
        ctx.integ = replace(ctx.integ, http=StagedCertProbe(ctx.integ.http, ctx.plan.site_host))
        detail = "certificate not working until asked for again (pretend)"
    audit.record(ctx.session, actor="admin", action="demo_fault", target=fault, result="ok",
                 business_id=ctx.business.id, detail=f"staged fault for the demo: {detail}")
    return fault


def apply_demo_fault(ctx: Ctx) -> str | None:
    """Admin demo switch (SPEC §6 "the fault is staged"): delete DMARC (or MX) once, through the
    same scoped/guarded DNS path, so the next check fails and the Doctor repairs it."""
    fault = ctx.business.demo_fault
    if not fault:
        return None
    ctx.business.demo_fault = ""  # one-shot
    ctx.session.add(ctx.business)
    ctx.session.commit()
    if fault in STAGED_FAULTS:
        return stage_fault(ctx, fault)
    rtype, name = DEMO_FAULTS[fault]
    if ctx.plan.mode != "full":
        audit.record(ctx.session, actor="admin", action="demo_fault", target=fault, result="skipped",
                     business_id=ctx.business.id, detail="sandbox launches have no email settings")
        return None
    try:
        assert_can_write(ctx, ctx.plan.zone, name)
    except StepFailed:
        return None
    ctx.integ.godaddy.delete_records(ctx.plan.zone, rtype, name)
    audit.record(ctx.session, actor="admin", action="demo_fault", target=f"{rtype} {name} @ {ctx.plan.zone}",
                 result="ok", business_id=ctx.business.id, detail="staged fault for the demo: setting removed")
    return fault


def needs_a_look(out: Outcome) -> bool:
    """A failure with no automatic fix that the Doctor should still investigate, so the owner gets a finding and
    an exact next step: the order email couldn't be sent (our mail service refused or was unreachable)."""
    return out.check == "test_order" and "mail server refused" in out.detail


def days_left(when: datetime | None) -> int | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - datetime.now(UTC)).days


def expiry_info(ctx: Ctx) -> dict:
    info: dict = {"cert_days_left": None, "domain_days_left": None, "app_domain_days_left": None}
    try:
        info["cert_days_left"] = days_left(ctx.integ.http.cert_expires(ctx.plan.site_host))
        if ctx.plan.mode == "full":  # the seller's own name: the seller renews (and pays)
            info["domain_days_left"] = days_left(ctx.integ.godaddy.domain_expires(ctx.plan.zone))
        else:  # sandbox addresses live under the app's own domain: the team renews it (Renewals card)
            info["app_domain_days_left"] = days_left(ctx.integ.godaddy.domain_expires(ctx.settings.app_domain))
    except Exception as e:  # informational only; never breaks a check run
        info["error"] = type(e).__name__
    return info


def run_checks(engine: Engine, settings: Settings, integ: Integrations, claude: Claude, plan_id: int, *,
               trigger: str, names: list[str] | None = None, fix: bool = True, run_id: int | None = None,
               symptom: str = "") -> RunSummary:
    """`symptom`: the owner's own words about what's wrong (optional). Data for the Doctor, never instructions."""
    with Session(engine) as session:
        plan = session.get(Plan, plan_id)
        business = session.get(Business, plan.business_id)
        if plan.status != "done":
            raise NotLaunched(plan_id)
        run = session.get(CheckRun, run_id) if run_id else None
        if run is None:
            run = start_run(session, business.id, plan.id, trigger)  # raises AlreadyChecking
        ctx = Ctx(session, settings, integ, plan, business, run_id=run.id)
        outs: list[Outcome] = []
        try:
            apply_demo_fault(ctx)
            repairs, failed = [], []
            for name in names or checks_for(ctx):  # check, and repair right away, so later checks see the fix
                out = run_check(ctx, name)
                outs.append(out)
                if out.passed:
                    continue
                if fix and (fixes_for(out.check, plan.mode) or needs_a_look(out)):
                    r = repair(claude, ctx, out, symptom)
                    repairs.append({"check": r.check, "fixed": r.fixed, "attempts": r.attempts,
                                    **({"doctor": r.doctor} if r.doctor else {})})
                    if r.fixed:
                        continue
                    out = r.final or out
                failed.append(out)
            info = expiry_info(ctx)
        except Exception as e:  # keep the run row consistent; report shows it as not passed
            audit.record(session, actor="checker", action="check_run", target=f"run:{run.id}", result="failed",
                         business_id=business.id, detail=f"{type(e).__name__}: {e}"[:300])
            failed, repairs, info = [Outcome("check_run", False, "We couldn't finish the checks.", str(e))], [], {}
        run.status, run.passed, run.finished_at = "done", not failed, utcnow()
        run.repairs_json, run.info_json = json.dumps(repairs), json.dumps(info)
        session.add(run)
        session.commit()
        audit.record(session, actor="checker", action="check_run", target=f"run:{run.id}",
                     result="pass" if not failed else "fail", business_id=business.id,
                     detail=f"{trigger}: {len(outs)} checks, "
                            f"{len(repairs)} repaired/attempted, failing: {[f.check for f in failed]}")
        return RunSummary(run.id, not failed, failed)
