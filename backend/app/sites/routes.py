"""Seller site pages, chosen by the Host header (see app.sites.hosts)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.mail.smtp import Mailer, get_mailer
from app.models import Business
from app.sites.hosts import business_for_host, normalize_host, subdomain_label
from app.sites.orders import OrderInvalid, parse_order_form, place_order
from app.sites.render import render_site

router = APIRouter(tags=["seller-site"])

NOT_SET_UP = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site not found</title><body style="font-family:system-ui;max-width:560px;margin:15vh auto;padding:0 16px;color:#1f2937">
<h1>This site isn't set up yet</h1><p>Please check the address. If this is your shop, finish setting it up in LaunchWitness.</p></body>"""


def seller_for_request(request: Request, settings: Settings, session: Session) -> tuple[Business, Profile] | None:
    """(business, profile) when the Host is a seller site; None when it's the app itself.

    Raises 404 for an unknown <label>.APP_DOMAIN, so typos don't show the app."""
    host = request.headers.get("host", "")
    b = business_for_host(host, settings, session)
    if b is None:
        if subdomain_label(normalize_host(host), settings) is not None:
            raise HTTPException(status_code=404, detail="site not set up")
        return None
    return b, Profile.model_validate_json(b.profile_json)


def seller_page(path: str, request: Request, settings: Settings, session: Session) -> HTMLResponse | None:
    try:
        found = seller_for_request(request, settings, session)
    except HTTPException:
        return HTMLResponse(NOT_SET_UP, status_code=404)
    if found is None:
        return None
    _b, profile = found
    if path in ("", "index.html"):
        return HTMLResponse(render_site(profile))
    if path.rstrip("/") == "privacy":
        return HTMLResponse(render_site(profile, page="privacy"))
    return HTMLResponse(NOT_SET_UP.replace("This site isn't set up yet", "Page not found"), status_code=404)


@router.post("/order", response_class=HTMLResponse)
async def submit_order(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
):
    found = seller_for_request(request, settings, session)
    if found is None:
        raise HTTPException(status_code=404)
    business, profile = found
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    try:
        data = parse_order_form(form, profile)
    except OrderInvalid as e:
        return HTMLResponse(render_site(profile, form_error=str(e), form_values=form), status_code=422)
    place_order(session, mailer, business=business, profile=profile, data=data, mail_to=settings.smtp_user)
    return HTMLResponse(render_site(profile, page="thanks", order=data))
