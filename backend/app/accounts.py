"""Accounts: emailed sign-in links, server-side sessions, the admin user, guest workspaces.

No passwords anywhere. A sign-in link carries 32 random bytes; only its SHA-256 is
stored; it works once, for 15 minutes. The link opens a page with a "Sign in" button
that POSTs the token: merely opening the link (as mail scanners do) uses nothing up.
"""

import re
import secrets
from datetime import timedelta
from html import escape

from fastapi import Response
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app import audit
from app.config import Settings
from app.models import Business, LoginToken, Membership, User, UserSession, utcnow
from app.safety.access import aware, sha, start_of_today

TOKEN_MINUTES = 15
EMAIL = re.compile(r"^[^@\s<>\"',;:\\]+@[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
NEXT = re.compile(r"^#/[A-Za-z0-9/_-]{0,120}$")  # a page inside our own app, nothing else
DEFAULT_NEXT = "#/shops"
SAME_ANSWER = "If that address can sign in, we've sent it a link. It works for 15 minutes."


def normalize_email(value: str) -> str | None:
    email = (value or "").strip().lower()
    return email if len(email) <= 254 and EMAIL.match(email) else None


def safe_next(value: str | None) -> str:
    """Where to go after signing in: only a page of this app (a `#/…` route). Anything else,
    including full URLs and `//host` tricks, becomes the default, so there's no open redirect."""
    return value if value and NEXT.match(value) else DEFAULT_NEXT


# ---------- emailed links ----------

def links_today(session: Session, email: str) -> int:
    return session.exec(select(func.count()).select_from(LoginToken).where(
        LoginToken.email == email, LoginToken.created_at >= start_of_today())).one()


def links_last_hour(session: Session, visitor: str) -> int:
    return session.exec(select(func.count()).select_from(LoginToken).where(
        LoginToken.visitor == visitor, LoginToken.created_at >= utcnow() - timedelta(hours=1))).one()


def issue_token(session: Session, email: str, purpose: str, visitor: str = "") -> str:
    raw = secrets.token_urlsafe(32)
    session.add(LoginToken(token_hash=sha(raw), email=email, purpose=purpose, visitor=visitor,
                           expires_at=utcnow() + timedelta(minutes=TOKEN_MINUTES)))
    session.commit()
    return raw


def consume_token(session: Session, raw: str, purpose: str, email: str | None = None) -> LoginToken | None:
    """Use the token up. Returns it only the FIRST time, and only if it hasn't expired. With `email`,
    a token issued to another address is refused WITHOUT being used up (so nobody can burn your link)."""
    if not raw or len(raw) > 200:
        return None
    row = session.exec(select(LoginToken).where(LoginToken.token_hash == sha(raw), LoginToken.purpose == purpose)).first()
    if row is None or row.used_at is not None or aware(row.expires_at) <= utcnow():
        return None
    if email is not None and row.email != email:
        return None
    done = session.exec(update(LoginToken).where(LoginToken.id == row.id, LoginToken.used_at == None)  # noqa: E711
                        .values(used_at=utcnow()))
    session.commit()
    if done.rowcount != 1:  # someone else used it in the same instant
        return None
    session.refresh(row)
    return row


def link_url(settings: Settings, page: str, raw: str, next_: str = "") -> str:
    url = f"{settings.app_base_url.rstrip('/')}/#/{page}?token={raw}"
    return url + (f"&next={next_[2:]}" if next_ and next_ != DEFAULT_NEXT else "")


def link_email(kind: str, url: str) -> tuple[str, str, str]:
    """(subject, plain text, simple HTML) for a sign-in or delete-account link."""
    if kind == "login":
        subject, lead, button = "Your LaunchWitness sign-in link", "Tap the button to sign in to LaunchWitness.", "Sign in"
        tail = "If you didn't ask for this, you can ignore this email. Nobody can sign in without this link."
    else:
        subject, lead, button = ("Confirm deleting your LaunchWitness account",
                                 "Tap the button to confirm that you want to delete your LaunchWitness account.",
                                 "Review and delete")
        tail = "If you didn't ask for this, ignore this email and nothing will be deleted."
    text = f"{lead}\n\n{url}\n\nThe link works once, for {TOKEN_MINUTES} minutes.\n{tail}\n\n- LaunchWitness"
    html = (f'<div style="font-family:system-ui,Arial,sans-serif;font-size:16px;line-height:1.5;color:#1f2937;max-width:480px">'
            f"<p>{escape(lead)}</p>"
            f'<p><a href="{escape(url, quote=True)}" style="display:inline-block;padding:12px 20px;border-radius:10px;'
            f'background:#1f2937;color:#ffffff;text-decoration:none;font-weight:600">{button}</a></p>'
            f"<p>The link works once, for {TOKEN_MINUTES} minutes.<br>{escape(tail)}</p>"
            f'<p style="color:#6b7280;font-size:14px">If the button doesn\'t work, copy this address into your browser:<br>'
            f"{escape(url)}</p><p>- LaunchWitness</p></div>")
    return subject, text, html


# ---------- sessions ----------

def create_session(session: Session, settings: Settings, user: User, user_agent: str) -> str:
    """A brand-new session id at every sign-in (nothing from before the sign-in is reused)."""
    raw = secrets.token_urlsafe(32)
    session.add(UserSession(token_hash=sha(raw), user_id=user.id, user_agent=(user_agent or "")[:200],
                            expires_at=utcnow() + timedelta(days=settings.session_days)))
    user.last_login_at = utcnow()
    session.add(user)
    session.commit()
    return raw


def cookie_flags(settings: Settings) -> dict:
    # Host-only (no Domain attribute): never sent to shop subdomains. `__Host-` also requires Secure + Path=/.
    return {"httponly": True, "samesite": "lax", "path": "/", "secure": not settings.dev_mode}


def set_session_cookie(response: Response, settings: Settings, raw: str) -> None:
    response.set_cookie(settings.session_cookie, raw, max_age=settings.session_days * 86400, **cookie_flags(settings))


def set_guest_cookie(response: Response, settings: Settings, raw: str) -> None:
    response.set_cookie(settings.guest_cookie, raw, max_age=86400, **cookie_flags(settings))


def clear_cookie(response: Response, settings: Settings, name: str) -> None:
    response.delete_cookie(name, **cookie_flags(settings))


def revoke_sessions(session: Session, user_id: int, only: UserSession | None = None) -> int:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked == False)  # noqa: E712
    if only is not None:
        q = q.where(UserSession.id == only.id)
    done = session.exec(q.values(revoked=True))
    session.commit()
    return done.rowcount


