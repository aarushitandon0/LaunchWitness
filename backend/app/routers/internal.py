"""Internal endpoints (called by Caddy on the private network, not exposed publicly)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.sites.hosts import HOSTNAME, business_for_host

router = APIRouter(prefix="/internal", tags=["internal"])


def is_allowed_tls_domain(domain: str, settings: Settings, session: Session) -> bool:
    """True only for the app domain, a seller subdomain in the DB, or a seller domain in the DB."""
    d = domain.strip().lower().rstrip(".")
    if not HOSTNAME.match(d):
        return False
    if d == settings.app_domain.lower().rstrip("."):
        return True
    return business_for_host(d, settings, session) is not None


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
