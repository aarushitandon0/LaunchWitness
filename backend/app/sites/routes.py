"""Public shop pages, chosen by the Host header (see app.sites.hosts).

Only shops that are live and real (not practice) are served here. A draft, a practice shop
and an unknown name all get the same "not set up" page; a paused shop gets a neutral page.
Owners see their own draft/practice shop through the preview route in the API.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.models import Business
from app.safety.access import visitor_id
from app.sites.hosts import business_for_host, normalize_host, subdomain_label
from app.sites.orders import (TOO_MANY, OrderInvalid, TooManyOrders, check_order_limits, existing_order, order_view,
                              parse_order_form, place_order)
from app.sites.render import render_site

router = APIRouter(tags=["seller-site"])


def plain_page(title: str, text: str) -> str:
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>{title}</title>
<body style="font-family:system-ui;max-width:560px;margin:15vh auto;padding:0 16px;color:#1f2937;line-height:1.5">
<h1>{title}</h1><p>{text}</p></body></html>"""


NOT_SET_UP = plain_page("This site isn't set up yet",
                        "Please check the address. If this is your shop, finish setting it up in LaunchWitness.")
NOT_FOUND = plain_page("Page not found", "Please check the address.")
PAUSED = plain_page("This shop is paused", "It isn't taking orders right now. Please check back later.")


def seller_for_request(request: Request, settings: Settings, session: Session) -> tuple[Business, Profile] | None:
    """(business, profile) when the Host is a public shop; None when it's the app itself.

    Raises 404 for any other <label>.APP_DOMAIN, so typos, drafts and practice shops don't show the app."""
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
    b, profile = found
    if b.paused:
        return HTMLResponse(PAUSED, status_code=503)
    if path in ("", "index.html"):
        return HTMLResponse(render_site(profile))
    if path.rstrip("/") == "privacy":
        return HTMLResponse(render_site(profile, page="privacy"))
    return HTMLResponse(NOT_FOUND, status_code=404)


@router.post("/order", response_class=HTMLResponse)
async def submit_order(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    server: Annotated[Integrations, Depends(get_integrations)],
    practice: Annotated[Integrations, Depends(get_practice_integrations)],
):
    try:
        found = seller_for_request(request, settings, session)
    except HTTPException:
        return HTMLResponse(NOT_SET_UP, status_code=404)
    if found is None:
        raise HTTPException(status_code=404)
    business, profile = found
    if business.paused:
        return HTMLResponse(PAUSED, status_code=503)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    token = form.get("order_token", "")
    again = existing_order(session, business, token)
    if again is not None:  # double tap / form sent twice: show the same thank-you, make nothing new
        return HTMLResponse(render_site(profile, page="thanks", order=order_view(again)))
    try:
        data = parse_order_form(form, profile)
    except OrderInvalid as e:
        return HTMLResponse(render_site(profile, form_error=str(e), form_values=form), status_code=422)
    visitor = visitor_id(request)
    try:
        check_order_limits(session, settings, business, visitor)
    except TooManyOrders:
        return HTMLResponse(render_site(profile, form_error=TOO_MANY, form_values=form), status_code=429)
    # The mailer is chosen per business: a practice shop can never reach the real mail server.
    mailer = for_business(business, server, practice).mailer
    place_order(session, mailer, settings, business=business, profile=profile, data=data, visitor=visitor, token=token)
    return HTMLResponse(render_site(profile, page="thanks", order=data))
