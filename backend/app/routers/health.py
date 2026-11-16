from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.models import AuditEvent, utcnow
from app.safety.access import ActorDep
from app.selfcheck import mailbox_warning, warnings  # noqa: F401  (mailbox_warning: re-exported for callers)

router = APIRouter(prefix="/api", tags=["health"])


def unsent_alerts(session: Session) -> int:
    """Alert emails that couldn't be sent in the last day and haven't gone out since (our mail service was down)."""
    since = utcnow() - timedelta(days=1)
    rows = session.exec(select(AuditEvent).where(AuditEvent.actor == "monitor", AuditEvent.created_at >= since,
                                                 AuditEvent.result.in_(("failed", "sent")),
                                                 AuditEvent.action.like("%alert%")).order_by(AuditEvent.id)).all()
    last = {(e.action, e.target, e.business_id, e.user_id): e.result for e in rows}
    return sum(1 for result in last.values() if result == "failed")


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)], actor: ActorDep,
           session: Annotated[Session, Depends(get_session)]) -> dict:
    """Liveness + the startup self-check. Anyone sees the harmless warnings; the admin sees all of them.
    Never a secret value."""
    out: dict = {"ok": True, "env": settings.godaddy_env}
    found = [w for w in warnings(settings) if w.public or actor.is_admin]
    texts, codes = [w.text for w in found], [w.code for w in found]
    unsent = unsent_alerts(session) if actor.is_admin else 0
    if unsent:
        texts.append(f"{unsent} alert email{'s' if unsent != 1 else ''} couldn't be sent in the last day (our mail "
                     "service refused or was unreachable). Each is tried again on the next monitoring round.")
        codes.append("alerts_unsent")
    if texts:
        out["warnings"], out["warning_codes"] = texts, codes
    return out
