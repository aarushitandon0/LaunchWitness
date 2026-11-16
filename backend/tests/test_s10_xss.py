"""S10 Part D: hostile text in EVERY field a seller (or customer) controls never becomes markup or script."""

import re  # noqa: F401
from html.parser import HTMLParser

from sqlmodel import Session

from app.agents.reader import Product, Profile
from app.models import Business
from app.sites.render import render_site

EVIL = '"><script>alert(1)</script><img src=x onerror=alert(2)>'
SHORT = '"><svg onload=1>'  # for the 20-character fields


def hostile_profile() -> Profile:
    return Profile(
        name=EVIL, tagline=EVIL, about=EVIL, area=EVIL[:120], hours=EVIL, phone="+91 98765 43210",
        whatsapp="+91 98765 43210", upi_id="evil@upi", tone=SHORT, selling_point=SHORT, upi_display_name=EVIL[:60],
        fssai_number="12345678901234",
        pickup_available=True, delivery_available=True, delivery_fee_inr=50, allow_item_message=True,
        products=[Product(name=EVIL, price_inr=100, description=EVIL, category=EVIL[:60]),
                  Product(name=EVIL + "x", price_inr=50, description=EVIL, category=EVIL[:60], addon=True)],
    )


def test_structured_fields_refuse_markup_outright():
    import pytest
    from pydantic import ValidationError

    base = {"name": "Ok", "products": [{"name": "Cake", "price_inr": 1}]}
    for field, value in (("phone", SHORT), ("whatsapp", SHORT), ("upi_id", "evil@upi" + SHORT), ("fssai_number", SHORT)):
        with pytest.raises(ValidationError):
            Profile.model_validate({**base, field: value})


class Elements(HTMLParser):
    """What a browser would actually build: element names and their attributes."""

    def __init__(self, html: str):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def assert_parsed_inert(html: str, scripts: int) -> None:
    tags = Elements(html).tags
    assert sum(t == "script" for t, _ in tags) <= scripts, "a <script> element came from the data"
    assert not [t for t, _ in tags if t in ("img", "iframe", "object", "embed")] or all(
        a.get("src", "").startswith(("data:", "/", "https://")) for t, a in tags if t == "img"), "an injected element"
    for t, a in tags:
        assert not [k for k in a if k.startswith("on")], f"event handler on <{t}>"
        for k in ("href", "src", "action"):
            assert not str(a.get(k) or "").strip().lower().startswith("javascript:"), f"javascript: in <{t} {k}>"


def assert_inert(html: str) -> None:
    assert_parsed_inert(html, scripts=1)  # at most the template's own basket script
    assert "alert(" not in html.split("<script>")[-1].split("</script>")[0] or "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html or "&#34;&gt;&lt;script" in html  # shown as text


def test_every_profile_field_is_escaped_on_every_page():
    p = hostile_profile()
    order = {"code": "LW-1", "items": [{"name": EVIL, "qty": 1, "price_inr": 100}], "total_inr": 100,
             "customer_name": EVIL, "customer_phone": SHORT, "note": EVIL, "item_message": EVIL}
    for page in ("home", "privacy"):
        assert_inert(render_site(p, page=page, shop=EVIL))
    assert_inert(render_site(p, page="thanks", order=order, shop="ok"))
    # A refused order comes back with the customer's own (hostile) values in the form.
    assert_inert(render_site(p, form_error=EVIL, form_values={"customer_name": EVIL, "note": EVIL, "item_message": EVIL,
                                                               "qty_0": EVIL, "order_token": EVIL}))


def test_hostile_shop_on_the_shared_report_page(client, engine):
    from tests.test_m3_launch import approve, meera, plan

    biz = meera(client)
    approve(client, plan(client, biz))
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.name = EVIL
        s.add(b)
        s.commit()
    url = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]
    html = client.get("/r/" + url.rsplit("/r/", 1)[1]).text
    from app.routers.proof import VERIFY_JS

    assert html.count("<script>") == 1 and VERIFY_JS in html  # S12: our own fixed Verify script, nothing from data
    assert_parsed_inert(html.replace(VERIFY_JS, ""), scripts=0)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html  # shown as text
