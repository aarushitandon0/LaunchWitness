"""One round of checks for a launched business (code): optional demo fault, the
checks, the Doctor on each failure (fixed playbook, max 3 attempts), days left
on the certificate and domain, and a CheckRun row the report reads.

Used after a launch finishes, by "Run checks now", and by monitoring.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.checker import Outcome, checks_for, run_check
from app.agents.claude_client import Claude
from app.agents.doctor import repair
from app.agents.executor import Ctx, StepFailed, assert_can_write
from app.agents.playbook import FIXES_FOR
from app.config import Settings
from app.integrations import Integrations
from app.models import Business, CheckRun, Plan, utcnow

DEMO_FAULTS = {"dmarc": ("TXT", "_dmarc"), "mx": ("MX", "@")}


class NotLaunched(Exception):
    pass


@dataclass
class RunSummary:
    run_id: int
    passed: bool
    failed: list[Outcome]  # final failures after any repair


def latest_launched_plan(session: Session, business_id: int) -> Plan | None:
    return session.exec(select(Plan).where(Plan.business_id == business_id, Plan.status == "done")
                        .order_by(Plan.id.desc())).first()


def running_check(session: Session, business_id: int) -> CheckRun | None:
    return session.exec(select(CheckRun).where(CheckRun.business_id == business_id, CheckRun.status == "running")
                        .order_by(CheckRun.id.desc())).first()


def apply_demo_fault(ctx: Ctx) -> str | None:
    """Admin demo switch (SPEC §6 "the fault is staged"): delete DMARC (or MX) once, through the
    same scoped/guarded DNS path, so the next check fails and the Doctor repairs it."""
    fault = ctx.business.demo_fault
    if not fault:
        return None
    ctx.business.demo_fault = ""  # one-shot
    ctx.session.add(ctx.business)
    ctx.session.commit()
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


def days_left(when: datetime | None) -> int | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return (when - datetime.now(UTC)).days


def expiry_info(ctx: Ctx) -> dict:
    info: dict = {"cert_days_left": None, "domain_days_left": None}
    try:
        info["cert_days_left"] = days_left(ctx.integ.http.cert_expires(ctx.plan.site_host))
        if ctx.plan.mode == "full":  # sandbox addresses live under the app's own domain
            info["domain_days_left"] = days_left(ctx.integ.godaddy.domain_expires(ctx.plan.zone))
    except Exception as e:  # informational only; never breaks a check run
        info["error"] = type(e).__name__
    return info


def run_checks(engine: Engine, settings: Settings, integ: Integrations, claude: Claude, plan_id: int, *,
               trigger: str, names: list[str] | None = None, fix: bool = True, run_id: int | None = None) -> RunSummary:
    with Session(engine) as session:
        plan = session.get(Plan, plan_id)
        business = session.get(Business, plan.business_id)
        if plan.status != "done":
            raise NotLaunched(plan_id)
        run = session.get(CheckRun, run_id) if run_id else None
        if run is None:
            run = CheckRun(business_id=business.id, plan_id=plan.id, trigger=trigger)
            session.add(run)
            session.commit()
            session.refresh(run)
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
                if fix and FIXES_FOR.get(out.check):
                    r = repair(claude, ctx, out)
                    repairs.append({"check": r.check, "fixed": r.fixed, "attempts": r.attempts})
                    if r.fixed:
                        continue
                    out = r.final or out
                failed.append(out)
            info = expiry_info(ctx)
        except Exception as e:  # keep the run row consistent; report shows it as not passed
            audit.record(session, actor="checker", action="check_run", target=f"run:{run.id}", result="failed",
                         business_id=business.id, detail=f"{type(e).__name__}: {e}"[:300])
            failed, repairs, info = [Outcome("launch_clean", False, "We couldn't finish the checks.", str(e))], [], {}
        run.status, run.passed, run.finished_at = "done", not failed, utcnow()
        run.repairs_json, run.info_json = json.dumps(repairs), json.dumps(info)
        session.add(run)
        session.commit()
        audit.record(session, actor="checker", action="check_run", target=f"run:{run.id}",
                     result="pass" if not failed else "fail", business_id=business.id,
                     detail=f"{trigger}: {len(outs)} checks, "
                            f"{len(repairs)} repaired/attempted, failing: {[f.check for f in failed]}")
        return RunSummary(run.id, not failed, failed)
