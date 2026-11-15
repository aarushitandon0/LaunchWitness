"""Who may do what.

- **User**: signs in with an emailed link. The browser holds a session cookie
  (`__Host-lw_session`: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain, so it is
  sent to the app's own host only and never to a shop subdomain). Only the SHA-256
  of the cookie value is stored (`sessions` table).
- **Guest**: "Try it" without signing in. An anonymous cookie owns a practice
  workspace (practice only, never public, removed after 24 hours). Signing in
  moves it to the account.
- **Admin**: the user whose email is ADMIN_EMAIL (role admin). `X-Admin-Token`
  (ADMIN_TOKEN) is kept for the command line and emergencies only.

`require_business_access` is the ONE gate every business-scoped route goes
through. The ownership filter is part of the database query, and someone else's
business answers 404 (not 403), so ids can't be probed.
"""

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session, func, select

from app import audit
from app.config import Settings, get_settings
from app.db import get_session
from app.models import AuditEvent, Business, Membership, Plan, User, UserSession, utcnow

DEFAULT_ADMIN_TOKEN = "change-me"
MIN_ADMIN_TOKEN = 16
COOKIE_VALUE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
ACTIVE = ("pending", "approved")  # statuses that may sign in
NOT_FOUND = "We couldn't find that shop."
SIGN_IN = "Please sign in to continue."


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for(cookie_value: str) -> str:
    """CSRF token tied to the session: derived from the HttpOnly cookie value, which page
    scripts can't read. The app gets it from /api/auth/me and sends it back in X-CSRF-Token."""
    return hashlib.sha256(b"lw-csrf:" + cookie_value.encode()).hexdigest()


def aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def admin_token_enabled(settings: Settings) -> bool:
    token = settings.admin_token.get_secret_value()
    return token != DEFAULT_ADMIN_TOKEN and len(token) >= MIN_ADMIN_TOKEN


def is_admin_token(settings: Settings, token: str | None) -> bool:
    if not token or not admin_token_enabled(settings):
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


def user_describes_today(session: Session, user_id: int) -> int:
    """Claude "describe" calls this user made today. Counted from `describe_used` audit rows, which carry no
    business id, so deleting a shop (which purges that shop's audit rows) doesn't reset the cap."""
    q = select(func.count()).select_from(AuditEvent).where(
        AuditEvent.user_id == user_id, AuditEvent.action == "describe_used", AuditEvent.created_at >= start_of_today())
    return session.exec(q).one()


def launches_today(session: Session, visitor: str) -> int:
    q = select(func.count()).select_from(Plan).where(Plan.visitor == visitor, Plan.approved_at >= start_of_today())
    return session.exec(q).one()


# ---------- who is calling ----------

@dataclass
class Actor:
    user: User | None = None
    session_row: UserSession | None = None
    guest: str = ""  # sha256 of the anonymous practice cookie ("" = none)
    token_admin: bool = False  # X-Admin-Token (command line / emergency)

    @property
    def is_admin(self) -> bool:
        return self.token_admin or (self.user is not None and self.user.role == "admin" and self.user.status == "approved")

    @property
    def approved(self) -> bool:
        """May do real launches (pending users practise only)."""
        return self.is_admin or (self.user is not None and self.user.status == "approved")

    @property
    def user_id(self) -> int | None:
        return self.user.id if self.user else None

    @property
    def label(self) -> str:
        return "admin" if self.is_admin else "owner" if self.user else "guest"


def session_user(session: Session, settings: Settings, raw: str | None) -> tuple[User, UserSession] | None:
    """The signed-in user for this cookie value, with the 14-day sliding expiry. None if the
    session is unknown, revoked, expired, or the user is suspended/deleted."""
    if not raw or not COOKIE_VALUE.match(raw):
        return None
    row = session.exec(select(UserSession).where(UserSession.token_hash == sha(raw),
                                                 UserSession.revoked == False)).first()  # noqa: E712
    now = utcnow()
    if row is None or aware(row.expires_at) <= now:
        return None
    user = session.get(User, row.user_id)
    if user is None or user.status not in ACTIVE:
        return None
    if now - aware(row.last_seen_at) > timedelta(minutes=10):  # slide, without a write on every request
        row.last_seen_at, row.expires_at = now, now + timedelta(days=settings.session_days)
        session.add(row)
        session.commit()
    return user, row


