"""Launch API: name ideas, plan (approval card), approve, step log, resume, practice "I bought it".

Every route needs the business's owner key (or admin). Practice businesses always
use the fake world (`for_business`). When a launch finishes, the launch checks run.
"""

import json
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.claude_client import Claude, ClaudeBudgetExceeded
from app.agents.executor import reset_for_resume, run_plan
from app.agents.namer import NamerError, find_names, namer_fixture
from app.agents.planner import PlanError, active_plan, build_plan, plan_out
from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.agents.launch_check import run_checks
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.models import Approval, Business, Plan, utcnow
from app.routers.businesses import get_claude
from app.safety.access import admin_flag, launches_today, owned_business, owned_plan, visitor_id
from app.sites.hosts import site_url

router = APIRouter(prefix="/api", tags=["launch"])
IntegFor = Callable[[Business], Integrations]


def integrations_for(server: Annotated[Integrations, Depends(get_integrations)],
                     practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> IntegFor:
    """FastAPI dependency: pick the fake world or the real one for a given business."""
    return lambda b: for_business(b, server, practice)


@router.get("/practice-mode")
def practice_mode(integ: Annotated[Integrations, Depends(get_integrations)],
                  admin: Annotated[bool, Depends(admin_flag)]) -> dict:
    """True when this visitor's shops run against the pretend GoDaddy (always, unless admin on a real server)."""
    return {"practice": integ.fake or not admin, "admin": admin}


@router.get("/businesses/{business_id}/names")
def name_ideas(b: Annotated[Business, Depends(owned_business)], session: Annotated[Session, Depends(get_session)],
               claude: Annotated[Claude, Depends(get_claude)],
               integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> list[dict]:
    integ = integ_for(b)
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


def card_out(plan: Plan, settings: Settings) -> dict:
    out = plan_out(plan)
    # Shown as its own line; the app doesn't buy it, so the spend guard doesn't cover it.
    out["email_plan_estimate_usd"] = settings.email_plan_estimate_usd if plan.mode == "full" else None
    return out


@router.post("/businesses/{business_id}/plans", status_code=201)
def create_plan(body: PlanRequest, b: Annotated[Business, Depends(owned_business)],
                settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    try:
        plan = build_plan(session, settings, integ_for(b), b, mode=body.mode, domain=body.domain)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail="Launching on your own name isn't switched on yet.") from e
    return card_out(plan, settings)


@router.get("/plans/{plan_id}")
def read_plan(plan: Annotated[Plan, Depends(owned_plan)], settings: Annotated[Settings, Depends(get_settings)],
              session: Annotated[Session, Depends(get_session)]) -> dict:
    out = card_out(plan, settings)
    b = session.get(Business, plan.business_id)
    out["practice"] = b.practice
    out["site_url"] = (f"https://{plan.site_host}/" if plan.mode == "full" and not b.practice
                       else site_url(b.subdomain, settings) if b and b.subdomain else None)
    out["approvals"] = [{"action": a.action, "target": a.target, "amount_usd": a.amount_usd,
                         "approved_by": a.approved_by, "used": a.used_at is not None}
                        for a in session.exec(select(Approval).where(Approval.plan_id == plan.id)).all()]
    return out


class ApproveRequest(BaseModel):
    approved_by: str = Field(default="owner", min_length=1, max_length=80)


def launch_then_check(engine: Engine, settings: Settings, integ: Integrations, claude: Claude, plan_id: int) -> str:
    """Run the plan; when it finishes, prove it works (checks + Doctor repairs)."""
    status = run_plan(engine, settings, integ, plan_id)
    if status == "done":
        run_checks(engine, settings, integ, claude, plan_id, trigger="launch")
    return status


def _start(background: BackgroundTasks, session: Session, settings: Settings, integ: Integrations, claude: Claude,
           plan: Plan) -> None:
    background.add_task(launch_then_check, session.get_bind(), settings, integ, claude, plan.id)


@router.post("/plans/{plan_id}/approve")
def approve_plan(body: ApproveRequest, request: Request, background: BackgroundTasks,
                 plan: Annotated[Plan, Depends(owned_plan)],
                 admin: Annotated[bool, Depends(admin_flag)],
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 claude: Annotated[Claude, Depends(get_claude)],
                 integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="This plan was already approved.")
    running = active_plan(session, plan.business_id)
    if running is not None:
        raise HTTPException(status_code=409, detail="Another launch is already running for this business.")
    visitor = visitor_id(request)
    if not admin and launches_today(session, visitor) >= settings.visitor_launches_per_day:
        raise HTTPException(status_code=429, detail="You've launched several shops today already. "
                            "Please come back tomorrow to launch another one.")
    b = session.get(Business, plan.business_id)
    integ = integ_for(b)

    if plan.mode == "full":
        # Re-check the price now: never approve a different amount than the card showed.
        if not integ.godaddy.is_owned(plan.zone):
            quote = integ.availability.check([plan.zone])[0]
            if not quote.available or quote.price_usd is None or float(quote.price_usd) > plan.total_cost_usd:
                raise HTTPException(status_code=409, detail="The price or availability changed. Please review the plan again.")
        clash = session.exec(select(Business).where(Business.domain == plan.zone, Business.id != b.id,
                                                    Business.practice == b.practice)).first()
        if clash is not None:
            raise HTTPException(status_code=409, detail="That name is already used by another business here.")
        b.domain = plan.zone  # from now on the domain is "in the app's database" for this business
        session.add(b)
        if plan.total_cost_usd > 0:
            session.add(Approval(business_id=b.id, plan_id=plan.id, action="buy_domain", target=plan.zone,
                                 amount_usd=plan.total_cost_usd, approved_by=body.approved_by))
    session.add(Approval(business_id=b.id, plan_id=plan.id, action="launch", target=plan.site_host,
                         amount_usd=plan.total_cost_usd, approved_by=body.approved_by))
    plan.status, plan.visitor, plan.approved_at = "approved", ("" if admin else visitor), utcnow()
    session.add(plan)
    session.commit()
    audit.record(session, actor="owner", action="approve_plan", target=plan.site_host, result="ok",
                 business_id=b.id, detail=f"plan #{plan.id}, ${plan.total_cost_usd:.2f}, by {body.approved_by}")
    _start(background, session, settings, integ, claude, plan)
    return {"ok": True, "plan_id": plan.id}


@router.post("/plans/{plan_id}/resume")
def resume_plan(background: BackgroundTasks, plan: Annotated[Plan, Depends(owned_plan)],
                settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                claude: Annotated[Claude, Depends(get_claude)],
                integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    if plan.status not in ("failed", "blocked"):
        raise HTTPException(status_code=409, detail="Only a stopped launch can be resumed.")
    reset_for_resume(session, plan)
    audit.record(session, actor="owner", action="resume_plan", target=plan.site_host, result="ok",
                 business_id=plan.business_id, detail=f"plan #{plan.id}")
    _start(background, session, settings, integ_for(session.get(Business, plan.business_id)), claude, plan)
    return {"ok": True, "plan_id": plan.id}


@router.post("/plans/{plan_id}/practice-buy")
def practice_buy(background: BackgroundTasks, plan: Annotated[Plan, Depends(owned_plan)],
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 claude: Annotated[Claude, Depends(get_claude)],
                 integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    """Practice mode only: pretend the owner bought the domain on godaddy.com, then resume.
    Touches nothing but the in-memory fake world; refused on real integrations."""
    b = session.get(Business, plan.business_id)
    integ = integ_for(b)
    if not integ.fake:
        raise HTTPException(status_code=409, detail="This is only available in practice mode. "
                            "Please buy the name on godaddy.com, then press Resume.")
    blocked = [s for s in json.loads(plan.steps_json) if s["kind"] == "get_domain" and s["status"] == "blocked"]
    if plan.mode != "full" or plan.status != "blocked" or not blocked:
        raise HTTPException(status_code=409, detail="This launch isn't waiting for a website name to be bought.")
    integ.godaddy.owned.add(plan.zone)
    audit.record(session, actor="owner", action="practice_buy", target=plan.zone, result="ok", business_id=b.id,
                 detail="practice mode: pretend purchase in the fake world (nothing bought, $0)")
    reset_for_resume(session, plan)
    _start(background, session, settings, integ, claude, plan)
    return {"ok": True, "plan_id": plan.id}


@router.get("/businesses/{business_id}/plans")
def list_plans(b: Annotated[Business, Depends(owned_business)], session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Plan).where(Plan.business_id == b.id).order_by(Plan.id.desc())).all()
    return [{"id": p.id, "mode": p.mode, "site_host": p.site_host, "status": p.status,
             "total_cost_usd": p.total_cost_usd, "steps": [s["status"] for s in json.loads(p.steps_json)]} for p in rows]
