"""S21: how each item is sold (sizes / packs with their own prices, unit, min / max, a required choice, item notice,
"Sold out today"). Code validates every field and draws it; totals come only from the menu; the checker's test order
still passes in every selling mode."""

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.agents.checker import lines_for_test_order as check_lines
from app.agents.policy import shop_text
from app.agents.reader import Product, Profile, tidy_profile
from app.models import Evidence, Order, Photo
from app.sites import items
from app.sites.orders import OrderInvalid, parse_order_form
from app.sites.render import render_site
from app.sites.themes import THEME_KEYS
from tests.test_m3_launch import approve, plan
from tests.test_s15_selling import HOST, change, day, pickup, shop

FIX = Path(__file__).parent / "fixtures"
GALLERY = sorted((FIX / "site_gallery").glob("*.json"))
CUSTOMER = {"customer_name": "Asha Rao", "customer_phone": "98765 43210"}


def meera() -> Profile:
    return tidy_profile(Profile.model_validate(json.loads((FIX / "claude" / "reader_meera_cakes.json").read_text(encoding="utf-8"))))


ROSES = {"name": "Crochet roses", "price_inr": 40, "category": "Flowers", "unit": "piece", "min_qty": 5,
         "choice_label": "Colour", "choices": ["Red", "Pink", "White", "Yellow"]}
BOUQUET = {"name": "Crochet bouquet", "price_inr": 260, "category": "Bouquets", "option_kind": "pack",
           "options": [{"label": "6 roses", "price_inr": 260}, {"label": "12 roses", "price_inr": 480}],
           "choice_label": "Colour", "choices": ["Red", "Pink", "White", "Yellow"]}


def crochet(**extra) -> Profile:
    return Profile.model_validate({"name": "Loops by Lata", "products": [ROSES, BOUQUET], "selling_mode": "pickup",
                                   "area": "Kothrud", **extra})


def parse(p: Profile, **form):
    return parse_order_form({**CUSTOMER, "fulfilment": "pickup", "wanted_date": day(10), **form}, p)


# ---------- the data model: optional, validated, bad values become defaults ----------

def test_an_old_item_loads_unchanged():
    old = {"name": "Kaju katli", "price_inr": 900, "description": "", "category": "Sweets"}
    p = Product.model_validate(old)
    assert (p.options, p.option_kind, p.unit, p.min_qty, p.max_qty, p.choice_label, p.choices, p.notice_days, p.sold_out) == \
        ([], "", "", 1, 0, "", [], 0, False)
    assert p.price_inr == 900


def test_bad_values_become_defaults_and_unknown_keys_are_dropped():
    p = Product.model_validate({
        "name": "Cake", "price_inr": 1, "colour": "red",
        "options": [{"label": "½ kg", "price_inr": 700}, {"label": "½ KG", "price_inr": 800},  # duplicate label (any case)
                    {"label": "", "price_inr": 5}, {"label": "free", "price_inr": 0}, {"label": "neg", "price_inr": -4},
                    "junk", {"label": "<b>1 kg</b>", "price_inr": "1200", "extra": 1}],
        "option_kind": "colour", "unit": "litre", "min_qty": 0, "max_qty": 500, "notice_days": 99,
        "choice_label": "<i>Flavour</i>", "choices": ["Chocolate", "chocolate", "<script>x</script>", "", 7, "Vanilla"],
        "sold_out": "yes"})
    assert [(o.label, o.price_inr) for o in p.options] == [("½ kg", 700), ("1 kg", 1200)]
    assert p.price_inr == 700  # the lowest option: "from ₹700", sorting and the gifts tiles keep working
    assert (p.option_kind, p.unit, p.min_qty, p.max_qty, p.notice_days, p.sold_out) == ("", "", 1, 0, 0, False)
    assert p.choice_label == "Flavour" and p.choices == ["Chocolate", "x", "Vanilla"]
    assert "colour" not in p.model_dump()


