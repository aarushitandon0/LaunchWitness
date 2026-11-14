"""Session 8: one generic shop template for every seller, the basket, new profile fields, and the scope guard."""

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.agents.reader import PROFILE_SCHEMA, Product, Profile, tidy_profile
from app.models import AuditEvent, Business, Order
from app.sites.render import badges, group_products, monogram, render_site
from tests.test_m2_site import MEERA, create, order_form, save

FIX = Path(__file__).parent / "fixtures"
GALLERY = sorted((FIX / "site_gallery").glob("*.json"))
TEMPLATE = Path(__file__).parents[1] / "app" / "sites" / "templates" / "seller.html"


def gallery(name: str) -> Profile:
    return Profile.model_validate(json.loads((FIX / "site_gallery" / f"{name}.json").read_text(encoding="utf-8")))


def base(**kw) -> Profile:
    return Profile(name="Test Shop", products=[Product(name="Thing", price_inr=100)], **kw)


# ---------- The gallery: very different sellers, one template ----------

def test_gallery_has_six_very_different_sellers():
    names = {p.stem for p in GALLERY}
    assert {"bakery", "tailor", "tiffin", "candles", "big_menu", "hinglish_long"} <= names
    assert len(gallery("candles").products) == 2
    big = gallery("big_menu")
    assert len(big.products) >= 40 and {x.category for x in big.products} == {"Menu"}
    long = gallery("hinglish_long")
    assert not (long.phone or long.whatsapp or long.upi_id) and max(len(x.name) for x in long.products) > 60
    assert any(x.price_from for x in gallery("tailor").products)


@pytest.mark.parametrize("path", GALLERY, ids=lambda p: p.stem)
def test_every_gallery_seller_renders_cleanly(path):
    p = Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    for page in ("home", "privacy", "thanks"):
        html = render_site(p, page=page, order={"customer_name": "Asha", "items": [], "total_inr": 0, "note": ""})
        assert "verified" not in html.lower()
        assert "None" not in re.sub(r"<script.*?</script>", "", html, flags=re.S)
    html = render_site(p)
    for i, item in enumerate(p.products):  # every item appears exactly once, with its own quantity box
        assert html.count(f'name="qty_{i}"') == 1
    assert ("WhatsApp" in html) == bool(p.whatsapp or p.phone)
    assert ('id="pay"' in html) == bool(p.upi_id)


def test_template_has_nothing_specific_to_one_seller_or_trade():
    src = TEMPLATE.read_text(encoding="utf-8").lower()
    for word in ("meera", "cake", "bake", "eggless", "tiffin", "tailor", "candle", "pickle", "verified"):
        assert word not in src, word


def test_no_per_business_css():
    """Every seller gets the same stylesheet; only the content changes."""
    styles = {re.search(r"<style>.*?</style>", render_site(gallery(p.stem)), re.S).group(0) for p in GALLERY}
    assert len(styles) == 1


def test_category_colours_come_from_fixed_palette_by_position():
    p = base()
    p.products = [Product(name=f"Item {i}", price_inr=10, category=f"Group {i}") for i in range(8)]
    html = render_site(p)
    for i in range(8):
        assert f'<div class="cat c{i % 6}" id="cat-{i}">' in html


def test_long_lists_get_two_columns_and_search():
    html = render_site(gallery("big_menu"))
    assert 'class="items dense"' in html and 'id="find"' in html
    small = render_site(gallery("candles"))
    assert "items dense" not in small and 'id="find"' not in small


# ---------- Badges: only from data, never filler ----------

def test_badges_come_only_from_profile_data():
    assert badges(base()) == []
    assert badges(base(selling_point="100% eggless", min_notice_days=2, pickup_available=True,
                       delivery_available=True)) == ["100% eggless", "Order 2 days ahead", "Pickup or delivery"]
    assert badges(base(min_notice_days=1)) == ["Order 1 day ahead"]
    assert badges(base(pickup_available=True)) == ["Pickup available"]
    assert badges(base(delivery_available=True)) == ["Delivery available"]
    assert 'class="badges"' not in render_site(base())


