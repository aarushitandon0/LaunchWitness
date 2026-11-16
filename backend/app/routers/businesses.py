"""Seller-facing API: read a business description, review/edit the profile, list orders."""

import json
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app import accounts, audit
from app.agents.claude_client import FALLBACK_NOTE, Claude, ClaudeBudgetExceeded, make_claude_client
from app.agents.reader import MAX_IMAGE_BYTES, Profile, ReaderError, read_business
from app.config import Settings, get_settings
from app.db import get_engine, get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.models import Business, Membership, Order, Plan
from app.safety.access import (
    ActorDep,
    csrf_for,
    describes_today,
    owner_emails,
    require_business_access,
    sha,
    user_describes_today,
    visitor_id,
)
from app.sites.hosts import is_public, site_url, slug_problem
from app.sites.render import render_site
from app.tenancy import purge_business

router = APIRouter(prefix="/api", tags=["businesses"])
SELLERS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sellers"


def get_claude(settings: Annotated[Settings, Depends(get_settings)]) -> Claude:
    """FastAPI dependency. Tests override this."""
    return make_claude_client(settings, get_engine() if settings.claude_mode == "live" else None)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")
    s = s[:30].strip("-")
    return s if len(s) >= 3 else "shop"


def unique_subdomain(session: Session, base: str) -> str:
    if slug_problem(base) is not None:  # reserved or brand-like: start from a neutral name
        base = "shop"
    candidate, n = base, 2
    while slug_problem(candidate) is not None or session.exec(select(Business.id).where(Business.subdomain == candidate)).first():
        candidate, n = f"{base[:26]}-{n}", n + 1
    return candidate


def latest_plan(session: Session | None, b: Business) -> dict | None:
    """The shop's newest launch plan, so the app can resume the 5-step flow at the right step."""
    if session is None:
        return None
    p = session.exec(select(Plan).where(Plan.business_id == b.id).order_by(Plan.id.desc())).first()
    return {"id": p.id, "status": p.status, "practice": p.practice} if p else None


def business_out(b: Business, settings: Settings, session: Session | None = None) -> dict:
    owners = owner_emails(session, b.id) if session is not None else []
    return {
        "latest_plan": latest_plan(session, b),
        "name": b.name,
        "guest": bool(b.guest_hash),  # made without signing in: practice only, kept for 24 hours
        "paused": b.paused,
        "review": b.review,
        "review_reason": b.review_reason,
        "id": b.id,
        "subdomain": b.subdomain,
        "site_url": site_url(b.subdomain, settings) if b.subdomain else None,
        "status": b.status,
        "practice": b.practice,
        "public": is_public(b) and not b.paused,  # false = only the owner sees it, through the preview
        "owner_email": owners[0] if owners else "",  # the sign-in address orders and alerts go to
        "profile": json.loads(b.profile_json),
    }


NOT_SUPPORTED_DEFAULT = ("Your customers book a time with you, and for now we can only build shops that take orders, "
                         "so we can't make your website yet.")

