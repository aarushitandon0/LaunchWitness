"""Internal endpoints (called by Caddy on the private network, not exposed publicly)."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Business

router = APIRouter(prefix="/internal", tags=["internal"])

_HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


def is_allowed_tls_domain(domain: str, settings: Settings, session: Session) -> bool:
    """True only for the app domain, a seller subdomain in the DB, or a seller domain in the DB."""
    d = domain.strip().lower().rstrip(".")
    if not _HOSTNAME.match(d):
        return False
    app_domain = settings.app_domain.lower().rstrip(".")
    if d == app_domain:
        return True
    suffix = "." + app_domain
    if d.endswith(suffix):
        label = d[: -len(suffix)]
        if "." in label:
            return False
        return session.exec(select(Business.id).where(Business.subdomain == label)).first() is not None
    return session.exec(select(Business.id).where(Business.domain == d)).first() is not None


@router.get("/tls-ask")
def tls_ask(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    domain: Annotated[str, Query(max_length=253)] = "",
) -> dict:
    """Caddy on-demand TLS `ask` hook: 200 = issue a certificate, anything else = refuse."""
    if not is_allowed_tls_domain(domain, settings, session):
        raise HTTPException(status_code=404, detail="unknown domain")
    return {"ok": True}