def test_limits_on_lengths_and_counts():
    many = [{"label": f"Size {n}", "price_inr": 100 + n} for n in range(12)]
    p = Product.model_validate({"name": "T", "price_inr": 1, "options": many, "choices": [f"c{n}" for n in range(12)],
                                "choice_label": "x" * 80, "min_qty": 7, "max_qty": 3})
    assert len(p.options) == items.MAX_OPTIONS and len(p.choices) == items.MAX_CHOICES
    assert len(p.choice_label) == items.CHOICE_LABEL_MAX
    assert p.max_qty == 0  # a maximum below the minimum is dropped
    long = Product.model_validate({"name": "T", "price_inr": 1, "options": [{"label": "y" * 90, "price_inr": 5}],
                                   "choices": ["z" * 90]})
    assert len(long.options[0].label) == 40 and long.choices == ["z" * 30]
    assert Product.model_validate({"name": "T", "price_inr": 1, "choices": [], "choice_label": "Colour"}).choice_label == ""


# ---------- code-side grouping (no Claude) ----------

@pytest.mark.parametrize("name,want", [
    ("Chocolate truffle cake 1/2 kg", ("Chocolate truffle cake", "½ kg", "weight")),
    ("Chocolate Truffle Cake (½ kg)", ("Chocolate Truffle Cake", "½ kg", "weight")),
    ("Mango achar 500gm", ("Mango achar", "500 g", "weight")),
    ("Laddoo 1 1/2 kg", ("Laddoo", "1½ kg", "weight")),
    ("Cupcakes box of 6", ("Cupcakes", "Box of 6", "pack")),
    ("Thali (pack of 12)", ("Thali", "Pack of 12", "pack")),
    ("Momos 6 pcs", ("Momos", "6 pcs", "pack")),
    ("1 kg", None), ("Banana walnut loaf", None), ("Kurti stitching", None),
])
def test_split_size(name, want):
    assert items.split_size(name) == want


def test_meeras_truffle_cake_becomes_one_item_with_two_sizes():
    p = meera()
    cakes = [x for x in p.products if "truffle" in x.name.lower()]
    assert len(cakes) == 1
    cake = cakes[0]
    assert cake.name == "Chocolate truffle cake" and cake.option_kind == "weight" and cake.price_inr == 650
    assert [(o.label, o.price_inr) for o in cake.options] == [("½ kg", 650), ("1 kg", 1200)]
    assert p.products.index(cake) == 0  # it takes the first one's place
    single = next(x for x in p.products if x.name.startswith("Pineapple"))  # only one size listed: left alone
    # S21B live reply: the one listed size stays in the item's words, it is not made into a size option
    assert single.name == "Pineapple cake" and "kg" in single.description and not single.options
    assert tidy_profile(p) == p  # running it again changes nothing


@pytest.mark.parametrize("path", GALLERY, ids=lambda p: p.stem)
def test_grouping_on_every_gallery_seller_never_merges_different_things(path):
    raw = Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    grouped = items.group_sizes(raw.products)
    before = {(x.name, x.category, x.price_inr) for x in raw.products}
    for g in grouped:
        if g.options:  # each option is one of her own items, same category, same price
            for o in g.options:
                assert any(n.startswith(g.name) and c == g.category and pr == o.price_inr for n, c, pr in before), (g.name, o)
        else:
            assert (g.name, g.category, g.price_inr) in before
    assert sum(max(1, len(g.options)) for g in grouped) == len(raw.products)  # nothing lost, nothing invented
    want = {"bakery": {"Chocolate truffle cake": ["½ kg", "1 kg"]}}.get(path.stem, {})
    assert {g.name: [o.label for o in g.options] for g in grouped if g.options} == want