@router.get("/samples")
def samples() -> list[dict]:
    """The three sample seller inputs, so the 'Try an example' buttons can fill the form."""
    out = []
    for path in sorted(SELLERS.glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        out.append({"id": d["id"], "owner_name": d["owner_name"], "city": d["city"],
                    "description": d["description"], "price_list": d["price_list"]})
    return out


@router.post("/businesses", status_code=201)
async def create_business(
    request: Request,
    response: Response,
    actor: ActorDep,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    claude: Annotated[Claude, Depends(get_claude)],
    description: Annotated[str, Form(max_length=4000)] = "",
    price_list: Annotated[str, Form(max_length=4000)] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> dict:
    visitor = visitor_id(request)
    admin, user = actor.is_admin, actor.user
    if user is not None and not admin:
        if accounts.shops_of(session, user.id) >= settings.max_shops_per_user:
            raise HTTPException(status_code=409, detail=f"You already have {settings.max_shops_per_user} shops, which is "
                                "the most one account can have. Delete one you don't need to make another.")
        if user_describes_today(session, user.id) >= settings.user_describes_per_day:
            raise HTTPException(status_code=429, detail="You've described several shops today already. "
                                "Please come back tomorrow to try another one.")
    elif not admin and describes_today(session, visitor) >= settings.visitor_describes_per_day:
        raise HTTPException(status_code=429, detail="You've set up several shops today already. "
                            "Please come back tomorrow to try another one.")
    if user is not None and not admin:
        # One row per Claude call, not tied to a shop, so deleting the shop doesn't reset the daily cap.
        audit.record(session, actor="reader", action="describe_used", result="ok", user_id=user.id)
    image = None
    if photo is not None and photo.filename:
        data = await photo.read(MAX_IMAGE_BYTES + 1)
        image = (data, (photo.content_type or "").lower())
    try:
        profile = read_business(claude, description=description, price_list=price_list, image=image)
    except ReaderError as e:
        audit.record(session, actor="reader", action="read_business", result="failed", detail=str(e)[:300],
                     user_id=actor.user_id)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ClaudeBudgetExceeded as e:
        audit.record(session, actor="reader", action="read_business", result="blocked", detail=str(e))
        raise HTTPException(status_code=503, detail="Our assistant has reached today's limit. Please try again tomorrow.") from e

    if profile.kind == "appointments":
        # Scope guard: v1 builds shops that take orders. Don't build a shop for a booking business.
        reason = profile.not_supported_reason.strip() or NOT_SUPPORTED_DEFAULT
        audit.record(session, actor="reader", action="read_business", result="refused",
                     detail="needs appointments/booking, not orders; no shop built")
        raise HTTPException(status_code=422, detail=reason)

    # Every shop starts as practice. It becomes real only through an approved user's real launch.
    guest_raw, guest_hash = None, ""
    if user is None:  # "Try it" without signing in: an anonymous cookie owns a practice workspace
        guest_hash = actor.guest
        if not guest_hash:
            guest_raw = secrets.token_urlsafe(32)
            guest_hash = sha(guest_raw)
    b = Business(name=profile.name, description=description, price_list_text=price_list,
                 profile_json=profile.model_dump_json(), subdomain=unique_subdomain(session, slugify(profile.name)),
                 practice=True, guest_hash=guest_hash, visitor="" if admin else visitor)
    session.add(b)
    session.commit()
    session.refresh(b)
    if user is not None:
        session.add(Membership(user_id=user.id, business_id=b.id, role="owner"))
        session.commit()
    audit.record(session, actor="reader", action="read_business", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id,
                 detail=f"{len(profile.products)} products" + (", with photo" if image else "")
                 + (", guest practice" if user is None else ", practice"))
    fell_back = getattr(claude, "fell_back", False)
    if fell_back:
        audit.record(session, actor="reader", action="claude_fallback", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail="live Claude unavailable or daily cap reached; used a saved sample")
    out = {**business_out(b, settings, session), "assistant_note": FALLBACK_NOTE if fell_back else None}
    if guest_raw is not None:
        accounts.set_guest_cookie(response, settings, guest_raw)
        out["csrf"] = csrf_for(guest_raw)  # the page needs it for its next change (the cookie itself is HttpOnly)
    return out


@router.get("/businesses")
def list_businesses(actor: ActorDep, settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    """"My shops": only the caller's own, filtered in the query. (The team's list of every shop is /api/admin/businesses.)"""
    if actor.user is not None:
        q = select(Business).join(Membership, Membership.business_id == Business.id).where(Membership.user_id == actor.user.id)
    elif actor.guest:
        q = select(Business).where(Business.guest_hash == actor.guest)
    else:
        return []
    return [{**business_out(b, settings, session), "renewal": shop_renewal(session, settings, b)}
            for b in session.exec(q.order_by(Business.id.desc())).all()]


def shop_renewal(session: Session, settings: Settings, b: Business) -> dict | None:
    """The renewal of a live shop that needs attention soonest (S10 Renewals), for "My shops"."""
    if b.status != "live":
        return None
    from app import renewals
    from app.agents.launch_check import latest_launched_plan
    from app.models import CheckRun

    plan = latest_launched_plan(session, b.id)
    run = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.status == "done")
                       .order_by(CheckRun.id.desc())).first()
    if plan is None:
        return None
    return renewals.nearest(renewals.card(settings, plan.mode, plan.zone, json.loads(run.info_json) if run else {}))


@router.get("/businesses/{business_id}")
def read_one(b: Annotated[Business, Depends(require_business_access)],
             settings: Annotated[Settings, Depends(get_settings)],
             session: Annotated[Session, Depends(get_session)]) -> dict:
    return business_out(b, settings, session)


class ProfileUpdate(BaseModel):
    profile: Profile
    subdomain: str


@router.put("/businesses/{business_id}")
def update_business(body: ProfileUpdate, actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                    settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> dict:
    sub = body.subdomain.strip().lower()
    problem = slug_problem(sub) if sub != b.subdomain else None
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if sub != b.subdomain and is_public(b):
        raise HTTPException(status_code=409, detail="Your shop is live at this address, so it can't be changed here.")
    taken = session.exec(select(Business.id).where(Business.subdomain == sub, Business.id != b.id)).first()
    if taken:
        raise HTTPException(status_code=409, detail="That site address is already taken. Please pick another.")
    old_sub = b.subdomain
    b.name = body.profile.name
    b.profile_json = body.profile.model_dump_json()
    b.subdomain = sub
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="owner", action="profile_saved", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"subdomain {old_sub} -> {sub}" if old_sub != sub else "")
    return business_out(b, settings, session)


@router.get("/businesses/{business_id}/preview", response_class=HTMLResponse)
def preview(b: Annotated[Business, Depends(require_business_access)], page: str = "home") -> HTMLResponse:
    """The owner's private look at their shop (drafts and practice shops are never public)."""
    profile = Profile.model_validate_json(b.profile_json)
    return HTMLResponse(render_site(profile, page="privacy" if page == "privacy" else "home", preview=True),
                        headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"})


@router.get("/businesses/{business_id}/orders")
def list_orders(b: Annotated[Business, Depends(require_business_access)],
                session: Annotated[Session, Depends(get_session)], tests: bool = False) -> list[dict]:
    """The shop's orders, newest first. The checker's own test orders are left out unless asked for."""
    q = select(Order).where(Order.business_id == b.id)
    if not tests:
        q = q.where(Order.is_test == False)  # noqa: E712
    rows = session.exec(q.order_by(Order.id.desc()).limit(500)).all()
    return [{"id": o.id, "ref": o.ref, "is_test": o.is_test, "customer_name": o.customer_name, "customer_phone": o.customer_phone,
             "items": json.loads(o.items_json), "total_inr": o.total_inr, "note": o.note,
             "email_status": o.email_status, "created_at": o.created_at.replace(tzinfo=None).isoformat() + "Z"} for o in rows]


@router.get("/businesses/{business_id}/export")
def export_business(b: Annotated[Business, Depends(require_business_access)],
                    session: Annotated[Session, Depends(get_session)]) -> dict:
    """Everything we hold about the shop, for the owner to keep."""
    return {"shop": {"name": b.name, "address": b.subdomain, "status": b.status, "practice": b.practice,
                     "created_at": b.created_at.isoformat(), "description": b.description,
                     "price_list": b.price_list_text, "profile": json.loads(b.profile_json)},
            "orders": list_orders(b, session, tests=True)}


@router.delete("/businesses/{business_id}")
def delete_business(actor: ActorDep, b: Annotated[Business, Depends(require_business_access)],
                    settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)],
                    server: Annotated[Integrations, Depends(get_integrations)],
                    practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> dict:
    """Take the shop off the internet and delete it with its orders. Can't be undone."""
    business_id, was_public = b.id, is_public(b)
    purge_business(session, settings, for_business(b, server, practice), b)
    audit.record(session, actor=actor.label, action="shop_deleted", target=f"business:{business_id}", result="ok",
                 user_id=actor.user_id, detail="was public" if was_public else "was not public")
    return {"ok": True}