def test_monogram():
    assert monogram("Meera's Eggless Bakes") == "ME"
    assert monogram("Wick & Wax by Kavya") == "WW"
    assert monogram("The Chai Stop") == "CS"
    assert monogram("!!!") == "•"


def test_area_not_repeated_in_header_when_tagline_says_it():
    p = base(tagline="Fresh cakes from Baner, Pune", area="Baner, Pune")
    hero = render_site(p).split('<div class="hero">')[1].split('<form class="layout"')[0]
    assert hero.count("Baner, Pune") == 1
    p2 = base(tagline="Fresh cakes", area="Baner, Pune")
    assert "Baner, Pune" in render_site(p2).split('<div class="hero">')[1].split('<form class="layout"')[0]


# ---------- New profile fields ----------

def test_upi_display_name_and_fssai_shown_without_verified_label():
    p = base(upi_id="shop@okaxis", upi_display_name="TEST SHOP", fssai_number="12345678901234")
    html = render_site(p)
    assert "Your UPI app should show: <strong>TEST SHOP</strong>" in html
    assert "FSSAI licence no. 12345678901234" in html.split("<footer>")[1]
    assert "verified" not in html.lower()


@pytest.mark.parametrize("bad", ["1234", "abcdefghijklmn", "123456789012345"])
def test_fssai_number_must_be_14_digits(bad):
    with pytest.raises(ValueError):
        base(fssai_number=bad)
    assert base(fssai_number="1234 5678 9012 34").fssai_number == "12345678901234"


def test_old_saved_profiles_still_load():
    """Businesses saved before session 8 have no new keys."""
    p = Profile.model_validate({"name": "Old", "products": [{"name": "A", "price_inr": 5, "description": "", "category": "X"}]})
    assert p.kind == "orders" and p.min_notice_days == 0 and not p.allow_item_message
    assert badges(p) == []


def test_reader_schema_lists_every_profile_field():
    assert set(PROFILE_SCHEMA["required"]) == set(Profile.model_fields)
    assert set(PROFILE_SCHEMA["properties"]["products"]["items"]["required"]) == set(Product.model_fields)


# ---------- Tidy-up of Reader replies (plain code) ----------

def meera_live() -> Profile:
    return Profile.model_validate(json.loads((FIX / "claude" / "reader_meera_cakes.json").read_text(encoding="utf-8")))


def test_tidy_moves_delivery_out_of_the_menu_and_reads_notice():
    raw = meera_live()
    assert any("delivery" in x.name.lower() for x in raw.products)
    p = tidy_profile(raw)
    assert not any("delivery" in x.name.lower() for x in p.products)
    assert p.delivery_available and p.delivery_fee_inr == 80 and p.pickup_available
    assert p.min_notice_days == 2
    assert "order" not in p.hours.lower() and "10am to 8pm" in p.hours
    extras = [x.name for x in p.products if x.addon]
    assert extras == ["Photo print on cake", "Theme topper"]
    topper = next(x for x in p.products if x.name == "Theme topper")
    assert topper.price_from and topper.description == ""  # "Price starts from ₹300" would just repeat it
    assert tidy_profile(p) == p  # running it again changes nothing


def test_tidy_keeps_a_profile_that_is_only_extras():
    p = base()
    p.products = [Product(name="Gift wrap", price_inr=30, category="Add-ons")]
    assert tidy_profile(p).products  # never leaves an empty menu


def test_tidy_does_not_override_what_reader_set():
    p = base(delivery_available=True, delivery_fee_inr=50, min_notice_days=3, hours="9 to 5. Order 1 day before.")
    p.products.append(Product(name="Delivery", price_inr=99, category="Delivery"))
    t = tidy_profile(p)
    assert t.delivery_fee_inr == 50 and t.min_notice_days == 3 and t.hours == "9 to 5."