def test_grouping_needs_the_same_category_and_skips_extras_and_from_prices():
    def prod(name, cat="Cakes", **kw):
        return Product.model_validate({"name": name, "price_inr": kw.pop("price", 500), "category": cat, **kw})
    assert len(items.group_sizes([prod("Cake 1 kg"), prod("Cake 1/2 kg", cat="Specials")])) == 2
    assert len(items.group_sizes([prod("Cake 1 kg"), prod("Cake 1/2 kg", price_from=True)])) == 2
    assert len(items.group_sizes([prod("Cake 1 kg"), prod("Cake 1/2 kg", addon=True)])) == 2
    assert len(items.group_sizes([prod("Cake 1 kg"), prod("Cake (1 kg)", price=600)])) == 2  # same label twice
    assert len(items.group_sizes([prod("Cake 1 kg", food_mark="veg"), prod("Cake 1/2 kg", food_mark="egg")])) == 2
    assert len(items.group_sizes([prod("Cake 1 kg"), prod("Tart 1/2 kg")])) == 2
    merged = items.group_sizes([prod("Barfi 250 g", price=200), prod("Kaju 1 kg"), prod("Barfi 500 g", price=380)])
    assert [x.name for x in merged] == ["Barfi", "Kaju 1 kg"]


# ---------- the order: totals only from the menu, every rule on the server ----------

def test_one_1kg_and_two_half_kg_add_up_from_the_menu():
    d = parse(meera(), qty_0_1="1", qty_0_0="2", price_inr="1", total_inr="1")
    assert d["items"] == [{"name": "Chocolate truffle cake", "qty": 2, "price_inr": 650, "option_label": "½ kg"},
                          {"name": "Chocolate truffle cake", "qty": 1, "price_inr": 1200, "option_label": "1 kg"}]
    assert d["items_inr"] == 2 * 650 + 1200


@pytest.mark.parametrize("form", [{"qty_0": "1"}, {"qty_0_2": "1"}, {"qty_0_9": "3"}, {"qty_1_0": "1"}])
def test_an_option_box_that_is_not_on_the_menu_is_refused(form):
    with pytest.raises(OrderInvalid, match="listed options|from the menu"):
        parse(meera(), **form)


def test_zero_in_a_stale_box_is_harmless():
    assert parse(meera(), qty_0="0", qty_1_0="0", qty_1="1")["items"][0]["name"].startswith("Pineapple")


def test_crochet_roses_minimum_and_colour():
    p = crochet()
    with pytest.raises(OrderInvalid, match=r"Crochet roses: please order at least 5 \(you chose 3\)"):
        parse(p, qty_0="3", choice_0="Red")
    with pytest.raises(OrderInvalid, match="Please choose a colour for Crochet roses"):
        parse(p, qty_0="5")
    with pytest.raises(OrderInvalid, match="Please choose a colour"):
        parse(p, qty_0="5", choice_0="Blue")  # only her own list
    d = parse(p, qty_0="5", choice_0="Pink", qty_1_1="1", choice_1="White")
    assert d["items"] == [{"name": "Crochet roses", "qty": 5, "price_inr": 40, "choice": "Pink"},
                          {"name": "Crochet bouquet", "qty": 1, "price_inr": 480, "option_label": "12 roses", "choice": "White"}]
    assert d["items_inr"] == 5 * 40 + 480
    assert parse(p, qty_1_0="1", choice_1="Red", choice_0="")["items"][0]["name"] == "Crochet bouquet"  # no roses: no colour needed


def test_maximum_counts_all_options_together():
    p = crochet(products=[{**BOUQUET, "max_qty": 2}])
    parse(p, qty_0_0="1", qty_0_1="1", choice_0="Red")
    with pytest.raises(OrderInvalid, match="at most 2"):
        parse(p, qty_0_0="2", qty_0_1="1", choice_0="Red")


def test_sold_out_is_refused_on_the_server_and_has_no_box():
    p = crochet(products=[{**ROSES, "sold_out": True}, BOUQUET])
    with pytest.raises(OrderInvalid, match="Crochet roses is sold out today"):
        parse(p, qty_0="5", choice_0="Red")
    html = render_site(p)
    row = re.search(r'<li class="item[^"]*sold-out[^"]*".*?(?=<li class="item)', html, re.S).group(0)
    assert "Sold out today" in row and 'name="qty_0"' not in row and 'name="choice_0"' not in row
    assert 'name="qty_1_0"' in html


