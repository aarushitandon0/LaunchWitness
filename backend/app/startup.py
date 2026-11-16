"""Startup reconciler: launches and check runs are worked on by this process. If the server
restarts in the middle, nothing would ever finish them, and the screens would say "running"
forever. On start we close them honestly: the plan becomes failed with "press Resume", and a
stuck check run becomes done / not passed.
"""

import json

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.models import CheckRun, Plan, utcnow

RESTART_MESSAGE = "The server restarted during your launch. Nothing was lost: press Resume to continue."


def reconcile(engine: Engine) -> dict:
    """Returns how many rows were closed: {"plans": n, "check_runs": n}."""
    with Session(engine) as s:
        plans = s.exec(select(Plan).where(Plan.status.in_(("approved", "running")))).all()  # type: ignore[attr-defined]
        for plan in plans:
            steps = json.loads(plan.steps_json)
            hit = next((st for st in steps if st["status"] == "running"), None) or \
                next((st for st in steps if st["status"] == "pending"), None)
            if hit is not None:
                hit.update(status="failed", message=RESTART_MESSAGE, finished_at=utcnow().isoformat())
            plan.steps_json, plan.status = json.dumps(steps), "failed"
            s.add(plan)
            audit.record(s, actor="system", action="reconcile", target=f"plan:{plan.id}", result="failed",
                         business_id=plan.business_id, detail="server restarted while this launch was running")
        runs = s.exec(select(CheckRun).where(CheckRun.status == "running")).all()
        for run in runs:
            run.status, run.passed, run.finished_at = "done", False, utcnow()
            s.add(run)
            audit.record(s, actor="system", action="reconcile", target=f"run:{run.id}", result="failed",
                         business_id=run.business_id, detail="server restarted while these checks were running")
        s.commit()
        from app import outbox

        mail = outbox.reconcile(s)  # S13: email left "sending" by a crash goes back to the queue
        if mail:
            audit.record(s, actor="system", action="reconcile", target="outbox", result="requeued",
                         detail=f"{mail} email(s) were being sent when the server stopped")
        return {"plans": len(plans), "check_runs": len(runs), "outbox": mail}
