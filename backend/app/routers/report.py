"""Launch report, "Run checks now", and the admin-only demo fault switch."""

import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import audit, proof, renewals
from app.agents.checker import TITLES
from app.agents.claude_client import Claude
from app.agents.launch_check import (
    STAGED_FAULTS,
    AlreadyChecking,
    fault_allowed,
    latest_launched_plan,
    run_checks,
    start_run,
)
from app.config import Settings, get_settings
from app.db import get_session
from app.models import AuditEvent, Business, CheckResult, CheckRun, Plan
from app.monitor.scheduler import QUICK_MINUTES
from app.routers.businesses import get_claude
from app.routers.launch import IntegFor, integrations_for
from app.safety.access import ActorDep, owner_emails, require_admin, require_business_access
from app.sites.hosts import is_public, site_url

router = APIRouter(prefix="/api", tags=["report"])
OWNER_RUNS = ("launch", "manual")
AUDIT_LIMIT = 300


def iso(v: datetime | None) -> str | None:
    return v.replace(tzinfo=None).isoformat() + "Z" if v else None


def run_out(session: Session, run: CheckRun) -> dict:
    rows = session.exec(select(CheckResult).where(CheckResult.run_id == run.id).order_by(CheckResult.id)).all()
    checks: dict[str, dict] = {}
    for r in rows:  # later rows (re-checks after a repair) replace earlier ones
        d = json.loads(r.detail) if r.detail.startswith("{") else {"plain": r.detail, "detail": ""}
        first = checks.get(r.check, {}).get("first_passed", r.passed)
        waiting = bool(d.get("waiting"))
        checks[r.check] = {"check": r.check, "title": TITLES.get(r.check, r.check), "passed": r.passed,
                           "plain": d.get("plain", ""), "detail": d.get("detail", ""), "at": iso(r.created_at),
                           "attempt": r.attempt, "first_passed": first, "fixed": r.passed and not first,
                           "waiting": waiting, "doctor": checks.get(r.check, {}).get("doctor")}
        if r.doctor_json:  # the Doctor's finding + trace stay with the check through its re-checks
            checks[r.check]["doctor"] = json.loads(r.doctor_json)
    repairs = [{**rep, "title": TITLES.get(rep["check"], rep["check"])} for rep in json.loads(run.repairs_json)]
    return {"id": run.id, "trigger": run.trigger, "status": run.status, "passed": run.passed,
            "started_at": iso(run.started_at), "finished_at": iso(run.finished_at),
            "checks": list(checks.values()), "repairs": repairs, "info": json.loads(run.info_json)}


PRACTICE_PASSED = "Practice run: passed (pretend GoDaddy)"


def launch_out(plan: Plan | None) -> dict | None:
    """The launch steps, shown apart from the checks (a finished launch is not proof that it works)."""
    if plan is None:
        return None
    return {"status": plan.status, "steps": [{"title": s["title"], "status": s["status"], "message": s["message"],
                                              "finished_at": s["finished_at"]} for s in json.loads(plan.steps_json)]}


def headline(plan: Plan | None, latest_plan: Plan | None, run: dict | None,
             practice: bool = False) -> tuple[bool, str, list[str]]:
    if plan is None:
        if latest_plan is None:
            return False, "Your business isn't launched yet", ["Choose where your website lives and approve the launch."]
        if latest_plan.status in ("failed", "blocked"):
            msg = next((s["message"] for s in json.loads(latest_plan.steps_json) if s["status"] in ("failed", "blocked")),
                       "")
            return False, "Your launch stopped before the end", [msg or "Open the launch steps and press Resume."]
        return False, "Your launch is still running", ["We'll check everything as soon as it finishes."]
    if run is None or run["status"] == "running":
        return False, "Checking everything for you…", []
    left = [c["plain"] for c in run["checks"] if not c["passed"]]
    waiting = [c["plain"] for c in run["checks"] if c.get("state") == "needs_you"]
    if not left and run["passed"] and waiting:  # accepted is not delivered: only she can prove the last hop
        return False, "Almost ready: tell us the test order reached you", waiting
    if not left and run["passed"]:
        # Never an unlabelled "ready" from the pretend world.
        return True, PRACTICE_PASSED if practice else "Your business is ready for customers", []
    return False, "Almost there: a few things still need attention", left or ["We couldn't finish the checks."]