def test_item_notice_is_the_longest_and_the_test_order_ignores_it():
    p = crochet(products=[ROSES, {**BOUQUET, "notice_days": 7}], min_notice_days=2)
    with pytest.raises(OrderInvalid, match=r"Crochet bouquet needs 7 days' notice\. The earliest date you can pick is"):
        parse(p, qty_1_0="1", choice_1="Red", wanted_date=day(4))
    no_rule = crochet(products=[ROSES, {**BOUQUET, "notice_days": 7}])  # the shop itself asks for no date
    with pytest.raises(OrderInvalid, match="needs 7 days' notice. Please pick the date"):
        parse_order_form({**CUSTOMER, "fulfilment": "pickup", "qty_1_0": "1", "choice_1": "Red"}, no_rule)
    assert parse(p, qty_1_0="1", choice_1="Red", wanted_date=day(7))["wanted_date"] == day(7)
    assert parse(p, qty_0="5", choice_0="Red", wanted_date=day(2))  # the roses keep the shop's own 2 days
    test = parse_order_form({**CUSTOMER, **check_lines(p)}, p, test=True)
    assert test["items"] and not test["wanted_date"]


# ---------- what the page draws ----------

def test_meeras_page_shows_the_cake_once_with_its_two_sizes_and_works_without_js():
    html = render_site(meera())
    assert html.count('data-item="Chocolate truffle cake"') == 1
    row = re.search(r'<li class="item has-opts" data-i="0".*?</li>', html, re.S).group(0)
    assert "<small>from </small>₹650" in row
    assert '<label class="opt-l" for="qty_0_0"><span>½ kg</span> <b>₹650</b></label>' in row
    assert '<label class="opt-l" for="qty_0_1"><span>1 kg</span> <b>₹1,200</b></label>' in row
    assert 'name="qty_0_0" type="number"' in row and 'name="qty_0_1" type="number"' in row  # plain boxes, JS-off
    assert 'name="qty_0"' not in html and "<noscript" not in html


def test_unit_min_choice_and_notice_are_drawn():
    html = render_site(crochet(products=[ROSES, {**BOUQUET, "notice_days": 3}]))
    assert "₹40 <small class=\"unit\">per piece</small>" in html and "<li>Min 5</li>" in html
    assert "<li>Order 3 days ahead</li>" in html and "Some items need more notice" in html
    assert '<select id="choice_0" name="choice_0"><option value="">Choose…</option><option value="Red">Red</option>' in html
    assert 'id="wanted_date"' in html  # an item notice brings the date box even when the shop has no rule


EVIL = '"><script>alert(1)</script><img src=x onerror=alert(1)>'


@pytest.mark.parametrize("key", THEME_KEYS)
def test_hostile_text_in_every_new_field_is_escaped_in_every_theme_and_motif(key):
    from app.sites import motifs

    hostile = {"name": EVIL, "price_inr": 40, "category": EVIL, "options": [{"label": EVIL, "price_inr": 9}, {"label": "b" + EVIL, "price_inr": 8}],
               "choice_label": EVIL, "choices": [EVIL, "x" + EVIL], "min_qty": 3, "notice_days": 4, "unit": "piece"}
    for motif in motifs.MOTIFS[key]:
        p = Profile.model_validate({"name": "Shop", "products": [hostile, {**hostile, "sold_out": True}], "theme": key, "motif": motif})
        for page, order in (("home", None), ("thanks", {"ref": "LW-1", "items": [{"name": EVIL, "option_label": EVIL, "choice": EVIL,
                                                                                   "qty": 1, "price_inr": 9}], "total_inr": 9})):
            html = render_site(p, page=page, order=order, form_values={"choice_0": EVIL, "qty_0_0": EVIL})
            body = re.sub(r"<script>.*?</script>", "", html, flags=re.S)
            assert "<script>alert" not in body and "<img src=x" not in body and "onerror=alert" not in body.replace("onerror=alert(1)&gt;", "")


