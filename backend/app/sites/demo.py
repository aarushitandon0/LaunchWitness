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
FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "claude"
DEMOS = {"meera": "reader_meera_cakes", "imran": "reader_tailor", "sunita": "reader_tiffin_service"}
# S14: each demo shop shows the theme that fits it (the same choice the Reader fixtures carry).
DEMO_LOOKS = {"meera": ("bakery", "raspberry"), "imran": ("tailor", "navy"), "sunita": ("kitchen", "turmeric")}
HEADERS = {"X-Robots-Tag": "noindex"}


@cache
def demo_profile(name: str) -> Profile:
    if name not in DEMOS:
        raise HTTPException(status_code=404)
    profile = Profile.model_validate(json.loads((FIXTURES / f"{DEMOS[name]}.json").read_text(encoding="utf-8")))
    # Never point a demo at a real person's phone, WhatsApp or UPI ID, even if a sample gains one later.
    theme, accent = DEMO_LOOKS[name]
    # S21: the same code-side grouping a Reader reply gets ("X ½ kg" + "X 1 kg" -> one item with two sizes)
    return profile.model_copy(update={"phone": "", "whatsapp": "", "upi_id": "", "upi_display_name": "",
                                      "theme": theme, "accent": accent, "products": group_sizes(profile.products)})


def page(name: str, which: str = "home", **kw) -> HTMLResponse:
    html = render_site(demo_profile(name), page=which, demo=True, base=f"/demo/{name}", **kw)
    return HTMLResponse(html, headers=HEADERS)


@router.get("/demo/{name}", response_class=HTMLResponse)
def demo_home(name: str) -> HTMLResponse:
    return page(name)


@router.get("/demo/{name}/privacy", response_class=HTMLResponse)
def demo_privacy(name: str) -> HTMLResponse:
    return page(name, "privacy")


@router.post("/demo/{name}/order", response_class=HTMLResponse)
async def demo_order(name: str, request: Request) -> HTMLResponse:
    """Nothing is stored, emailed or counted. A valid form shows "This is a demo"; an invalid one
    shows the same plain error a real shop would, so the demo behaves like the real thing."""
    profile = demo_profile(name)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    try:
        data = parse_order_form(form, profile)
    except OrderInvalid as e:
        return HTMLResponse(render_site(profile, form_error=str(e), form_values=form, demo=True,
                                        base=f"/demo/{name}"), status_code=422, headers=HEADERS)
    return page(name, "thanks", order={**data, "ref": ""})
