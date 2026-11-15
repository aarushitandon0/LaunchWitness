"""Public shop pages, chosen by the Host header (see app.sites.hosts).

Only shops that are live and real (not practice) are served here. A draft, a practice shop
and an unknown name all get the same "not set up" page; a paused shop gets a neutral page.
Owners see their own draft/practice shop through the preview route in the API.
"""

from html import escape
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, func, select

from app import audit
from app.agents.reader import Profile
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import Integrations, for_business, get_integrations, get_practice_integrations
from app.mail.smtp import Mailer, get_mailer
from app.models import Business, ShopReport
from app.safety.access import start_of_today, visitor_id
from app.sites.hosts import business_for_host, normalize_host, subdomain_label
from app.sites.orders import accept_order_form
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


REPORT_REASONS = {"fake": "It pretends to be another shop or brand", "scam": "It looks like a scam",
                  "illegal": "It sells something that isn't allowed", "other": "Something else"}


def report_page(shop: str, message: str = "", done: bool = False) -> str:
    name = escape(shop)
    if done:
        body = ("<p>Thank you. Our team will look at this shop.</p>"
                '<p><a href="/">Back to the shop</a></p>')
    else:
        options = "".join(f'<label style="display:block;margin:6px 0"><input type="radio" name="reason" value="{k}" required> {escape(v)}</label>'
                          for k, v in REPORT_REASONS.items())
        body = (f'{f"<p role=alert style=color:#b91c1c>{escape(message)}</p>" if message else ""}'
                f'<form method="post" action="/report-shop"><p>What is wrong with <strong>{name}</strong>?</p>{options}'
                '<p><label for="note">Anything we should know? (optional)</label><br>'
                '<textarea id="note" name="note" rows="3" maxlength="1000" style="width:100%;font:inherit"></textarea></p>'
                '<div style="position:absolute;left:-9999px" aria-hidden="true"><label>Leave empty <input name="website" tabindex="-1" autocomplete="off"></label></div>'
                '<p><button type="submit" style="font:inherit;padding:10px 18px;border-radius:10px;border:0;background:#1f2937;color:#fff">Send report</button> '
                '<a href="/" style="margin-left:12px">Cancel</a></p></form>'
                "<p style=\"color:#6b7280;font-size:14px\">Reports go to the LaunchWitness team, not to the shop. We don't ask who you are.</p>")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Report this shop</title>
<body style="font-family:system-ui;max-width:560px;margin:8vh auto;padding:0 16px;color:#1f2937;line-height:1.5">
<h1>Report this shop</h1>{body}</body></html>"""


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
        return HTMLResponse(render_site(profile, shop=b.subdomain or str(b.id)))
    if path.rstrip("/") == "privacy":
        return HTMLResponse(render_site(profile, page="privacy"))
    if path.rstrip("/") == "report-shop":
        return HTMLResponse(report_page(profile.name))
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
    # The mailer is chosen per business: a practice shop can never reach the real mail server.
    mailer = for_business(business, server, practice).mailer
    status, html = accept_order_form(session, settings, mailer, business=business, profile=profile, form=form,
                                     visitor=visitor_id(request))
    return HTMLResponse(html, status_code=status)


@router.post("/report-shop", response_class=HTMLResponse)
async def report_shop(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    mailer: Annotated[Mailer, Depends(get_mailer)],
):
    """A visitor reports a public shop. Stored for the team's queue, audited, and emailed to the team."""
    try:
        found = seller_for_request(request, settings, session)
    except HTTPException:
        return HTMLResponse(NOT_SET_UP, status_code=404)
    if found is None:
        raise HTTPException(status_code=404)
    business, profile = found
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    if form.get("website"):  # bot: pretend it worked
        return HTMLResponse(report_page(profile.name, done=True))
    reason = form.get("reason", "")
    if reason not in REPORT_REASONS:
        return HTMLResponse(report_page(profile.name, "Please choose what is wrong."), status_code=422)
    visitor = visitor_id(request)
    today = session.exec(select(func.count()).select_from(ShopReport).where(
        ShopReport.visitor == visitor, ShopReport.created_at >= start_of_today())).one()
    if today >= settings.shop_reports_per_visitor_per_day:
        return HTMLResponse(report_page(profile.name, "You've sent several reports today. Thank you, we have them."),
                            status_code=429)
    row = ShopReport(business_id=business.id, reason=reason, note=form.get("note", "").strip()[:1000], visitor=visitor)
    session.add(row)
    session.commit()
    session.refresh(row)
    audit.record(session, actor="visitor", action="shop_reported", target=f"business:{business.id}", result="ok",
                 business_id=business.id, detail=reason)
    try:
        mailer.send(to=settings.smtp_user, subject=f"[LaunchWitness] Shop reported: {business.subdomain}",
                    body=f"Shop: {profile.name} ({business.subdomain})\nReason: {REPORT_REASONS[reason]}\n"
                         f"Note: {row.note or '(none)'}\n\nOpen the team page to pause the shop or close the report.")
    except Exception as e:  # the report is stored either way
        audit.record(session, actor="system", action="report_email", target=f"report:{row.id}", result="failed",
                     business_id=business.id, detail=type(e).__name__)
    return HTMLResponse(report_page(profile.name, done=True))