def test_old_profiles_render_exactly_as_before_where_nothing_is_set():
    p = Profile.model_validate({"name": "Old", "products": [{"name": "A", "price_inr": 5, "category": "X"}]})
    html = render_site(p)
    assert 'name="qty_0" type="number"' in html and 'class="item has-opts' not in html and '<ul class="item-notes">' not in html
    assert '<div class="choice">' not in html and 'sold-out"' not in html


# ---------- the checker's test order ----------

def test_the_test_order_takes_the_first_item_that_can_be_ordered():
    p = crochet(products=[{**ROSES, "sold_out": True}, {**BOUQUET, "min_qty": 2}])
    assert check_lines(p) == {"qty_1_0": "2", "choice_1": "Red"}
    assert check_lines(crochet()) == {"qty_0": "5", "choice_0": "Red"}
    assert check_lines(meera()) == {"qty_0_0": "1"}
    assert check_lines(crochet(products=[{**ROSES, "sold_out": True}])) == {}  # nothing to order: only the note


@pytest.mark.parametrize("changes", [
    {"selling_mode": "pickup"},
    {"selling_mode": "local", "delivery_areas": "Baner, Aundh"},
    {"selling_mode": "india", "dispatch_days": 3, "payment_terms": "upfront"},
    {"selling_mode": "pickup_local", "min_notice_days": 30, "days_off": [0, 1, 2, 3, 4, 5]},
])
@pytest.mark.parametrize("menu", ["options", "roses_first", "all_sold_out"])
def test_the_test_order_passes_with_options_min_choice_and_sold_out(client, engine, changes, menu):
    menus = {"options": None,  # Meera's own: truffle cake with ½ kg / 1 kg first
             "roses_first": [ROSES, {**BOUQUET, "notice_days": 9}],
             "all_sold_out": [{**ROSES, "sold_out": True}]}
    extra = {"products": menus[menu]} if menus[menu] else {}
    biz = shop(client, publish_it=False, **changes, **extra)
    approve(client, plan(client, biz))
    with Session(engine) as s:
        o = s.exec(select(Order)).one()
        assert o.is_test and o.email_status == "sent"
        lines = json.loads(o.items_json)
        steps = [e.step for e in s.exec(select(Evidence).where(Evidence.check == "test_order").order_by(Evidence.id)).all()]
    assert steps == ["form_post", "smtp_accepted", "imap_seen"]
    want = {"options": [("Chocolate truffle cake", "½ kg", "", 1)], "roses_first": [("Crochet roses", "", "Red", 5)],
            "all_sold_out": []}[menu]
    assert [(x["name"], x.get("option_label", ""), x.get("choice", ""), x["qty"]) for x in lines] == want


# ---------- the real path: page -> order -> Orders page -> email ----------

def test_meera_order_shows_both_sizes_everywhere(client, engine, mailer):
    biz = shop(client)
    r = client.post("/order", data={**CUSTOMER, **pickup(), "qty_0_1": "1", "qty_0_0": "2", "order_token": "s21" * 7}, headers=HOST)
    assert r.status_code == 200, r.text
    assert "2 × Chocolate truffle cake · ½ kg" in r.text and "1 × Chocolate truffle cake · 1 kg" in r.text
    assert "₹2,500" in r.text
    mail = mailer.sent[-1]["body"]
    assert "- 2 x Chocolate truffle cake · ½ kg @ ₹650 = ₹1,300" in mail
    assert "- 1 x Chocolate truffle cake · 1 kg @ ₹1,200 = ₹1,200" in mail
    rows = client.get(f"/api/businesses/{biz['id']}/orders").json()
    got = [(x["name"], x["option_label"], x["qty"], x["price_inr"]) for x in rows[0]["items"]]
    assert got == [("Chocolate truffle cake", "½ kg", 2, 650), ("Chocolate truffle cake", "1 kg", 1, 1200)]
    assert rows[0]["total_inr"] == 2500


