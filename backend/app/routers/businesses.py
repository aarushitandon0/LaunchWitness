"""Seller-facing API: read a business description, review/edit the profile, list orders."""

import json
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from app import audit
from app.agents.claude_client import Claude, ClaudeBudgetExceeded, make_claude_client
from app.agents.reader import MAX_IMAGE_BYTES, Profile, ReaderError, read_business
from app.config import Settings, get_settings
from app.db import get_engine, get_session
from app.models import Business, Order
from app.sites.hosts import RESERVED_SUBDOMAINS, SUBDOMAIN, site_url

router = APIRouter(prefix="/api", tags=["businesses"])
SELLERS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sellers"


def get_claude(settings: Annotated[Settings, Depends(get_settings)]) -> Claude:
    """FastAPI dependency. Tests override this."""
    return make_claude_client(settings, get_engine() if settings.claude_mode == "live" else None)


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("'", "")).strip("-")
    return s[:30].strip("-") or "shop"


def unique_subdomain(session: Session, base: str) -> str:
    candidate, n = base, 2
    while candidate in RESERVED_SUBDOMAINS or session.exec(select(Business.id).where(Business.subdomain == candidate)).first():
        candidate, n = f"{base[:27]}-{n}", n + 1
    return candidate


def business_out(b: Business, settings: Settings) -> dict:
    return {
        "id": b.id,
        "subdomain": b.subdomain,
        "site_url": site_url(b.subdomain, settings) if b.subdomain else None,
        "status": b.status,
        "profile": json.loads(b.profile_json),
    }


def get_business(session: Session, business_id: int) -> Business:
    b = session.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that business.")
    return b


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
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    claude: Annotated[Claude, Depends(get_claude)],
    description: Annotated[str, Form(max_length=4000)] = "",
    price_list: Annotated[str, Form(max_length=4000)] = "",
    photo: Annotated[UploadFile | None, File()] = None,
) -> dict:
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

    b = Business(name=profile.name, description=description, price_list_text=price_list,
                 profile_json=profile.model_dump_json(), subdomain=unique_subdomain(session, slugify(profile.name)))
    session.add(b)
    session.commit()
    session.refresh(b)
    audit.record(session, actor="reader", action="read_business", target=f"business:{b.id}", result="ok",
                 business_id=b.id, detail=f"{len(profile.products)} products" + (", with photo" if image else ""))
    return business_out(b, settings)


@router.get("/businesses")
def list_businesses(settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Business).order_by(Business.id.desc())).all()
    return [{"id": b.id, "name": b.name, "subdomain": b.subdomain,
             "site_url": site_url(b.subdomain, settings) if b.subdomain else None} for b in rows]


@router.get("/businesses/{business_id}")
def read_one(business_id: int, settings: Annotated[Settings, Depends(get_settings)],
             session: Annotated[Session, Depends(get_session)]) -> dict:
    return business_out(get_business(session, business_id), settings)


class ProfileUpdate(BaseModel):
    profile: Profile
    subdomain: str


@router.put("/businesses/{business_id}")
def update_business(business_id: int, body: ProfileUpdate, settings: Annotated[Settings, Depends(get_settings)],
                    session: Annotated[Session, Depends(get_session)]) -> dict:
    b = get_business(session, business_id)
    sub = body.subdomain.strip().lower()
    if not SUBDOMAIN.match(sub):
        raise HTTPException(status_code=422, detail="Site address can use only letters, numbers and dashes (2–42 characters).")
    if sub in RESERVED_SUBDOMAINS:
        raise HTTPException(status_code=422, detail="That site address is reserved. Please pick another.")
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
                 business_id=b.id, detail=f"subdomain {old_sub} -> {sub}" if old_sub != sub else "")
    return business_out(b, settings)


@router.get("/businesses/{business_id}/orders")
def list_orders(business_id: int, session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    get_business(session, business_id)
    rows = session.exec(select(Order).where(Order.business_id == business_id).order_by(Order.id.desc())).all()
    return [{"id": o.id, "customer_name": o.customer_name, "customer_phone": o.customer_phone,
             "items": json.loads(o.items_json), "total_inr": o.total_inr, "note": o.note,
             "email_status": o.email_status, "created_at": o.created_at.isoformat()} for o in rows]
