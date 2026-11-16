"""Internal endpoints (called by Caddy on the private network, not exposed publicly)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.checks.dns_resolver import points_here
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, get_integrations
from app.sites.hosts import HOSTNAME, business_for_host

router = APIRouter(prefix="/internal", tags=["internal"])


def is_allowed_tls_domain(domain: str, settings: Settings, session: Session, integ: Integrations | None = None) -> bool:
    """True only for the app domain and for shops that are live, real (not practice) and not paused.

    A shop becomes live only after every nameserver answered with our server (executor `wait_dns`), so a yes here
    means Let's Encrypt can validate. On a real server we ask the nameservers once more before saying yes: if the
    record has gone since (or one nameserver disagrees), a certificate attempt would only burn one of Let's
    Encrypt's 5 failed validations per name per hour, so the answer is no until DNS is right again."""
    d = domain.strip().lower().rstrip(".")
    if not HOSTNAME.match(d):
        return False
    if d == settings.app_domain.lower().rstrip("."):
        return True
    b = business_for_host(d, settings, session)  # only live, non-practice shops
    if b is None or b.paused:
        return False
    if integ is not None and not integ.fake:
        return points_here(integ.dns, d, settings.server_ip)
    return True


@router.get("/tls-ask")
def tls_ask(
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    integ: Annotated[Integrations, Depends(get_integrations)],
    domain: Annotated[str, Query(max_length=253)] = "",
) -> dict:
    """Caddy on-demand TLS `ask` hook: 200 = issue a certificate, anything else = refuse."""
    if not is_allowed_tls_domain(domain, settings, session, integ):
        raise HTTPException(status_code=404, detail="unknown domain")
    return {"ok": True}
