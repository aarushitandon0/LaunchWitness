from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    out: dict = {"ok": True, "env": settings.godaddy_env}
    warning = mailbox_warning(settings)
    if warning:
        out["warnings"] = [warning]
    return out


WARN_DAYS = 14


def mailbox_warning(settings: Settings, today: date | None = None) -> str | None:
    """The app's mailbox carries sign-in links, orders and alerts: warn before it lapses."""
    end = settings.mailbox_expires_on
    if end is None:
        return None
    days = (end - (today or date.today())).days
    if days > WARN_DAYS:
        return None
    return (f"The app's mailbox ({settings.smtp_user}) " + (f"lapses in {days} day(s)" if days >= 0 else "has lapsed")
            + ": sign-in links, orders and alerts all depend on it. Renew it.")