# ---------- Ordering: basket, extras, item message, server-side totals ----------

def test_extras_cannot_be_ordered_alone_and_totals_come_from_the_menu(client, engine):
    biz = create(client)
    save(client, biz)
    products = biz["profile"]["products"]
    extra = next(i for i, x in enumerate(products) if x["addon"])
    item = next(i for i, x in enumerate(products) if not x["addon"])
    base_form = {k: v for k, v in order_form().items() if not k.startswith("qty_")}
    r = client.post("/order", data={**base_form, f"qty_{extra}": "1"}, headers={"host": MEERA})
    assert r.status_code == 422 and "Extras go with another item" in r.text
    # Prices sent by the browser are ignored: the total is worked out from the menu.
    r = client.post("/order", data={**base_form, f"qty_{extra}": "1", f"qty_{item}": "2",
                                    "price_inr": "1", "total_inr": "1"}, headers={"host": MEERA})
    assert r.status_code == 200
    with Session(engine) as s:
        order = s.exec(select(Order)).one()
    assert order.total_inr == 2 * products[item]["price_inr"] + products[extra]["price_inr"]


def test_item_message_only_when_seller_allows_it(client, engine):
    biz = create(client)
    save(client, biz)
    form = {**order_form(), "item_message": "Happy Birthday Riya"}
    assert 'id="item_message"' not in client.get("/", headers={"host": MEERA}).text
    client.post("/order", data=form, headers={"host": MEERA})
    save(client, biz, allow_item_message=True)
    assert 'id="item_message"' in client.get("/", headers={"host": MEERA}).text
    client.post("/order", data=form, headers={"host": MEERA})
    with Session(engine) as s:
        notes = [o.note for o in s.exec(select(Order).order_by(Order.id)).all()]
    assert "Happy Birthday" not in notes[0]
    assert notes[1].startswith("Message on the item: Happy Birthday Riya")


# ---------- Scope guard: booking businesses get a plain sentence, not a shop ----------

def test_booking_business_gets_one_plain_sentence_and_no_shop(client, engine, claude):
    salon = json.loads((FIX / "sellers_hard" / "salon.json").read_text(encoding="utf-8"))
    r = client.post("/api/businesses", data={"description": salon["description"], "price_list": salon["price_list"]})
    assert claude.calls == ["reader_salon"]
    assert r.status_code == 422
    sentence = r.json()["detail"]
    assert sentence.endswith(".") and sentence.count(". ") == 0 and len(sentence) < 200
    assert "orders" in sentence and "book" in sentence
    with Session(engine) as s:
        assert s.exec(select(Business)).all() == []
        ev = s.exec(select(AuditEvent).where(AuditEvent.action == "read_business")).all()[-1]
        assert ev.result == "refused"


def test_booking_business_without_reason_gets_default_sentence(client, engine):
    from app.routers.businesses import NOT_SUPPORTED_DEFAULT, get_claude

    class Booking:
        def ask_json(self, **kw):
            d = json.loads((FIX / "claude" / "reader_salon.json").read_text(encoding="utf-8"))
            return {**d, "not_supported_reason": ""}

    client.app.dependency_overrides[get_claude] = lambda: Booking()
    r = client.post("/api/businesses", data={"description": "Tuition classes for class 10 maths, Rs 2000 a month"})
    assert r.status_code == 422 and r.json()["detail"] == NOT_SUPPORTED_DEFAULT


def test_order_shops_are_still_built(client):
    for seller in ("meera_cakes", "tailor", "tiffin_service"):
        assert create(client, seller)["profile"]["kind"] == "orders"


def test_group_products_leaves_extras_out():
    p = tidy_profile(meera_live())
    names = [item.name for cat in group_products(p.products) for _i, item in cat.items]
    assert "Photo print on cake" not in names and "Chocolate truffle cake 1 kg" in names