# ---------- users ----------

def find_user(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == email)).first()


def user_for_login(session: Session, settings: Settings, email: str) -> User:
    """The account for a proven email address; created on first sign-in (pending, or the admin)."""
    user = find_user(session, email)
    if user is None:
        is_admin = bool(settings.admin_email) and email == normalize_email(settings.admin_email)
        user = User(email=email, status="approved" if is_admin else "pending", role="admin" if is_admin else "seller")
        session.add(user)
        session.commit()
        session.refresh(user)
        audit.record(session, actor="system", action="user_created", target=f"user:{user.id}", result="ok",
                     user_id=user.id, detail="admin" if is_admin else "pending approval")
    return user


def ensure_admin(engine: Engine, settings: Settings) -> None:
    """At startup: the ADMIN_EMAIL account exists, is approved and has the admin role."""
    email = normalize_email(settings.admin_email)
    if not email:
        return
    with Session(engine) as s:
        user = find_user(s, email)
        if user is None:
            user = User(email=email)
        if (user.status, user.role) != ("approved", "admin"):
            user.status, user.role = "approved", "admin"
            s.add(user)
            s.commit()
            audit.record(s, actor="system", action="admin_ensured", target=f"user:{user.id}", result="ok", user_id=user.id)


def shops_of(session: Session, user_id: int) -> int:
    return session.exec(select(func.count()).select_from(Membership).where(Membership.user_id == user_id)).one()


def adopt_guest_shops(session: Session, settings: Settings, user: User, guest_hash: str) -> int:
    """Signing in keeps the practice workspace: the guest's shops become the account's (up to the per-user limit)."""
    if not guest_hash:
        return 0
    room = max(0, settings.max_shops_per_user - shops_of(session, user.id)) if user.role != "admin" else 10**6
    moved = 0
    for b in session.exec(select(Business).where(Business.guest_hash == guest_hash).order_by(Business.id.desc())).all():
        if moved >= room:
            break
        b.guest_hash = ""
        session.add(b)
        session.add(Membership(user_id=user.id, business_id=b.id, role="owner"))
        moved += 1
        audit.record(session, actor="owner", action="workspace_kept", target=f"business:{b.id}", result="ok",
                     business_id=b.id, user_id=user.id, detail="practice shop moved to the account at sign-in")
    session.commit()
    return moved
