"""Launch API: name ideas, plan (approval card), approve, step log, resume, practice "I bought it".

Every route needs the business's owner key (or admin). Practice businesses always
use the fake world (`for_business`). When a launch finishes, the launch checks run.
"""

import json
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app import audit
from app.agents.claude_client import FALLBACK_NAMES_NOTE, Claude, ClaudeBudgetExceeded
from app.agents.executor import reset_for_resume, run_plan
from app.agents.launch_check import AlreadyChecking, run_checks
from app.agents.namer import NamerError, find_names, namer_fixture
from app.agents.planner import PlanError, active_plan, build_plan, plan_out
from app.agents.policy import policy_check
from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.models import Approval, Business, Plan, utcnow
from app.routers.businesses import get_claude
from app.safety.access import ActorDep, launches_today, require_business_access, require_plan_access, visitor_id
from app.sites.hosts import is_public, site_url

router = APIRouter(prefix="/api", tags=["launch"])
IntegFor = Callable[[Business | Plan], Integrations]  # chosen by the object's own `practice` flag


def integrations_for(server: Annotated[Integrations, Depends(get_integrations)],
                     practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> IntegFor:
    """FastAPI dependency: pick the fake world or the real one for a given business."""
    return lambda b: for_business(b, server, practice)


NOT_APPROVED = ("Your account is waiting for approval, so you can practise for now. "
                "We'll email you as soon as you can launch for real.")
SUBDOMAINS_ONLY = "Shops live at an address under ours for now. Using your own domain comes later."


def live_shops(session: Session) -> int:
    return session.exec(select(func.count()).select_from(Business).where(
        Business.status == "live", Business.practice == False)).one()  # noqa: E712


@router.get("/businesses/{business_id}/names")
def name_ideas(response: Response, b: Annotated[Business, Depends(require_business_access)],
               session: Annotated[Session, Depends(get_session)],
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
    if getattr(claude, "fell_back", False):
        response.headers["X-Assistant-Note"] = FALLBACK_NAMES_NOTE
        audit.record(session, actor="namer", action="claude_fallback", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail="live Claude unavailable or daily cap reached; used saved sample names")
    return [{"domain": q.domain, "price_usd": q.price_usd} for q in quotes]


class PlanRequest(BaseModel):
    mode: Literal["sandbox", "full"]
    domain: str | None = Field(default=None, max_length=63)
    real: bool = False  # false = practice (pretend GoDaddy). true = a real launch: approved accounts only.


def card_out(plan: Plan, settings: Settings) -> dict:
    out = plan_out(plan)
    # Shown as its own line; the app doesn't buy it, so the spend guard doesn't cover it.
    out["email_plan_estimate_usd"] = settings.email_plan_estimate_usd if plan.mode == "full" else None
    return out


@router.post("/businesses/{business_id}/plans", status_code=201)
def create_plan(body: PlanRequest, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                server: Annotated[Integrations, Depends(get_integrations)],
                practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> dict:
    if body.real:
        if not actor.approved or b.guest_hash:
            raise HTTPException(status_code=403, detail=NOT_APPROVED if actor.user else "Please sign in to launch for real.")
        if body.mode != "sandbox":
            raise HTTPException(status_code=422, detail=SUBDOMAINS_ONLY)
    elif not b.practice:
        raise HTTPException(status_code=409, detail="This shop is real now, so it can't be launched in practice mode.")
    try:
        plan = build_plan(session, settings, practice if not body.real else server, b, mode=body.mode,
                          domain=body.domain, practice=not body.real)
    except PlanError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail="Launching on your own name isn't switched on yet.") from e
    return card_out(plan, settings)


@router.get("/plans/{plan_id}")
def read_plan(plan: Annotated[Plan, Depends(require_plan_access)], settings: Annotated[Settings, Depends(get_settings)],
              session: Annotated[Session, Depends(get_session)]) -> dict:
    out = card_out(plan, settings)
    b = session.get(Business, plan.business_id)
    out["practice"] = plan.practice
    out["public"] = is_public(b) and not b.paused
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
        try:
            run_checks(engine, settings, integ, claude, plan_id, trigger="launch")
        except AlreadyChecking:  # a check for this shop is already running; its result is the proof
            pass
    return status


def _start(background: BackgroundTasks, session: Session, settings: Settings, integ: Integrations, claude: Claude,
           plan: Plan) -> None:
    background.add_task(launch_then_check, session.get_bind(), settings, integ, claude, plan.id)


@router.post("/plans/{plan_id}/approve")
def approve_plan(body: ApproveRequest, request: Request, background: BackgroundTasks,
                 plan: Annotated[Plan, Depends(require_plan_access)],
                 actor: ActorDep,
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 claude: Annotated[Claude, Depends(get_claude)],
                 integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    if plan.status != "draft":
        raise HTTPException(status_code=409, detail="This plan was already approved.")
    running = active_plan(session, plan.business_id)
    if running is not None:
        raise HTTPException(status_code=409, detail="Another launch is already running for this business.")
    visitor, admin = visitor_id(request), actor.is_admin
    if not admin and launches_today(session, visitor) >= settings.visitor_launches_per_day:
        raise HTTPException(status_code=429, detail="You've launched several shops today already. "
                            "Please come back tomorrow to launch another one.")
    b = session.get(Business, plan.business_id)
    integ = integ_for(plan)

    if not plan.practice:
        # A real launch puts a shop on the public internet under our name. Checked again here, at the
        # moment of approval: the account, the certificate budget, and the go-live policy check.
        if not actor.approved or b.guest_hash or plan.mode != "sandbox":
            raise HTTPException(status_code=403, detail=NOT_APPROVED)
        if not (b.status == "live" and not b.practice) and live_shops(session) >= settings.max_live_shops:
            raise HTTPException(status_code=409, detail="We've reached the number of live shops we can host this week. "
                                "Nothing was changed. Please try again in a few days.")
        if b.paused:
            raise HTTPException(status_code=409, detail="This shop is paused by our team, so it can't be launched right now.")
        if b.review != "cleared":  # "cleared" = the team already looked
            verdict = policy_check(claude, Profile.model_validate_json(b.profile_json))
            b.review, b.review_reason = ("ok", "") if verdict.ok else ("held", verdict.reason)
            session.add(b)
            session.commit()
            audit.record(session, actor="policy", action="policy_check", target=f"business:{b.id}",
                         result="ok" if verdict.ok else "held", business_id=b.id, user_id=actor.user_id,
                         detail=f"by {verdict.by}: {verdict.reason}"[:300])
            if not verdict.ok:
                raise HTTPException(status_code=409, detail=f"{verdict.reason} Nothing was launched. "
                                    "We'll email you when our team has looked at it.")
        if b.practice:  # from here on the shop is real: old practice results no longer count
            b.practice, b.status = False, "draft"
            session.add(b)
            session.commit()

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
                 business_id=b.id, user_id=actor.user_id,
                 detail=f"plan #{plan.id}, {'practice' if plan.practice else 'REAL'}, ${plan.total_cost_usd:.2f}, by {body.approved_by}")
    _start(background, session, settings, integ, claude, plan)
    return {"ok": True, "plan_id": plan.id}


@router.post("/plans/{plan_id}/resume")
def resume_plan(background: BackgroundTasks, plan: Annotated[Plan, Depends(require_plan_access)],
                settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                claude: Annotated[Claude, Depends(get_claude)],
                integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    if plan.status not in ("failed", "blocked"):
        raise HTTPException(status_code=409, detail="Only a stopped launch can be resumed.")
    reset_for_resume(session, plan)
    audit.record(session, actor="owner", action="resume_plan", target=plan.site_host, result="ok",
                 business_id=plan.business_id, detail=f"plan #{plan.id}")
    _start(background, session, settings, integ_for(plan), claude, plan)
    return {"ok": True, "plan_id": plan.id}


@router.post("/plans/{plan_id}/practice-buy")
def practice_buy(background: BackgroundTasks, plan: Annotated[Plan, Depends(require_plan_access)],
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 claude: Annotated[Claude, Depends(get_claude)],
                 integ_for: Annotated[IntegFor, Depends(integrations_for)]) -> dict:
    """Practice mode only: pretend the owner bought the domain on godaddy.com, then resume.
    Touches nothing but the in-memory fake world; refused on real integrations."""
    b = session.get(Business, plan.business_id)
    integ = integ_for(plan)
    if not integ.fake or not plan.practice:
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
def list_plans(b: Annotated[Business, Depends(require_business_access)], session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Plan).where(Plan.business_id == b.id).order_by(Plan.id.desc())).all()
    return [{"id": p.id, "mode": p.mode, "practice": p.practice, "site_host": p.site_host, "status": p.status,
             "total_cost_usd": p.total_cost_usd, "steps": [s["status"] for s in json.loads(p.steps_json)]} for p in rows]
