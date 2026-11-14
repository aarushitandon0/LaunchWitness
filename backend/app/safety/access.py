"""Who may do what, without accounts (decided 2026-11-14, session 3).

- Owner: each business has a secret owner link (random token). Only its sha256
  is stored. The token is sent as the `X-Owner-Key` header and is needed to edit,
  approve, launch, see the report or run checks. The seller's public site stays public.
- Admin: `X-Admin-Token` equal to ADMIN_TOKEN. Admin is OFF while ADMIN_TOKEN is
  the default or shorter than 16 characters. Admin may do anything an owner may,
  plus the demo fault switch, and is exempt from visitor limits.
- Visitor: a hash of the client IP, used for the per-day describe/launch limits.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session, func, select

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Business, Plan

DEFAULT_ADMIN_TOKEN = "change-me"
MIN_ADMIN_TOKEN = 16


def new_owner_key() -> str:
    return secrets.token_urlsafe(24)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def owner_link(settings: Settings, business_id: int, key: str) -> str:
    return f"{settings.app_base_url.rstrip('/')}/#/b/{business_id}?key={key}"


def admin_enabled(settings: Settings) -> bool:
    token = settings.admin_token.get_secret_value()
    return token != DEFAULT_ADMIN_TOKEN and len(token) >= MIN_ADMIN_TOKEN


def is_admin(settings: Settings, token: str | None) -> bool:
    if not token or not admin_enabled(settings):
        return False
    return hmac.compare_digest(token.encode(), settings.admin_token.get_secret_value().encode())


def visitor_id(request: Request) -> str:
    """Hashed client IP. Behind Caddy the real client is the LAST X-Forwarded-For entry
    (Caddy appends it and does not trust client-sent values by default)."""
    xff = request.headers.get("x-forwarded-for", "")
    ip = xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "")
    return hashlib.sha256(f"lw-visitor:{ip}".encode()).hexdigest()[:16]


def start_of_today() -> datetime:
    return datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)


def describes_today(session: Session, visitor: str) -> int:
    q = select(func.count()).select_from(Business).where(Business.visitor == visitor,
                                                         Business.created_at >= start_of_today())
    return session.exec(q).one()


def launches_today(session: Session, visitor: str) -> int:
    q = select(func.count()).select_from(Plan).where(Plan.visitor == visitor, Plan.approved_at >= start_of_today())
    return session.exec(q).one()


# ---------- FastAPI dependencies ----------

def admin_flag(settings: Annotated[Settings, Depends(get_settings)],
               x_admin_token: Annotated[str | None, Header()] = None) -> bool:
    return is_admin(settings, x_admin_token)


def require_admin(admin: Annotated[bool, Depends(admin_flag)]) -> None:
    if not admin:
        raise HTTPException(status_code=403, detail="This is for the LaunchWitness team only.")


NEED_LINK = "Please open this page from your owner link (the private link you saved when you described your business)."


def check_owner(b: Business, key: str | None, admin: bool) -> None:
    if admin:
        return
    if not key or not b.owner_key_hash or not hmac.compare_digest(hash_key(key), b.owner_key_hash):
        raise HTTPException(status_code=403, detail=NEED_LINK)


def owned_business(business_id: int, session: Annotated[Session, Depends(get_session)],
                   admin: Annotated[bool, Depends(admin_flag)],
                   x_owner_key: Annotated[str | None, Header()] = None) -> Business:
    b = session.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that business.")
    check_owner(b, x_owner_key, admin)
    return b


def owned_plan(plan_id: int, session: Annotated[Session, Depends(get_session)],
               admin: Annotated[bool, Depends(admin_flag)],
               x_owner_key: Annotated[str | None, Header()] = None) -> Plan:
    plan = session.get(Plan, plan_id)
    b = session.get(Business, plan.business_id) if plan else None
    if plan is None or b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that launch plan.")
    check_owner(b, x_owner_key, admin)
    return plan
