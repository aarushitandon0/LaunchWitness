"""Seller-facing API: read a business description, review/edit the profile, list orders."""

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import audit
from app.agents.claude_client import FALLBACK_NOTE, Claude, ClaudeBudgetExceeded, make_claude_client
from app.agents.reader import MAX_IMAGE_BYTES, Profile, ReaderError, read_business
from app.config import Settings, get_settings
from app.db import get_engine, get_session
from app.models import Business, Order
from app.safety.access import (admin_flag, describes_today, hash_key, new_owner_key, owned_business, owner_link,
                               require_admin, visitor_id)
from app.sites.hosts import is_public, site_url, slug_problem
from app.sites.render import render_site

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


def business_out(b: Business, settings: Settings) -> dict:
    return {
        "id": b.id,
        "subdomain": b.subdomain,
        "site_url": site_url(b.subdomain, settings) if b.subdomain else None,
        "status": b.status,
        "practice": b.practice,
        "public": is_public(b) and not b.paused,  # false = only the owner sees it, through the preview
        "owner_email": b.owner_email,
        "profile": json.loads(b.profile_json),
    }


NOT_SUPPORTED_DEFAULT = ("Your customers book a time with you, and for now we can only build shops that take orders, "
                         "so we can't make your website yet.")

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
    admin: Annotated[bool, Depends(admin_flag)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    claude: Annotated[Claude, Depends(get_claude)],
    description: Annotated[str, Form(max_length=4000)] = "",
    price_list: Annotated[str, Form(max_length=4000)] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> dict:
    visitor = visitor_id(request)
    if not admin and describes_today(session, visitor) >= settings.visitor_describes_per_day:
        raise HTTPException(status_code=429, detail="You've set up several shops today already. "
                            "Please come back tomorrow to try another one.")
    image = None
    if photo is not None and photo.filename:
        data = await photo.read(MAX_IMAGE_BYTES + 1)
        image = (data, (photo.content_type or "").lower())
    try:
        profile = read_business(claude, description=description, price_list=price_list, image=image)
    except ReaderError as e:
        audit.record(session, actor="reader", action="read_business", result="failed", detail=str(e)[:300])
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

    key = new_owner_key()
    # Only the admin on a real server creates real businesses; everyone else practises (never real GoDaddy/DNS).
    practice = not (admin and not settings.use_fakes)
    b = Business(name=profile.name, description=description, price_list_text=price_list,
                 profile_json=profile.model_dump_json(), subdomain=unique_subdomain(session, slugify(profile.name)),
                 owner_key_hash=hash_key(key), practice=practice, visitor="" if admin else visitor)
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="reader", action="read_business", target=f"business:{b.id}", result="ok",
                 business_id=b.id, detail=f"{len(profile.products)} products" + (", with photo" if image else "")
                 + (", practice" if practice else ", real"))
    fell_back = getattr(claude, "fell_back", False)
    if fell_back:
        audit.record(session, actor="reader", action="claude_fallback", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail="live Claude unavailable or daily cap reached; used a saved sample")
    # The owner key is returned ONCE, here. Only its hash is stored.
    return {**business_out(b, settings), "owner_key": key, "owner_link": owner_link(settings, b.id, key),
            "assistant_note": FALLBACK_NOTE if fell_back else None}


@router.get("/businesses", dependencies=[Depends(require_admin)])
def list_businesses(settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Business).order_by(Business.id.desc())).all()
    return [{"id": b.id, "name": b.name, "subdomain": b.subdomain,
             "site_url": site_url(b.subdomain, settings) if b.subdomain else None} for b in rows]


@router.get("/businesses/{business_id}")
def read_one(b: Annotated[Business, Depends(owned_business)], settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    return business_out(b, settings)


class ProfileUpdate(BaseModel):
    profile: Profile
    subdomain: str
    owner_email: str | None = Field(default=None, max_length=254)  # personal email for alerts; None = unchanged


@router.put("/businesses/{business_id}")
def update_business(body: ProfileUpdate, b: Annotated[Business, Depends(owned_business)],
                    settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> dict:
    email = body.owner_email.strip() if body.owner_email is not None else None
    if email and not EMAIL.match(email):
        raise HTTPException(status_code=422, detail="That email address doesn't look right. Please check it.")
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
    if email is not None:
        b.owner_email = email
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="owner", action="profile_saved", target=f"business:{b.id}", result="ok",
                 business_id=b.id, detail=f"subdomain {old_sub} -> {sub}" if old_sub != sub else "")
    return business_out(b, settings)


@router.get("/businesses/{business_id}/preview", response_class=HTMLResponse)
def preview(b: Annotated[Business, Depends(owned_business)], page: str = "home") -> HTMLResponse:
    """The owner's private look at their shop (drafts and practice shops are never public)."""
    profile = Profile.model_validate_json(b.profile_json)
    return HTMLResponse(render_site(profile, page="privacy" if page == "privacy" else "home", preview=True),
                        headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-store"})


@router.get("/businesses/{business_id}/orders")
def list_orders(b: Annotated[Business, Depends(owned_business)], session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Order).where(Order.business_id == b.id).order_by(Order.id.desc())).all()
    return [{"id": o.id, "customer_name": o.customer_name, "customer_phone": o.customer_phone,
             "items": json.loads(o.items_json), "total_inr": o.total_inr, "note": o.note,
             "email_status": o.email_status, "created_at": o.created_at.replace(tzinfo=None).isoformat() + "Z"} for o in rows]
