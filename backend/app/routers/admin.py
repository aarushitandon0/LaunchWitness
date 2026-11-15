"""Team (admin) pages: approval queue, users, shops, reports. Every action is written to the audit log."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import accounts, audit
from app.config import Settings, get_settings
from app.db import get_session
from app.mail.smtp import Mailer, get_mailer
from app.models import Business, Membership, ShopReport, User
from app.safety.access import Actor, require_admin
from app.sites.hosts import is_public, site_url

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])
AdminDep = Annotated[Actor, Depends(require_admin)]


def iso(v) -> str | None:
    return v.replace(tzinfo=None).isoformat() + "Z" if v else None


def user_out(session: Session, u: User) -> dict:
    shops = session.exec(select(Business.name).join(Membership, Membership.business_id == Business.id)
                         .where(Membership.user_id == u.id)).all()
    return {"id": u.id, "email": u.email, "status": u.status, "role": u.role, "status_reason": u.status_reason,
            "created_at": iso(u.created_at), "last_login_at": iso(u.last_login_at), "shops": list(shops)}


def tell(mailer: Mailer, session: Session, user: User, subject: str, body: str) -> bool:
    """Email the user about a decision. A mail failure never undoes the decision; it is logged."""
    try:
        mailer.send(to=user.email, subject=subject, body=body + "\n\n- LaunchWitness")
        return True
    except Exception as e:
        log.warning("could not email a decision: %s", type(e).__name__)
        audit.record(session, actor="system", action="decision_email", target=f"user:{user.id}", result="failed",
                     detail=type(e).__name__)
        return False


def get_user(session: Session, user_id: int) -> User:
    u = session.get(User, user_id)
    if u is None or u.status == "deleted":
        raise HTTPException(status_code=404, detail="We couldn't find that user.")
    return u


class Reason(BaseModel):
    reason: str = Field(default="", max_length=300)


@router.get("/check")
def admin_check(_admin: AdminDep) -> dict:
    return {"admin": True}


@router.get("/users")
def users(admin: AdminDep, session: Annotated[Session, Depends(get_session)], status: str | None = None) -> list[dict]:
    q = select(User).where(User.status != "deleted")
    if status:
        q = q.where(User.status == status)
    rows = session.exec(q.order_by(User.id.desc()).limit(500)).all()
    audit.record(session, actor="admin", action="admin_list_users", result="ok", user_id=admin.user_id,
                 detail=f"{len(rows)} row(s), status={status or 'any'}")
    return [user_out(session, u) for u in rows]


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    u = get_user(session, user_id)
    u.status, u.status_reason = "approved", ""
    session.add(u)
    session.commit()
    audit.record(session, actor="admin", action="user_approved", target=f"user:{u.id}", result="ok", user_id=admin.user_id)
    emailed = tell(mailer, session, u, "You're approved on LaunchWitness",
                   "Good news: your LaunchWitness account is approved. You can now launch your shop for real.\n\n"
                   f"Sign in here: {settings.app_base_url.rstrip('/')}/#/signin")
    return {**user_out(session, u), "emailed": emailed}


def _suspend(session: Session, u: User, reason: str) -> int:
    u.status, u.status_reason = "suspended", reason.strip()
    session.add(u)
    paused = 0
    for b in session.exec(select(Business).join(Membership, Membership.business_id == Business.id)
                          .where(Membership.user_id == u.id)).all():
        if not b.paused:
            b.paused, b.paused_reason, paused = True, "owner's account is suspended", paused + 1
            session.add(b)
    session.commit()
    accounts.revoke_sessions(session, u.id)
    return paused


@router.post("/users/{user_id}/reject")
def reject_user(user_id: int, body: Reason, admin: AdminDep, session: Annotated[Session, Depends(get_session)],
                mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    """Turn down a sign-up: the account can't sign in; the user gets the reason by email."""
    u = get_user(session, user_id)
    if u.role == "admin":
        raise HTTPException(status_code=409, detail="The admin account can't be rejected.")
    _suspend(session, u, body.reason)
    audit.record(session, actor="admin", action="user_rejected", target=f"user:{u.id}", result="ok",
                 user_id=admin.user_id, detail=body.reason)
    emailed = tell(mailer, session, u, "About your LaunchWitness sign-up",
                   "Thank you for signing up. We can't approve your account right now."
                   + (f"\n\nReason: {body.reason.strip()}" if body.reason.strip() else "")
                   + "\n\nIf you think this is a mistake, reply through the contact form on our home page.")
    return {**user_out(session, u), "emailed": emailed}


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: int, body: Reason, admin: AdminDep, session: Annotated[Session, Depends(get_session)],
                 mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    """Suspended users can't sign in, every session ends at once, and their shops are paused."""
    u = get_user(session, user_id)
    if u.role == "admin":
        raise HTTPException(status_code=409, detail="The admin account can't be suspended.")
    paused = _suspend(session, u, body.reason)
    audit.record(session, actor="admin", action="user_suspended", target=f"user:{u.id}", result="ok",
                 user_id=admin.user_id, detail=f"{body.reason} ({paused} shop(s) paused)")
    emailed = tell(mailer, session, u, "Your LaunchWitness account is suspended",
                   "Your LaunchWitness account has been suspended and your shops are paused."
                   + (f"\n\nReason: {body.reason.strip()}" if body.reason.strip() else "")
                   + "\n\nIf you think this is a mistake, reply through the contact form on our home page.")
    return {**user_out(session, u), "emailed": emailed, "shops_paused": paused}


