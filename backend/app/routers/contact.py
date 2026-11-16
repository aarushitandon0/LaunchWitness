"""Contact form on the app's own landing page (hackathon requirement, M1).

Sends to the app mailbox (SMTP_USER) through the Mailer: SMTP over SSL to
smtpout.secureserver.net with the full address as username and the password
from env only. Per-visitor daily limit; honeypot field against bots; audited.
"""

import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app import audit
from app.config import Settings, get_settings
from app.db import get_session
from app.mail.smtp import Mailer, get_mailer
from app.models import AuditEvent
from app.safety.access import start_of_today, visitor_id

router = APIRouter(prefix="/api", tags=["contact"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContactForm(BaseModel):
    name: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=254)
    message: str = Field(default="", max_length=3000)
    website: str = Field(default="", max_length=200)  # honeypot: humans leave it empty


def sent_today(session: Session, visitor: str) -> int:
    q = select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "contact_form", AuditEvent.target == visitor, AuditEvent.result == "sent",
        AuditEvent.created_at >= start_of_today())
    return session.exec(q).one()


@router.post("/contact")
def contact(body: ContactForm, request: Request, settings: Annotated[Settings, Depends(get_settings)],
            session: Annotated[Session, Depends(get_session)],
            mailer: Annotated[Mailer, Depends(get_mailer)]) -> dict:
    name, email, message = body.name.strip(), body.email.strip(), body.message.strip()
    if body.website:  # bot: pretend it worked, send nothing
        audit.record(session, actor="visitor", action="contact_form", target="honeypot", result="dropped")
        return {"ok": True, "message": "Thank you! Your message was sent. We'll reply by email."}
    if not name or not message:
        raise HTTPException(status_code=422, detail="Please add your name and a message.")
    if not EMAIL.match(email):
        raise HTTPException(status_code=422, detail="That email address doesn't look right. Please check it, "
                            "so we can reply.")
    visitor = visitor_id(request)
    if sent_today(session, visitor) >= settings.visitor_contacts_per_day:
        raise HTTPException(status_code=429, detail="You've sent us several messages today. "
                            "We'll reply soon — please try again tomorrow if it's urgent.")
    subject = f"[LaunchWitness contact] {name[:60]}"
    text = f"From: {name} <{email}>\n\n{message}\n\n— sent from the LaunchWitness contact form"
    from app import outbox

    # S13: the message is kept in the outbox, so a mail outage never loses it (the outbox keeps trying)
    row = outbox.send(session, settings, mailer, kind="contact", key=f"contact:{secrets.token_hex(12)}",
                      to=settings.smtp_user, subject=subject, body=text)
    if row.status != "sent":
        audit.record(session, actor="visitor", action="contact_form", target=visitor, result="queued",
                     detail=f"outbox:{row.id} {row.last_error}")
        return {"ok": True, "message": "Thank you! We have your message. Our email is slow right now, so it may "
                "take a little while to reach us; we'll reply by email."}
    audit.record(session, actor="visitor", action="contact_form", target=visitor, result="sent",
                 detail=f"to app mailbox, {len(message)} chars")
    return {"ok": True, "message": "Thank you! Your message was sent. We'll reply by email."}