@router.get("/businesses/{business_id}/report")
def report(b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
           settings: Annotated[Settings, Depends(get_settings)],
           session: Annotated[Session, Depends(get_session)],
           integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    admin = actor.is_admin
    practice = b.practice or integ_for(b).fake  # results from the pretend world are always labelled
    plan = latest_launched_plan(session, b.id)
    latest_plan = session.exec(select(Plan).where(Plan.business_id == b.id, Plan.practice == b.practice)
                               .order_by(Plan.id.desc())).first()
    run_row = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.trigger.in_(OWNER_RUNS))
                           .order_by(CheckRun.id.desc())).first()
    run = run_out(session, run_row) if run_row and plan else None
    proven = proof.summary(session, run)  # adds each check's hops + state ("proven" / "needs_you" / "failed")
    ready, title, left = headline(plan, latest_plan, run, practice)

    def last(trigger: str) -> dict | None:
        r = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.trigger == trigger,
                                                CheckRun.status == "done").order_by(CheckRun.id.desc())).first()
        return {"at": iso(r.finished_at), "passed": r.passed} if r else None

    info_row = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.status == "done")
                            .order_by(CheckRun.id.desc())).first()
    info = json.loads(info_row.info_json) if info_row else {}
    events = session.exec(select(AuditEvent).where(AuditEvent.business_id == b.id)
                          .order_by(AuditEvent.id.desc()).limit(AUDIT_LIMIT)).all()
    # A practice launch's own name is pretend (maybe someone else's real site): link the practice address instead.
    site = (f"https://{plan.site_host}/" if plan and plan.mode == "full" and not b.practice
            else site_url(b.subdomain, settings) if b.subdomain else None)
    return {
        "business": {"id": b.id, "name": b.name, "site_url": site, "has_owner_email": bool(owner_emails(session, b.id)),
                     "practice": b.practice, "public": is_public(b) and not b.paused},
        "plan": {"id": plan.id, "mode": plan.mode, "site_host": plan.site_host, "mailbox": plan.mailbox}
        if plan else ({"id": latest_plan.id, "mode": latest_plan.mode, "site_host": latest_plan.site_host,
                       "mailbox": latest_plan.mailbox} if latest_plan else None),
        "practice": practice,
        "ready": ready, "headline": title, "left": left, "run": run, "proof": proven,
        "launch": launch_out(plan or latest_plan),
        "monitoring": {"enabled": settings.monitor_enabled, "every_minutes": QUICK_MINUTES,
                       "last_quick": last("monitor_quick"), "last_daily": last("monitor_daily"),
                       "cert_days_left": info.get("cert_days_left"), "domain_days_left": info.get("domain_days_left")},
        # Renewals (S10): only for a launched shop; dates from the pretend world are labelled by `practice`.
        "renewals": renewals.card(settings, plan.mode, plan.zone, info) if plan and b.status == "live" else None,
        "audit": [{"at": iso(e.created_at), "actor": e.actor, "action": e.action, "target": e.target,
                   "result": e.result, "detail": e.detail} for e in events],
        "admin": admin,
        "demo_fault": b.demo_fault if admin else None,
        "confirmed_by_you": confirmed_by_you(session, b),
    }


def confirmed_by_you(session: Session, b: Business) -> list[dict]:
    """The owner's own checks (S10.5), shown as their own lines labelled "confirmed by you". They are never
    counted as, or mixed with, the machine-proven hops above. No numbers or IDs here, only what and when."""
    from app import golive
    from app.agents.reader import Profile
    from app.models import Evidence

    p = Profile.model_validate_json(b.profile_json)
    got_it = session.exec(select(Evidence).where(Evidence.business_id == b.id, Evidence.step == "owner_confirmed")
                          .order_by(Evidence.id.desc())).first()
    return [
        {"what": "whatsapp", "label": "Your WhatsApp number opens your own chat",
         "at": iso(b.wa_confirmed_at) if golive.whatsapp_confirmed(b, p) else None},
        {"what": "upi", "label": "UPI name test: your UPI app showed the right name",
         "at": iso(b.upi_confirmed_at) if golive.upi_confirmed(b, p) else None},
        {"what": "got_it", "label": "“Yes, I got it”: the test order email reached you",
         "at": iso(got_it.at) if got_it else None},
    ]


@router.post("/businesses/{business_id}/checks", status_code=202)
def run_checks_now(background: BackgroundTasks, actor: ActorDep,
                   b: Annotated[Business, Depends(require_business_access)],
                   settings: Annotated[Settings, Depends(get_settings)],
                   session: Annotated[Session, Depends(get_session)],
                   claude: Annotated[Claude, Depends(get_claude)],
                   integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    plan = latest_launched_plan(session, b.id)
    if plan is None:
        raise HTTPException(status_code=409, detail="Your business isn't launched yet, so there's nothing to check.")
    try:
        run = start_run(session, b.id, plan.id, "manual")
    except AlreadyChecking:
        raise HTTPException(status_code=409, detail="We're already checking. This takes a few seconds.") from None
    audit.record(session, actor=actor.label, action="run_checks_now", target=plan.site_host, result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"run #{run.id}")
    background.add_task(run_checks, session.get_bind(), settings, integ_for(plan), claude, plan.id,
                        trigger="manual", run_id=run.id)
    return {"ok": True, "run_id": run.id}


class DemoFault(BaseModel):
    fault: Literal["", "dmarc", "mx", "a_record", "smtp_login", "cert"]


@router.put("/admin/businesses/{business_id}/demo-fault", dependencies=[Depends(require_admin)])
def set_demo_fault(business_id: int, body: DemoFault, session: Annotated[Session, Depends(get_session)],
                   settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    b = session.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that business.")
    plan = latest_launched_plan(session, b.id)
    if body.fault in STAGED_FAULTS:
        why = "This shop hasn't been launched yet." if plan is None else fault_allowed(session, settings, b, body.fault)
        if why:
            raise HTTPException(status_code=409, detail=why)
    elif body.fault and (plan is None or plan.mode != "full"):
        raise HTTPException(status_code=409, detail="The demo fault needs a practice launch on the shop's own name "
                            "(a shop's free address has no email settings of its own to break).")
    b.demo_fault = body.fault
    session.add(b)
    session.commit()
    audit.record(session, actor="admin", action="demo_fault_switch", target=body.fault or "off", result="ok",
                 business_id=b.id, detail="armed: removed before the next check" if body.fault else "disarmed")
    return {"ok": True, "demo_fault": b.demo_fault}


@router.delete("/admin/practice-businesses/{business_id}", dependencies=[Depends(require_admin)])
def delete_practice_business(business_id: int, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Demo reset (scripts/seed_demo.py --reset): remove a PRACTICE business and all its rows.
    Real businesses are never deleted this way."""
    from app.tenancy import delete_business_rows

    b = session.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that business.")
    if not b.practice:
        raise HTTPException(status_code=409, detail="Only practice businesses can be deleted here.")
    name = b.name
    delete_business_rows(session, b)
    session.commit()
    audit.record(session, actor="admin", action="delete_practice_business", target=f"business:{business_id}",
                 result="ok", detail=name)
    return {"ok": True}