def test_crochet_choice_reaches_the_email_and_whatsapp_line(client, mailer):
    shop(client, products=[ROSES, BOUQUET])
    r = client.post("/order", data={**CUSTOMER, **pickup(), "qty_0": "6", "choice_0": "Yellow", "order_token": "c" * 20}, headers=HOST)
    assert r.status_code == 200 and "6 × Crochet roses · Yellow" in r.text
    assert "6 x Crochet roses · Yellow @ ₹40 = ₹240" in mailer.sent[-1]["body"]
    assert "6%20x%20Crochet%20roses%20%C2%B7%20Yellow" in r.text  # the "Send this order to the shop" WhatsApp line
    r = client.post("/order", data={**CUSTOMER, **pickup(), "qty_0": "3", "choice_0": "Red", "order_token": "d" * 20}, headers=HOST)
    assert r.status_code == 422 and "please order at least 5" in r.text and 'value="3"' in r.text  # her input is kept


def test_sold_out_toggle_is_not_a_word_change_on_a_live_shop(client, engine, monkeypatch):
    from app.routers import businesses

    biz = shop(client)
    calls = []
    monkeypatch.setattr(businesses.live_contact, "is_real_live", lambda b: True)
    monkeypatch.setattr("app.agents.policy.policy_check", lambda claude, p: calls.append(1))
    cur = client.get(f"/api/businesses/{biz['id']}").json()["profile"]
    products = [dict(x) for x in cur["products"]]
    products[1]["sold_out"] = True
    out = change(client, biz, products=products)
    assert out["profile"]["products"][1]["sold_out"] is True and not calls  # saved at once, no policy check
    assert "Sold out today" in client.get("/", headers=HOST).text


def test_option_labels_and_choices_are_words_for_the_policy_check():
    p = crochet()
    assert "6 roses, 12 roses" in shop_text(p) and "Colour: Red, Pink, White, Yellow" in shop_text(p)
    plain = Profile.model_validate({"name": "S", "products": [{"name": "A", "price_inr": 5, "description": "d"}]})
    assert shop_text(plain).endswith("Items:\n- A: d")  # unchanged for items without them
    renamed = crochet(products=[ROSES, {**BOUQUET, "options": [{"label": "6 roses", "price_inr": 260}, {"label": "Free gift", "price_inr": 480}]}])
    assert shop_text(renamed) != shop_text(p)
    assert shop_text(crochet(products=[{**ROSES, "sold_out": True}, BOUQUET])) == shop_text(p)


# ---------- photos follow merged items ----------

def test_a_photo_follows_its_size_into_the_merged_item(client, engine):
    from app.photos import follow_items

    biz = shop(client, publish_it=False)
    with Session(engine) as s:
        for n, item in enumerate(("Chocolate truffle cake 1/2 kg", "Chocolate truffle cake 1 kg", "Pineapple cake 1/2 kg", "Gone")):
            s.add(Photo(business_id=biz["id"], item=item, name=f"s21photo{n}", small=b"", large=b"", small_w=1, small_h=1,
                        large_w=1, large_h=1))
        s.commit()
        old = ["Chocolate truffle cake 1/2 kg", "Chocolate truffle cake 1 kg", "Pineapple cake 1/2 kg", "Gone"]
        new = ["Chocolate truffle cake", "Pineapple cake 1/2 kg"]
        follow_items(s, biz["id"], old, new)
        s.commit()
        assert sorted(p.item for p in s.exec(select(Photo)).all()) == ["Chocolate truffle cake", "Pineapple cake 1/2 kg"]


def test_demo_meera_shows_the_merged_cake(client):
    html = client.get("/demo/meera").text
    assert html.count('data-item="Chocolate truffle cake"') == 1 and 'name="qty_0_1"' in html
    r = client.post("/demo/meera/order", data={**CUSTOMER, **pickup(), "qty_0_1": "1"})
    assert r.status_code == 200 and "This is a demo" in r.text



# ---------- the one-tap "Sold out today" switch ----------

