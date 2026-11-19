"""Team (admin) pages: approval queue, users, shops, reports. Every action is written to the audit log."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import accounts, audit
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, get_integrations, get_practice_integrations
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


def tell(settings: Settings, mailer: Mailer, session: Session, user: User, subject: str, body: str) -> bool:
    """Email the user about a decision, through the outbox (kept and retried if the mail server is down).
    A mail failure never undoes the decision. True if it went out now."""
    import secrets

    from app import outbox

    row = outbox.send(session, settings, mailer, kind="team", key=f"decision:{user.id}:{secrets.token_hex(8)}",
                      to=user.email, subject=subject, body=body + "\n\n- LaunchWitness", user_id=user.id,
                      ref={"audit": {"actor": "system", "action": "decision_email", "target": f"user:{user.id}"}})
    if row.status != "sent":
        log.warning("could not email a decision at once: %s", row.last_error)
    return row.status == "sent"


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
    emailed = tell(settings, mailer, session, u, "You're approved on LaunchWitness",
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
def reject_user(user_id: int, body: Reason, admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
                session: Annotated[Session, Depends(get_session)],
                mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    """Turn down a sign-up: the account can't sign in; the user gets the reason by email."""
    u = get_user(session, user_id)
    if u.role == "admin":
        raise HTTPException(status_code=409, detail="The admin account can't be rejected.")
    _suspend(session, u, body.reason)
    audit.record(session, actor="admin", action="user_rejected", target=f"user:{u.id}", result="ok",
                 user_id=admin.user_id, detail=body.reason)
    emailed = tell(settings, mailer, session, u, "About your LaunchWitness sign-up",
                   "Thank you for signing up. We can't approve your account right now."
                   + (f"\n\nReason: {body.reason.strip()}" if body.reason.strip() else "")
                   + "\n\nIf you think this is a mistake, reply through the contact form on our home page.")
    return {**user_out(session, u), "emailed": emailed}


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: int, body: Reason, admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    """Suspended users can't sign in, every session ends at once, and their shops are paused."""
    u = get_user(session, user_id)
    if u.role == "admin":
        raise HTTPException(status_code=409, detail="The admin account can't be suspended.")
    paused = _suspend(session, u, body.reason)
    audit.record(session, actor="admin", action="user_suspended", target=f"user:{u.id}", result="ok",
                 user_id=admin.user_id, detail=f"{body.reason} ({paused} shop(s) paused)")
    emailed = tell(settings, mailer, session, u, "Your LaunchWitness account is suspended",
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
                    "created_at": iso(b.created_at),
                    # S19D: an edit to this live shop that the policy check held (the shop shows the last approved one)
                    "pending_edit": {"reason": b.pending_reason, "at": iso(b.pending_at)} if b.pending_profile_json else None})
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


@router.post("/businesses/{business_id}/publish-edit")
def publish_edit(business_id: int, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    """S19D: the team looked at a held edit to a live shop and it's fine: it goes up now (same save as the owner's)."""
    from app.agents.reader import Profile
    from app.routers.businesses import apply_profile

    b = get_business(session, business_id)
    if not b.pending_profile_json:
        raise HTTPException(status_code=409, detail="This shop has no edit waiting.")
    apply_profile(session, b, Profile.model_validate_json(b.pending_profile_json), actor="admin", user_id=admin.user_id,
                  note="held edit published by the team")
    return {"ok": True, "pending_edit": None}


@router.post("/businesses/{business_id}/discard-edit")
def discard_edit(business_id: int, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    """S19D: the held edit is not OK: it is dropped; the shop keeps its approved version (and stays live)."""
    b = get_business(session, business_id)
    if not b.pending_profile_json:
        raise HTTPException(status_code=409, detail="This shop has no edit waiting.")
    b.pending_profile_json, b.pending_reason, b.pending_at = "", "", None
    session.add(b)
    session.commit()
    audit.record(session, actor="admin", action="edit_discarded", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=admin.user_id)
    return {"ok": True, "pending_edit": None}


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


# ---------- zone hygiene (S10): proposed fixes to shop A records on the app domain; the admin decides ----------

def _zone_godaddy(integ: Annotated[Integrations, Depends(get_integrations)]):
    return integ.godaddy  # the server's own GoDaddy (the guarded client writes shop A records only)


@router.get("/zone-findings")
def zone_findings(admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> list[dict]:
    from app.models import ZoneFinding
    from app.zone_hygiene import finding_out

    rows = session.exec(select(ZoneFinding).order_by(ZoneFinding.id.desc()).limit(100)).all()
    return [finding_out(f) for f in rows]


@router.post("/zone-check")
def zone_check(admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
               session: Annotated[Session, Depends(get_session)], godaddy=Depends(_zone_godaddy)) -> dict:
    """Read the app zone now and list what doesn't match the shops (changes nothing)."""
    from app.zone_hygiene import finding_out, scan

    try:
        found = scan(session.get_bind(), settings, godaddy)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"We couldn't read the address records ({type(e).__name__}).") from e
    return {"open": [finding_out(f) for f in found]}


@router.post("/zone-findings/{finding_id}/approve")
def zone_approve(finding_id: int, admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)], godaddy=Depends(_zone_godaddy)) -> dict:
    from app.zone_hygiene import NoLongerTrue, approve, finding_out

    by = admin.user.email if admin.user else "admin token"
    try:
        f = approve(session.get_bind(), settings, godaddy, finding_id, by)
    except LookupError as e:
        raise HTTPException(status_code=404, detail="That finding isn't open any more.") from e
    except NoLongerTrue as e:
        raise HTTPException(status_code=409, detail="That's no longer the case, so nothing was changed.") from e
    return finding_out(f)


@router.post("/zone-findings/{finding_id}/dismiss")
def zone_dismiss(finding_id: int, admin: AdminDep, session: Annotated[Session, Depends(get_session)]) -> dict:
    from app.zone_hygiene import dismiss, finding_out

    try:
        return finding_out(dismiss(session.get_bind(), finding_id, admin.user.email if admin.user else "admin token"))
    except LookupError as e:
        raise HTTPException(status_code=404, detail="That finding isn't open any more.") from e


# ---------- S13: the email outbox ----------

@router.get("/outbox")
def outbox_summary(admin: AdminDep, settings: Annotated[Settings, Depends(get_settings)],
                   session: Annotated[Session, Depends(get_session)]) -> dict:
    """Counts by status and the last errors (kind, tries, error kind). No bodies, no addresses, no customer data."""
    from app import outbox

    return outbox.summary(session, settings)


class PracticeMail(BaseModel):
    down: bool


@router.put("/practice-mail")
def practice_mail(body: PracticeMail, admin: AdminDep, session: Annotated[Session, Depends(get_session)],
                  practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> dict:
    """Practice only: make the PRETEND mail server refuse (or accept again), to show an order kept while email is
    down. It can't touch the real mail server: it only exists in the pretend world."""
    mailer = practice.mailer
    if not practice.fake or not hasattr(mailer, "fail"):
        raise HTTPException(status_code=409, detail="This only works on the pretend mail server.")
    mailer.fail = body.down
    audit.record(session, actor="admin", action="practice_mail", target="pretend mail server", result="ok",
                 user_id=admin.user_id, detail="down" if body.down else "up")
    return {"down": mailer.fail, "practice": True}