def get_actor(request: Request, settings: Annotated[Settings, Depends(get_settings)],
              session: Annotated[Session, Depends(get_session)],
              x_admin_token: Annotated[str | None, Header()] = None) -> Actor:
    actor = Actor(token_admin=is_admin_token(settings, x_admin_token))
    found = session_user(session, settings, request.cookies.get(settings.session_cookie))
    if found is not None:
        actor.user, actor.session_row = found
    guest = request.cookies.get(settings.guest_cookie)
    if guest and COOKIE_VALUE.match(guest):
        actor.guest = sha(guest)
    return actor


ActorDep = Annotated[Actor, Depends(get_actor)]


def admin_flag(actor: ActorDep) -> bool:
    return actor.is_admin


def require_user(actor: ActorDep) -> User:
    if actor.user is None:
        raise HTTPException(status_code=401, detail=SIGN_IN)
    return actor.user


def require_admin(actor: ActorDep) -> Actor:
    if actor.is_admin:
        return actor
    if actor.user is None:
        raise HTTPException(status_code=401, detail=SIGN_IN)
    raise HTTPException(status_code=403, detail="This is for the LaunchWitness team only.")


# ---------- the one gate for everything that belongs to a business ----------

def business_query(actor: Actor):
    """SELECT of the businesses this actor may manage: the ownership filter is IN the query."""
    q = select(Business)
    if actor.is_admin:
        return q
    if actor.user is not None:
        return q.join(Membership, Membership.business_id == Business.id).where(Membership.user_id == actor.user.id)
    if actor.guest:
        return q.where(Business.guest_hash == actor.guest)
    return None


def load_business(session: Session, actor: Actor, business_id: int, need: str = "owner") -> Business:
    q = business_query(actor)
    if q is None:
        raise HTTPException(status_code=401, detail=SIGN_IN)
    if need == "owner" and actor.user is not None and not actor.is_admin:
        q = q.where(Membership.role == "owner")
    b = session.exec(q.where(Business.id == business_id)).first()
    if b is None:  # not there, or not yours: the same answer, so ids can't be probed
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    if actor.is_admin and actor.user is not None:
        mine = session.exec(select(Membership.id).where(Membership.business_id == b.id,
                                                        Membership.user_id == actor.user.id)).first()
        if mine is None:  # the team looked at someone else's shop: write it down
            audit.record(session, actor="admin", action="admin_access", target=f"business:{b.id}", result="ok",
                         business_id=b.id, user_id=actor.user.id)
    return b


def require_business_access(business_id: int, actor: ActorDep,
                            session: Annotated[Session, Depends(get_session)]) -> Business:
    """Every business-scoped route depends on this (or on `require_plan_access`, which calls it)."""
    return load_business(session, actor, business_id, need="owner")


def require_plan_access(plan_id: int, actor: ActorDep, session: Annotated[Session, Depends(get_session)]) -> Plan:
    if business_query(actor) is None:
        raise HTTPException(status_code=401, detail=SIGN_IN)
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    load_business(session, actor, plan.business_id, need="owner")  # 404 unless it's the caller's
    return plan


def owner_emails(session: Session, business_id: int) -> list[str]:
    """Verified sign-in addresses of the shop's owners (orders, test orders and alerts go there)."""
    rows = session.exec(select(User.email).join(Membership, Membership.user_id == User.id)
                        .where(Membership.business_id == business_id, Membership.role == "owner",
                               User.status.in_(ACTIVE)).order_by(Membership.id)).all()  # type: ignore[attr-defined]
    return list(rows)


def run_by_team(session: Session, business_id: int) -> bool:
    """True when the shop's owner is an admin: a shop we run ourselves (its orders also reach the app mailbox)."""
    return session.exec(select(User.id).join(Membership, Membership.user_id == User.id)
                        .where(Membership.business_id == business_id, User.role == "admin")).first() is not None
