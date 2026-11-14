"""Launch API: name ideas, plan (approval card), approve, step log, resume."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import audit
from app.agents.claude_client import Claude, ClaudeBudgetExceeded
from app.agents.executor import reset_for_resume, run_plan
from app.agents.namer import NamerError, find_names, namer_fixture
from app.agents.planner import PlanError, active_plan, build_plan, plan_out
from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, get_integrations
from app.models import Approval, Business, Plan
from app.routers.businesses import get_business, get_claude
from app.sites.hosts import site_url

router = APIRouter(prefix="/api", tags=["launch"])


def get_plan(session: Session, plan_id: int) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="We couldn't find that launch plan.")
    return plan


@router.get("/practice-mode")
def practice_mode(integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    return {"practice": integ.fake}


@router.get("/businesses/{business_id}/names")
def name_ideas(business_id: int, session: Annotated[Session, Depends(get_session)],
               claude: Annotated[Claude, Depends(get_claude)],
               integ: Annotated[Integrations, Depends(get_integrations)]) -> list[dict]:
    b = get_business(session, business_id)
    profile = Profile.model_validate_json(b.profile_json)
    try:
        quotes = find_names(claude, integ.availability, profile, fixture=namer_fixture(b.description))
    except NamerError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ClaudeBudgetExceeded as e:
        raise HTTPException(status_code=503, detail="Our assistant has reached today's limit. Please try again tomorrow.") from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail="Checking real website names isn't switched on yet. "
                            "You can launch on the free address for now.") from e
    audit.record(session, actor="namer", action="name_ideas", target=f"business:{b.id}", result="ok",
                 business_id=b.id, detail=", ".join(q.domain for q in quotes))
    return [{"domain": q.domain, "price_usd": q.price_usd} for q in quotes]


class PlanRequest(BaseModel):
    mode: Literal["sandbox", "full"]
    domain: str | None = Field(default=None, max_length=63)


@router.post("/businesses/{business_id}/plans", status_code=201)
def create_plan(business_id: int, body: PlanRequest, settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    b = get_business(session, business_id)
    try:
        plan = build_plan(session, settings, integ, b, mode=body.mode, domain=body.domain)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail="Launching on your own name isn't switched on yet.") from e
    return plan_out(plan)


@router.get("/plans/{plan_id}")
def read_plan(plan_id: int, settings: Annotated[Settings, Depends(get_settings)],
              session: Annotated[Session, Depends(get_session)]) -> dict:
    plan = get_plan(session, plan_id)
    out = plan_out(plan)
    b = session.get(Business, plan.business_id)
    out["site_url"] = (f"https://{plan.site_host}/" if plan.mode == "full"
                       else site_url(b.subdomain, settings) if b and b.subdomain else None)
    out["approvals"] = [{"action": a.action, "target": a.target, "amount_usd": a.amount_usd,
                         "approved_by": a.approved_by, "used": a.used_at is not None}
                        for a in session.exec(select(Approval).where(Approval.plan_id == plan.id)).all()]
    return out


class ApproveRequest(BaseModel):
    approved_by: str = Field(default="owner", min_length=1, max_length=80)


def _start(background: BackgroundTasks, session: Session, settings: Settings, integ: Integrations, plan: Plan) -> None:
    background.add_task(run_plan, session.get_bind(), settings, integ, plan.id)


@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: int, body: ApproveRequest, background: BackgroundTasks,
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    plan = get_plan(session, plan_id)
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="This plan was already approved.")
    running = active_plan(session, plan.business_id)
    if running is not None:
        raise HTTPException(status_code=409, detail="Another launch is already running for this business.")
    b = session.get(Business, plan.business_id)

    if plan.mode == "full":
        # Re-check the price now: never approve a different amount than the card showed.
        if not integ.godaddy.is_owned(plan.zone):
            quote = integ.availability.check([plan.zone])[0]
            if not quote.available or quote.price_usd is None or float(quote.price_usd) > plan.total_cost_usd:
                raise HTTPException(status_code=409, detail="The price or availability changed. Please review the plan again.")
        clash = session.exec(select(Business).where(Business.domain == plan.zone, Business.id != b.id)).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail="That name is already used by another business here.")
        b.domain = plan.zone  # from now on the domain is "in the app's database" for this business
        session.add(b)
        if plan.total_cost_usd > 0:
            session.add(Approval(business_id=b.id, plan_id=plan.id, action="buy_domain", target=plan.zone,
                                 amount_usd=plan.total_cost_usd, approved_by=body.approved_by))
    session.add(Approval(business_id=b.id, plan_id=plan.id, action="launch", target=plan.site_host,
                         amount_usd=plan.total_cost_usd, approved_by=body.approved_by))
    plan.status = "approved"
    session.add(plan)
    session.commit()
    audit.record(session, actor="owner", action="approve_plan", target=plan.site_host, result="ok",
                 business_id=b.id, detail=f"plan #{plan.id}, ${plan.total_cost_usd:.2f}, by {body.approved_by}")
    _start(background, session, settings, integ, plan)
    return {"ok": True, "plan_id": plan.id}


@router.post("/plans/{plan_id}/resume")
def resume_plan(plan_id: int, background: BackgroundTasks, settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    plan = get_plan(session, plan_id)
    if plan.status not in ("failed", "blocked"):
        raise HTTPException(status_code=409, detail="Only a stopped launch can be resumed.")
    reset_for_resume(session, plan)
    audit.record(session, actor="owner", action="resume_plan", target=plan.site_host, result="ok",
                 business_id=plan.business_id, detail=f"plan #{plan.id}")
    _start(background, session, settings, integ, plan)
    return {"ok": True, "plan_id": plan.id}


@router.get("/businesses/{business_id}/plans")
def list_plans(business_id: int, session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    get_business(session, business_id)
    rows = session.exec(select(Plan).where(Plan.business_id == business_id).order_by(Plan.id.desc())).all()
    return [{"id": p.id, "mode": p.mode, "site_host": p.site_host, "status": p.status,
             "total_cost_usd": p.total_cost_usd, "steps": [s["status"] for s in json.loads(p.steps_json)]} for p in rows]