@router.get("/businesses")
def businesses(admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
               session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    rows = session.exec(select(Business).order_by(Business.id.desc()).limit(500)).all()
    audit.record(session, actor="admin", action="admin_list_shops", result="ok", user_id=admin.user_id,
                 detail=f"{len(rows)} row(s)")
    out = []
    for b in rows:
        owners = session.exec(select(User.email).join(Membership, Membership.user_id == User.id)
                              .where(Membership.business_id == b.id)).all()
        out.append({"id": b.id, "name": b.name, "subdomain": b.subdomain, "status": b.status, "practice": b.practice,
                    "public": is_public(b) and not b.paused, "paused": b.paused, "paused_reason": b.paused_reason,
                    "review": b.review, "review_reason": b.review_reason, "guest": bool(b.guest_hash),
                    "owners": list(owners), "site_url": site_url(b.subdomain, settings) if b.subdomain else None,
                    "created_at": iso(b.created_at)})
    return out


def get_business(session: Session, business_id: int) -> Business:
    b = session.get(Business, business_id)
    if b is None:
        raise HTTPException(status_code=404, detail="We couldn't find that shop.")
    return b


@router.post("/businesses/{business_id}/pause")
def pause(business_id: int, body: Reason, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    """Takes effect on the very next request: the shop shows a neutral "This shop is paused" page."""
    b = get_business(session, business_id)
    b.paused, b.paused_reason = True, body.reason.strip()
    session.add(b)
    session.commit()
    audit.record(session, actor="admin", action="shop_paused", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=admin.user_id, detail=body.reason)
    return {"ok": True, "paused": True}


@router.post("/businesses/{business_id}/unpause")
def unpause(business_id: int, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    b = get_business(session, business_id)
    b.paused, b.paused_reason = False, ""
    session.add(b)
    session.commit()
    audit.record(session, actor="admin", action="shop_unpaused", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=admin.user_id)
    return {"ok": True, "paused": False}


@router.post("/businesses/{business_id}/clear-review")
def clear_review(business_id: int, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    """A shop held by the go-live policy check may launch once the team has looked at it."""
    b = get_business(session, business_id)
    b.review, b.review_reason = "cleared", ""
    session.add(b)
    session.commit()
    audit.record(session, actor="admin", action="shop_review_cleared", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=admin.user_id)
    return {"ok": True, "review": "cleared"}


@router.get("/reports")
def reports(admin: AdminDep, session: Annotated[Session, Depends(get_session)], status: str = "open") -> list[dict]:
    rows = session.exec(select(ShopReport).where(ShopReport.status == status).order_by(ShopReport.id.desc()).limit(500)).all()
    out = []
    for r in rows:
        b = session.get(Business, r.business_id)
        out.append({"id": r.id, "business_id": r.business_id, "shop": b.name if b else "(deleted)",
                    "subdomain": b.subdomain if b else None, "paused": bool(b and b.paused), "reason": r.reason,
                    "note": r.note, "status": r.status, "created_at": iso(r.created_at)})
    return out


@router.post("/reports/{report_id}/close")
def close_report(report_id: int, body: Reason, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    r = session.get(ShopReport, report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="We couldn't find that report.")
    r.status, r.closed_note = "closed", body.reason.strip()
    session.add(r)
    session.commit()
    audit.record(session, actor="admin", action="report_closed", target=f"report:{r.id}", result="ok",
                 business_id=r.business_id, user_id=admin.user_id, detail=body.reason)
    return {"ok": True}
