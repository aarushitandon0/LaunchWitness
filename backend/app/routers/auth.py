"""Sign-in by emailed link, sessions, "who am I", and deleting the account."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import accounts, audit
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.mail.smtp import Mailer, get_mailer
from app.models import Business, Membership, User
from app.safety.access import ACTIVE, COOKIE_VALUE, ActorDep, csrf_for, require_user, visitor_id
from app.tenancy import purge_business

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["auth"])

EXPIRED = "This link has expired or was already used. Please ask for a new one."
NO_EMAIL = "We couldn't send the email right now. Please try again in a few minutes."


class LinkRequest(BaseModel):
    email: str = Field(max_length=254)
    next: str | None = Field(default=None, max_length=200)


def send_link(settings: Settings, mailer: Mailer, session: Session, *, kind: str, email: str, page: str, raw: str,
              next_: str = "") -> dict:
    """Email the link. In DEV_MODE (local only) nothing is emailed and the link is returned instead.
    If the mail server is down we say so: we never pretend an email went out."""
    url = accounts.link_url(settings, page, raw, next_)
    if settings.dev_mode:
        return {"dev_link": url}
    subject, text, html = accounts.link_email(kind, url)
    try:
        mailer.send(to=email, subject=subject, body=text, html=html)
    except Exception as e:
        log.warning("could not send %s email: %s", kind, type(e).__name__)
        audit.record(session, actor="system", action=f"{kind}_email", result="failed", detail=type(e).__name__)
        raise HTTPException(status_code=503, detail=NO_EMAIL) from e
    audit.record(session, actor="system", action=f"{kind}_email", result="sent")
    return {}


@router.post("/auth/request-link")
def request_link(body: LinkRequest, request: Request, settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)],
                 mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    """Always the same answer, whether or not the address has an account, so nobody can find out which emails do."""
    email = accounts.normalize_email(body.email)
    if email is None:
        raise HTTPException(status_code=422, detail="That email address doesn't look right. Please check it.")
    visitor = visitor_id(request)
    if accounts.links_last_hour(session, visitor) >= settings.signin_links_per_ip_per_hour:
        raise HTTPException(status_code=429, detail="Too many sign-in links were asked for from here. "
                            "Please wait an hour and try again.")
    out = {"ok": True, "message": accounts.SAME_ANSWER}
    user = accounts.find_user(session, email)
    if user is not None and user.status not in ACTIVE:  # suspended: no link, same answer
        return out
    if accounts.links_today(session, email) >= settings.signin_links_per_email_per_day:
        audit.record(session, actor="system", action="login_email", result="blocked", detail="daily limit for one address")
        return out  # same answer; the limit protects the inbox from being flooded
    raw = accounts.issue_token(session, email, "login", visitor)
    out.update(send_link(settings, mailer, session, kind="login", email=email, page="signin/confirm", raw=raw,
                         next_=accounts.safe_next(body.next)))
    return out


class Confirm(BaseModel):
    token: str = Field(max_length=200)


def me_out(settings: Settings, session: Session, user: User | None, guest_raw: str | None, session_raw: str | None,
           integ_fake: bool) -> dict:
    cookie = session_raw if user is not None else guest_raw
    return {
        "user": {"email": user.email, "status": user.status, "role": user.role,
                 "status_reason": user.status_reason} if user else None,
        "guest": user is None and bool(guest_raw),
        "csrf": csrf_for(cookie) if cookie else None,
        "practice_server": integ_fake,  # true: even approved launches run against the pretend GoDaddy here
        "limits": {"shops": settings.max_shops_per_user},
    }


@router.post("/auth/confirm")
def confirm(body: Confirm, request: Request, response: Response, actor: ActorDep,
            settings: Annotated[Settings, Depends(get_settings)], session: Annotated[Session, Depends(get_session)],
            integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    """The "Sign in" button on the confirm page POSTs the token here. Only this uses the token up."""
    row = accounts.consume_token(session, body.token, "login")
    if row is None:
        raise HTTPException(status_code=400, detail=EXPIRED)
    user = accounts.user_for_login(session, settings, row.email)
    if user.status not in ACTIVE:
        raise HTTPException(status_code=403, detail="This account can't sign in right now. "
                            "Please use the contact form on our home page if you think that's a mistake.")
    raw = accounts.create_session(session, settings, user, request.headers.get("user-agent", ""))
    kept = accounts.adopt_guest_shops(session, settings, user, actor.guest)
    accounts.set_session_cookie(response, settings, raw)
    accounts.clear_cookie(response, settings, settings.guest_cookie)
    audit.record(session, actor="owner", action="login", target=f"user:{user.id}", result="ok", user_id=user.id,
                 detail=f"{kept} practice shop(s) kept" if kept else "")
    return {**me_out(settings, session, user, None, raw, integ.fake), "kept_shops": kept}


@router.get("/auth/me")
def me(request: Request, response: Response, actor: ActorDep, settings: Annotated[Settings, Depends(get_settings)],
       session: Annotated[Session, Depends(get_session)],
       integ: Annotated[Integrations, Depends(get_integrations)]) -> dict:
    session_raw = request.cookies.get(settings.session_cookie)
    if session_raw and actor.user is None:  # expired / revoked / suspended: drop the dead cookie
        accounts.clear_cookie(response, settings, settings.session_cookie)
    guest_raw = request.cookies.get(settings.guest_cookie)
    guest_raw = guest_raw if guest_raw and COOKIE_VALUE.match(guest_raw) else None
    response.headers["Cache-Control"] = "no-store"
    return me_out(settings, session, actor.user, guest_raw, session_raw, integ.fake)


@router.post("/auth/logout")
def logout(response: Response, actor: ActorDep, settings: Annotated[Settings, Depends(get_settings)],
           session: Annotated[Session, Depends(get_session)]) -> dict:
    if actor.user is not None and actor.session_row is not None:
        accounts.revoke_sessions(session, actor.user.id, only=actor.session_row)
        audit.record(session, actor="owner", action="logout", target=f"user:{actor.user.id}", result="ok", user_id=actor.user.id)
    accounts.clear_cookie(response, settings, settings.session_cookie)
    return {"ok": True}


@router.post("/auth/logout-all")
def logout_all(response: Response, user: Annotated[User, Depends(require_user)],
               settings: Annotated[Settings, Depends(get_settings)],
               session: Annotated[Session, Depends(get_session)]) -> dict:
    n = accounts.revoke_sessions(session, user.id)
    audit.record(session, actor="owner", action="logout_all", target=f"user:{user.id}", result="ok", user_id=user.id,
                 detail=f"{n} session(s) ended")
    accounts.clear_cookie(response, settings, settings.session_cookie)
    return {"ok": True, "ended": n}


# ---------- deleting the account (confirmed by an emailed link) ----------

@router.post("/account/delete-request")
def delete_request(request: Request, user: Annotated[User, Depends(require_user)],
                   settings: Annotated[Settings, Depends(get_settings)],
                   session: Annotated[Session, Depends(get_session)],
                   mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    if accounts.links_today(session, user.email) >= settings.signin_links_per_email_per_day:
        raise HTTPException(status_code=429, detail="You've asked for several emails today. Please try again tomorrow.")
    raw = accounts.issue_token(session, user.email, "delete_account", visitor_id(request))
    out = {"ok": True, "message": "We've emailed you a link to confirm. Nothing is deleted until you use it."}
    out.update(send_link(settings, mailer, session, kind="delete_account", email=user.email, page="account/delete", raw=raw))
    return out


@router.post("/account/delete")
def delete_account(body: Confirm, response: Response, user: Annotated[User, Depends(require_user)],
                   settings: Annotated[Settings, Depends(get_settings)],
                   session: Annotated[Session, Depends(get_session)],
                   server: Annotated[Integrations, Depends(get_integrations)],
                   practice: Annotated[Integrations, Depends(get_practice_integrations)]) -> dict:
    """Unpublish and delete the user's shops, remove memberships and personal data, end every
    session, and keep one anonymous audit record. Needs the emailed link AND being signed in."""
    row = accounts.consume_token(session, body.token, "delete_account", email=user.email)
    if row is None:
        raise HTTPException(status_code=400, detail=EXPIRED)
    if user.role == "admin":
        raise HTTPException(status_code=409, detail="The admin account can't be deleted here.")
    shops = session.exec(select(Business).join(Membership, Membership.business_id == Business.id)
                         .where(Membership.user_id == user.id, Membership.role == "owner")).all()
    for b in shops:
        purge_business(session, settings, for_business(b, server, practice), b)
    user_id = user.id
    from app.models import WatchedAddress

    for w in session.exec(select(WatchedAddress).where(WatchedAddress.user_id == user_id)).all():
        session.delete(w)  # watched addresses go with the account
    accounts.revoke_sessions(session, user_id)
    user.email, user.status, user.status_reason = f"deleted-{user_id}@deleted.invalid", "deleted", ""
    session.add(user)
    session.commit()
    audit.record(session, actor="owner", action="account_deleted", target=f"user:{user_id}", result="ok",
                 detail=f"{len(shops)} shop(s) removed; email erased")  # no email, no shop names
    accounts.clear_cookie(response, settings, settings.session_cookie)
    return {"ok": True}