def test_sold_out_switch_is_owner_only_audited_and_refuses_a_changed_menu(client, new_client, engine):
    from app.models import AuditEvent

    biz = shop(client)
    url = f"/api/businesses/{biz['id']}/sold-out"
    name = biz["profile"]["products"][1]["name"]
    r = client.put(url, json={"index": 1, "name": name, "sold_out": True})
    assert r.status_code == 200 and r.json()["profile"]["products"][1]["sold_out"] is True
    assert "Sold out today" in client.get("/", headers=HOST).text
    assert client.put(url, json={"index": 1, "name": "Something else", "sold_out": False}).status_code == 409
    assert client.put(url, json={"index": 99, "name": name, "sold_out": False}).status_code == 409
    assert new_client().put(url, json={"index": 1, "name": name, "sold_out": False}).status_code in (401, 403, 404)
    r = client.put(url, json={"index": 1, "name": name, "sold_out": False})
    assert r.json()["profile"]["products"][1]["sold_out"] is False
    with Session(engine) as s:
        rows = [e.detail for e in s.exec(select(AuditEvent).where(AuditEvent.action == "item_sold_out")).all()]
    assert rows == ["item 2: sold out today", "item 2: back on sale"]


def test_sold_out_switch_also_reaches_a_held_edit(client, engine):
    from app.models import Business

    biz = shop(client)
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        pending = Profile.model_validate_json(b.profile_json)
        pending.tagline = "Edited and waiting"
        b.pending_profile_json = pending.model_dump_json()
        s.add(b)
        s.commit()
    name = biz["profile"]["products"][2]["name"]
    r = client.put(f"/api/businesses/{biz['id']}/sold-out", json={"index": 2, "name": name, "sold_out": True})
    assert r.status_code == 200
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        assert Profile.model_validate_json(b.profile_json).products[2].sold_out
        assert Profile.model_validate_json(b.pending_profile_json).products[2].sold_out
        assert Profile.model_validate_json(b.pending_profile_json).tagline == "Edited and waiting"


# ---------- STEP 4: link preview when the shop is shared ----------

def test_public_shop_home_has_link_preview_tags_and_preview_demo_privacy_do_not(client):
    from tests.test_s12_photos import jpeg, up

    biz = shop(client, tagline='Cakes & "bakes" <b>here</b>', section_copy={"hero_line": "", "about": "", "how_ordering": ""})
    html = client.get("/", headers=HOST).text
    assert '<meta property="og:type" content="website">' in html
    assert '<meta property="og:title" content="Meera&#39;s Eggless Bakes">' in html
    assert '<meta property="og:url" content="http://meera.localhost/">' in html
    assert '<meta property="og:description" content="Cakes &amp; &#34;bakes&#34; &lt;b&gt;here&lt;/b&gt;">' in html
    assert '<meta name="twitter:card" content="summary">' in html and "og:image" not in html  # no photo: no image tag
    assert '<link rel="canonical" href="http://meera.localhost/">' in html
    r = up(client, biz, jpeg())
    assert r.status_code == 201, r.text
    large = r.json()["shop"][0]["large"]
    html = client.get("/", headers=HOST).text
    assert f'<meta property="og:image" content="http://meera.localhost{large}">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert "og:" not in client.get("/privacy", headers=HOST).text
    assert "og:" not in client.get(f"/api/businesses/{biz['id']}/preview").text
    assert "og:" not in client.get("/demo/meera").text and client.get("/demo/meera").headers["X-Robots-Tag"] == "noindex"


def test_link_preview_text_is_escaped(client):
    shop(client, section_copy={"hero_line": EVIL, "about": "", "how_ordering": ""})
    head = client.get("/", headers=HOST).text.split("</head>")[0]
    assert "<script>alert" not in head and "<img src=x" not in head and "og:description" in head


def test_poster_is_owner_only_for_a_live_shop_with_a_qr_and_no_script(client, new_client):
    biz = shop(client, tagline="Eggless <cakes> & more", section_copy={"hero_line": "", "about": "", "how_ordering": ""})
    r = client.get(f"/api/businesses/{biz['id']}/poster")
    assert r.status_code == 200 and "default-src 'none'" in r.headers["Content-Security-Policy"]
    html = r.text
    assert "<script" not in html and "Order online" in html and "meera.localhost" in html
    assert 'aria-label="QR code for http://meera.localhost/"' in html and "<path" in html
    assert "Eggless &lt;cakes&gt; &amp; more" in html and "http" not in html.split("<style>")[1].split("</style>")[0]
    assert new_client().get(f"/api/businesses/{biz['id']}/poster").status_code in (401, 403, 404)
    from tests.test_s15_selling import create

    draft = create(client)  # a draft is not on the internet: nothing to print
    assert client.get(f"/api/businesses/{draft['id']}/poster").status_code == 404


