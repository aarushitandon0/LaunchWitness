"""Demo shops: read-only sample shops served by the app itself at /demo/<name>.

Rendered from the saved sample profiles (tests/fixtures/claude/reader_*.json), so they need no
database row and no sign-in. Every page is labelled "Demo shop: orders here are not real", and the
order form places no order: the POST is parsed only to show a friendly "This is a demo" page.
Shop hosts never serve /demo (request_guard), so a demo can't appear under a seller's address.
"""

import json
from functools import cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.agents.reader import Profile
from app.sites.items import group_sizes
from app.sites.orders import OrderInvalid, parse_order_form
from app.sites.render import render_site

router = APIRouter(tags=["demo"])
FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
# S21: eight demo shops, so every one of the six looks has at least one (the landing page's strip links to each).
# The first three are saved Reader replies; the rest are the site-gallery sellers (made-up shops, no real people).
DEMOS = {"meera": "claude/reader_meera_cakes", "imran": "claude/reader_tailor", "sunita": "claude/reader_tiffin_service",
         "sugarcrumb": "site_gallery/cake_studio", "zari": "site_gallery/tailor_studio", "ember": "site_gallery/candle_maker",
         "giftgarden": "site_gallery/gift_hampers", "greencorner": "site_gallery/plant_shop"}
# S14: each demo shop shows the theme (and accent) that fits it.
DEMO_LOOKS = {"meera": ("bakery", "raspberry"), "imran": ("tailor", "navy"), "sunita": ("kitchen", "turmeric"),
              "sugarcrumb": ("bakery", "caramel"), "zari": ("tailor", "thread"), "ember": ("handmade", "clay"),
              "giftgarden": ("gifts", "ruby"), "greencorner": ("general", "forest")}
# S21: each demo's signature (motif, arrangement); none = chosen by code from the shop's name as before, so the three
# older demos look exactly as they did. Every demo has a different motif.
DEMO_SIGNATURES = {"sugarcrumb": ("cherries", "scatter"), "zari": ("buttons", "scatter"), "ember": ("dots", "corner"),
                   "giftgarden": ("ribbons", "scatter"), "greencorner": ("sparks", "corner")}
# S22: the items that take custom requests on each demo (matched in the item's name or its category, lower case). The
# saved Reader replies keep custom = false (nothing is re-captured); a real shop gets it from her words or Review.
DEMO_CUSTOM = {"meera": ("photo print", "theme topper"), "imran": ("stitching",), "zari": ("stitching",),
               "giftgarden": ("hamper",), "sugarcrumb": ("photo cake",)}
HEADERS = {"X-Robots-Tag": "noindex"}


def mark_custom(name: str, products: list) -> list:
    words = DEMO_CUSTOM.get(name, ())
    return [x.model_copy(update={"custom": True}) if any(w in f"{x.name} {x.category}".lower() for w in words) else x
            for x in products]


@cache
def demo_profile(name: str) -> Profile:
    if name not in DEMOS:
        raise HTTPException(status_code=404)
    profile = Profile.model_validate(json.loads((FIXTURES / f"{DEMOS[name]}.json").read_text(encoding="utf-8")))
    # Never point a demo at a real person's phone, WhatsApp or UPI ID, even if a sample gains one later.
    theme, accent = DEMO_LOOKS[name]
    # S21: the same code-side grouping a Reader reply gets ("X ½ kg" + "X 1 kg" -> one item with two sizes)
    return profile.model_copy(update={"phone": "", "whatsapp": "", "upi_id": "", "upi_display_name": "",
                                      "theme": theme, "accent": accent,
                                      "products": mark_custom(name, group_sizes(profile.products))})


@cache
def demo_shop(name: str) -> Profile:
    """S21: what a demo page shows: the sample profile with its own signature, and without anything that could point
    at a real person (no Instagram handle, no pasted customer messages; phone, WhatsApp and UPI are already gone)."""
    motif, art = DEMO_SIGNATURES.get(name, ("", ""))
    return demo_profile(name).model_copy(update={"motif": motif, "art": art, "instagram": "", "testimonials": []})


def page(name: str, which: str = "home", **kw) -> HTMLResponse:
    html = render_site(demo_shop(name), page=which, demo=True, base=f"/demo/{name}", **kw)
    return HTMLResponse(html, headers=HEADERS)


@router.get("/demo/{name}", response_class=HTMLResponse)
def demo_home(name: str) -> HTMLResponse:
    return page(name)


@router.get("/demo/{name}/privacy", response_class=HTMLResponse)
def demo_privacy(name: str) -> HTMLResponse:
    return page(name, "privacy")


@router.get("/demo/{name}/whatsapp", response_class=HTMLResponse)
def demo_whatsapp(name: str) -> HTMLResponse:
    """S22: a demo's WhatsApp button lands here: no number, never opens WhatsApp."""
    return page(name, "whatsapp")


@router.post("/demo/{name}/order", response_class=HTMLResponse)
async def demo_order(name: str, request: Request) -> HTMLResponse:
    """Nothing is stored, emailed or counted. A valid form shows "This is a demo"; an invalid one
    shows the same plain error a real shop would, so the demo behaves like the real thing."""
    from app import payclaims
    from app.sites.routes import read_order_form

    profile = demo_shop(name)
    # S22: the same multipart reader as a real shop; the photo is checked like a real one (so the demo behaves the same)
    # and then dropped: nothing is stored. The parsed form is closed inside read_order_form.
    form, photo, photo_error = await read_order_form(request)
    try:
        data = parse_order_form(form, profile)
        if any(it.get("custom") for it in data["items"]) and (photo or photo_error):
            if photo_error:
                raise OrderInvalid(photo_error)
            try:
                payclaims.process_reference(photo)
            except payclaims.ClaimRefused as e:
                raise OrderInvalid(str(e)) from None
            data["has_ref_photo"] = True
    except OrderInvalid as e:
        return HTMLResponse(render_site(profile, form_error=str(e), form_values=form, demo=True,
                                        base=f"/demo/{name}"), status_code=422, headers=HEADERS)
    data.pop("ref_photo", None)
    return page(name, "thanks", order={**data, "ref": ""})
