"""Public shop pages, chosen by the Host header (see app.sites.hosts).

Only shops that are live and real (not practice) are served here. A draft, a practice shop
and an unknown name all get the same "not set up" page; a paused shop gets a neutral page.
Owners see their own draft/practice shop through the preview route in the API.
"""

import base64
import hashlib
import re
from html import escape
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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

FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILE = re.compile(r"^[a-z0-9-]+\.woff2$")
SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)


def shop_headers(html: str) -> dict[str, str]:
    """A strict Content-Security-Policy for a public shop page (S14): nothing loads except the shop's own images and
    fonts, styles are inline, and the only scripts that may run are the template's own fixed ones (matched by hash,
    so a script that came from seller data could never run even if it got through escaping)."""
    hashes = " ".join("'sha256-" + base64.b64encode(hashlib.sha256(m.encode()).digest()).decode() + "'"
                      for m in SCRIPT.findall(html))
    csp = ("default-src 'none'; img-src 'self'; font-src 'self'; style-src 'unsafe-inline'; "
           f"script-src {hashes or chr(39) + 'none' + chr(39)}; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
    return {"Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin"}


def shop_response(html: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(html, status_code=status_code, headers=shop_headers(html))


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
    from app.sites.live_contact import public_profile

    return b, public_profile(b)  # S19D: never an unconfirmed WhatsApp / UPI to customers


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
        from app import photos
        from app.sites.orders import full_days

        return shop_response(render_site(profile, shop=b.subdomain or str(b.id), photos=photos.for_site(session, b.id),
                                         full_dates=full_days(session, b, profile)))
    if path.rstrip("/") == "privacy":
        return shop_response(render_site(profile, page="privacy"))
    if path.rstrip("/") == "report-shop":
        return shop_response(report_page(profile.name))
    m = STATUS_PATH.match(path.rstrip("/"))
    if m:  # S20: a real order's own page (the long random token in the link is the permission)
        return status_page(session, b, profile, m.group(1))
    return HTMLResponse(NOT_FOUND, status_code=404)


STATUS_PATH = re.compile(r"^order/([A-Za-z0-9_-]{24,64})$")


def status_page(session: Session, business: Business, profile: Profile, token: str, *, claim_error: str = "",
                code: int = 200) -> HTMLResponse:
    """The thank-you page again, for one order: its UPI details (only here and on the thank-you page), what the customer
    told the shop, and the shop's own update. No store, no cache, not indexed. An unknown token is a plain 404."""
    from app import payclaims
    from app.sites.orders import order_view

    order = payclaims.order_for_token(session, business, token)
    if order is None:
        return HTMLResponse(NOT_FOUND, status_code=404, headers={"Cache-Control": "no-store"})
    html = render_site(profile, page="thanks", order=order_view(order, payclaims.claim_for(session, order.id)),
                       claim_error=claim_error)
    resp = shop_response(html, code)
    resp.headers.update({"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})
    return resp


PHOTO_FILE = re.compile(r"^([0-9a-f]{32})-(\d+)\.webp$")


@router.get("/photos/{file}")
def photo(file: str, request: Request, settings: Annotated[Settings, Depends(get_settings)],
          session: Annotated[Session, Depends(get_session)]) -> Response:
    """S12: a shop's photo. On a shop's own host: only that live shop's photos. On the app's own host: any photo by
    its random 128-bit name (the owner's preview of a draft shows them); nowhere else. Long cache: names never repeat."""
    from app.models import Photo
    from app.photos import CACHE, LARGE_WIDTH, SMALL_WIDTH

    m = PHOTO_FILE.match(file)
    if m is None or int(m.group(2)) not in (SMALL_WIDTH, LARGE_WIDTH):
        raise HTTPException(status_code=404)
    try:
        found = seller_for_request(request, settings, session)
    except HTTPException:
        raise HTTPException(status_code=404) from None
    row = session.exec(select(Photo).where(Photo.name == m.group(1))).first()
    if row is None or (found is not None and (found[0].paused or row.business_id != found[0].id)):
        raise HTTPException(status_code=404)
    body = row.small if int(m.group(2)) == SMALL_WIDTH else row.large
    return Response(body, media_type="image/webp", headers={"Cache-Control": CACHE, "X-Content-Type-Options": "nosniff",
                                                            "Content-Security-Policy": "default-src 'none'"})


@router.get("/shop-assets/fonts/{file}")
def shop_font(file: str) -> Response:
    """S14: the themes' self-hosted fonts (open licence, see docs/FONTS.md). Served on every host (the shop pages and the
    owner's preview). `Access-Control-Allow-Origin: *` because the preview runs in a sandboxed frame (opaque origin)."""
    path = FONT_DIR / file
    if not FONT_FILE.match(file) or not path.is_file():
        raise HTTPException(status_code=404)
    return Response(path.read_bytes(), media_type="font/woff2",
                    headers={"Cache-Control": "public, max-age=604800", "Access-Control-Allow-Origin": "*",
                             "X-Content-Type-Options": "nosniff"})


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
    from app.outbox import channel_of

    integ = for_business(business, server, practice)
    status, html = accept_order_form(session, settings, integ.mailer, business=business, profile=profile, form=form,
                                     visitor=visitor_id(request), channel=channel_of(integ))
    return shop_response(html, status)


@router.post("/order/{token}/paid")
async def submit_payment_claim(
    token: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
    server: Annotated[Integrations, Depends(get_integrations)],
    practice: Annotated[Integrations, Depends(get_practice_integrations)],
):
    """S20 "I've paid": a plain multipart form (no JavaScript). The UTR and one optional screenshot are stored as a CLAIM
    for the owner to check in her own UPI app; nothing here says "paid" or "verified"."""
    from app import payclaims
    from app.outbox import channel_of

    try:
        found = seller_for_request(request, settings, session)
    except HTTPException:
        return HTMLResponse(NOT_SET_UP, status_code=404)
    if found is None:
        raise HTTPException(status_code=404)
    business, profile = found
    if business.paused:
        return HTMLResponse(PAUSED, status_code=503)
    order = payclaims.order_for_token(session, business, token)
    if order is None:
        return HTMLResponse(NOT_FOUND, status_code=404, headers={"Cache-Control": "no-store"})
    try:
        declared = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        declared = 0
    if declared > payclaims.MAX_BODY_BYTES:  # refused before the body is read
        return status_page(session, business, profile, token, code=413,
                           claim_error="That screenshot is too big. Please use one under 4 MB, or leave it out.")
    form = await request.form()
    text = form.get("utr")
    shot = form.get("screenshot")
    data = None
    if shot is not None and not isinstance(shot, str):
        data = await shot.read(payclaims.MAX_SHOT_BYTES + 1)
    integ = for_business(business, server, practice)
    try:
        payclaims.submit(session, settings, integ.mailer, business=business, profile=profile, order=order,
                         utr_text=text if isinstance(text, str) else "", screenshot=data or None,
                         visitor=visitor_id(request), channel=channel_of(integ))
    except payclaims.ClaimRefused as e:
        return status_page(session, business, profile, token, claim_error=str(e), code=e.status if e.status != 404 else 422)
    return RedirectResponse(f"/order/{token}#claim", status_code=303)


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
