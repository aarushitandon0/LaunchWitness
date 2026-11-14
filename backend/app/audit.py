"""One helper for writing audit events."""

from sqlmodel import Session

from app.models import AuditEvent


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    result: str,
    target: str = "",
    detail: str = "",
    business_id: int | None = None,
) -> AuditEvent:
    event = AuditEvent(
        business_id=business_id,
        actor=actor,
        action=action,
        target=target,
        result=result,
        detail=detail,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