# ---------- STEP 2: the Reader (saved live replies, re-captured in S21B) ----------

def test_reader_crochet_reply_keeps_her_minimum_packs_and_colours():
    from app.agents.claude_client import FixtureClaudeClient
    from app.agents.reader import read_business

    s = json.loads((FIX / "sellers_hard" / "crochet.json").read_text(encoding="utf-8"))
    claude = FixtureClaudeClient()
    p = read_business(claude, description=s["description"], price_list=s["price_list"])
    assert claude.calls == ["reader_crochet"]
    roses, bouquet = p.products
    assert (roses.price_inr, roses.unit, roses.min_qty, roses.choice_label, roses.choices) == \
        (40, "piece", 5, "Colour", ["Red", "Pink", "White", "Yellow"])
    assert [(o.label, o.price_inr) for o in bouquet.options] == [("6 flowers", 260), ("12 flowers", 480)]
    assert bouquet.price_inr == 260 and not any(x.sold_out for x in p.products)


def test_reader_schema_asks_only_for_keys_code_can_check_and_never_sold_out():
    from app.agents.reader import PROFILE_SCHEMA, SYSTEM

    item = PROFILE_SCHEMA["properties"]["products"]["items"]
    assert "sold_out" not in item["properties"] and "new_until" not in item["properties"]
    assert item["properties"]["unit"]["enum"] == ["", *items.UNITS]
    assert item["properties"]["option_kind"]["enum"] == ["", *items.OPTION_KINDS]
    assert "never invent sizes, prices, minimums or choices" in SYSTEM


@pytest.mark.parametrize("name", ["reader_meera_cakes", "reader_tiffin_service", "reader_prompt_injection", "reader_crochet"])
def test_s21_replies_are_live_captures_with_every_item_key(name):
    # S21B: re-captured live on the laptop (the S21 hand-written placeholders are gone)
    data = json.loads((FIX / "claude" / f"{name}.json").read_text(encoding="utf-8"))
    assert "_s21_placeholder" not in data and "placeholder" not in data.get("_note", "").lower()
    for x in data["products"]:  # every per-item key the schema asks for is present
        assert {"options", "option_kind", "unit", "min_qty", "max_qty", "choice_label", "choices", "notice_days"} <= set(x)


def test_prompt_injection_reply_still_ignores_the_injected_prices():
    p = tidy_profile(Profile.model_validate(json.loads((FIX / "claude" / "reader_prompt_injection.json").read_text(encoding="utf-8"))))
    assert p.name != "Hacked" and all(x.price_inr > 1 for x in p.products) and all(not x.options for x in p.products)


def test_a_changed_option_label_on_a_live_shop_goes_through_the_policy_check(client, monkeypatch):
    from app.agents.policy import Verdict
    from app.routers import businesses

    biz = shop(client)
    seen = []
    monkeypatch.setattr(businesses.live_contact, "is_real_live", lambda b: True)
    monkeypatch.setattr("app.agents.policy.policy_check", lambda claude, p: seen.append(p) or Verdict(False, "Needs a look."))
    cur = client.get(f"/api/businesses/{biz['id']}").json()["profile"]
    products = [dict(x) for x in cur["products"]]
    products[0]["options"] = [{"label": "½ kg", "price_inr": 650}, {"label": "Huge 5 kg", "price_inr": 1200}]
    out = change(client, biz, products=products)
    assert len(seen) == 1 and out["pending_edit"]  # held for the team; customers keep the approved menu
    assert "Huge 5 kg" not in client.get("/", headers=HOST).text
