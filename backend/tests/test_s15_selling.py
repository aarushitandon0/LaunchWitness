"""S15: where a shop sells, when, and how the customer pays. Every rule is checked on the SERVER (the form's JavaScript is
only a courtesy), and the address is private."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.agents.reader import Profile
from app.models import AuditEvent, Evidence, Order
from app.sites import fulfilment as ful
from app.sites.render import render_site
from tests.conftest import GO_LIVE, publish_client, ready_for_real, set_user, sign_in
from tests.test_m3_launch import approve, plan

SELLERS = Path(__file__).parent / "fixtures" / "sellers"
HOST = {"host": "meera.localhost"}
ADDRESS = "Flat 4B, 12 Secret Lane, Baner, Pune"
BASE = {"qty_0": "1", "customer_name": "Asha Rao", "customer_phone": "98765 43210"}
ITEM = 650  # Chocolate truffle cake 1/2 kg in Meera's saved reply


def day(n: int) -> str:
    return (ful.today_ist() + timedelta(days=n)).isoformat()


def weekday_of(n: int) -> int:
    return (ful.today_ist() + timedelta(days=n)).weekday()


def create(client) -> dict:
    s = json.loads((SELLERS / "meera_cakes.json").read_text(encoding="utf-8"))
    r = client.post("/api/businesses", data={"description": s["description"], "price_list": s["price_list"]})
    assert r.status_code == 201, r.text
    return r.json()


# Meera, set up the S15 way. Her saved reply has pickup + delivery and 2 days' notice; everything else is set per test.
SHOP = {"selling_mode": "pickup_local", "city": "Pune", "area": "Baner", "delivery_areas": "Baner, Aundh, 411045",
        "delivery_fee_inr": 80, "whatsapp": "98765 43210", "upi_id": "meera.cakes@okaxis", "min_notice_days": 2,
        "upi_display_name": "Meera Joshi", "phone": "98765 43210"}


def shop(client, publish_it=True, **changes) -> dict:
    biz = create(client)
    body = {**biz["profile"], **SHOP, **changes}
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": body, "subdomain": "meera"})
    assert r.status_code == 200, r.text
    if publish_it:
        publish_client(client, biz["id"])
    return r.json()


def change(client, biz, **changes) -> dict:
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], **changes}, "subdomain": cur["subdomain"]})
    assert r.status_code == 200, r.text
    return r.json()


def order(client, **form):
    return client.post("/order", data={**BASE, **form}, headers=HOST)


def pickup(**form):
    return {"fulfilment": "pickup", "wanted_date": day(5), **form}


def delivery(**form):
    return {"fulfilment": "delivery", "wanted_date": day(5), "delivery_address": ADDRESS, "delivery_pin": "411045", **form}


def stored(engine) -> list[Order]:
    with Session(engine) as s:
        return list(s.exec(select(Order).where(Order.is_test == False)).all())  # noqa: E712


# ---------- old profiles ----------

OLD = {"name": "Old Shop", "area": "Baner, Pune", "pickup_available": True, "delivery_available": True, "delivery_fee_inr": 50,
       "delivery_areas": "All of Pune, 411001-411060, near the river", "hours": "Tue-Sun",
       "products": [{"name": "Cake", "price_inr": 500}]}


def test_an_old_profile_loads_with_safe_defaults():
    p = Profile.model_validate(OLD)
    assert p.selling_mode == "pickup_local"  # worked out from the two old yes/no boxes
    assert (p.pickup_available, p.delivery_available) == (True, True)
    assert p.payment_terms == "on_delivery" and p.advance_percent == 0 and p.accepts_cash is False
    assert p.cancellation_preset == "" and p.on_break is False and p.days_off == [] and p.time_slots == []
    assert p.max_orders_per_day == 0 and p.city == "" and p.products[0].food_mark == ""
    assert p.delivery_areas.startswith("All of Pune")  # the old free text is kept as it was, never rejected on load


@pytest.mark.parametrize("pickup,deliver,want", [(False, False, ""), (True, False, "pickup"), (False, True, "local"),
                                                 (True, True, "pickup_local")])
def test_old_yes_no_boxes_become_a_selling_mode(pickup, deliver, want):
    p = Profile.model_validate({**OLD, "pickup_available": pickup, "delivery_available": deliver})
    assert p.selling_mode == want


@pytest.mark.parametrize("mode,flags", [("pickup", (True, False)), ("local", (False, True)), ("pickup_local", (True, True)),
                                        ("india", (False, True)), ("pickup_india", (True, True))])
def test_selling_mode_drives_the_two_boxes(mode, flags):
    p = Profile.model_validate({**OLD, "selling_mode": mode, "pickup_available": not flags[0], "delivery_available": not flags[1]})
    assert (p.pickup_available, p.delivery_available) == flags and p.selling_mode == mode


def test_unknown_values_fall_back_safely():
    p = Profile.model_validate({**OLD, "selling_mode": "drone", "payment_terms": "bitcoin", "cancellation_preset": "x",
                                "products": [{"name": "Cake", "price_inr": 5, "food_mark": "vegan?"}]})
    assert p.selling_mode == "pickup_local" and p.payment_terms == "on_delivery" and p.cancellation_preset == ""
    assert p.products[0].food_mark == ""


def test_new_fields_are_validated():
    for bad in ({"payment_terms": "advance", "advance_percent": 5}, {"payment_terms": "advance", "advance_percent": 95},
                {"back_on": "next week"}, {"days_off": [7]}, {"days_off": [0, 1, 2, 3, 4, 5, 6]},
                {"shipping_fee_inr": -1}, {"max_orders_per_day": 501}, {"dispatch_days": 31}):
        with pytest.raises(ValidationError):
            Profile.model_validate({**OLD, **bad})
    ok = Profile.model_validate({**OLD, "payment_terms": "advance", "advance_percent": 0})
    assert ok.advance_percent == 50  # an advance with no percent gets the plain default
    p = Profile.model_validate({**OLD, "days_off": [6, 0, 0], "time_slots": [" 10am-1pm ", "10am-1pm", "", "4-7pm"]})
    assert p.days_off == [0, 6] and p.time_slots == ["10am-1pm", "4-7pm"]


# ---------- delivery areas ----------

def test_area_list_accepts_localities_and_valid_pins():
    a = ful.parse_areas("Baner, Aundh; 411045\n411007, baner")
    assert a.localities == ["Baner", "Aundh"] and a.pins == ["411045", "411007"] and a.bad == []
    assert ful.areas_error("Baner, 411045") is None and ful.areas_error("") is None


@pytest.mark.parametrize("text", ["41104", "4110456", "011045", "Baner, 12345", "<b>x</b>", "a" * 60])
def test_area_list_refuses_bad_entries_in_plain_words(text):
    msg = ful.areas_error(text)
    assert msg and "6-digit PIN" in msg


def test_saving_a_bad_area_list_is_refused_but_an_old_one_still_loads(client):
    biz = shop(client, publish_it=False)
    cur = client.get(f"/api/businesses/{biz['id']}").json()["profile"]
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur, "delivery_areas": "Baner, 4110"}, "subdomain": "meera"})
    assert r.status_code == 422 and "PIN" in r.json()["detail"]
    # global free text on a shop that doesn't deliver locally isn't checked (nothing uses it)
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur, "selling_mode": "pickup", "delivery_areas": "Baner, 4110"},
                                                         "subdomain": "meera"})
    assert r.status_code == 200


# ---------- the go-live checklist ----------

def checklist(profile: dict):
    return ful.selling_problem(Profile.model_validate({**OLD, **profile}))


@pytest.mark.parametrize("profile,ok", [
    ({"selling_mode": "pickup", "city": "Pune", "area": "Baner"}, True),
    ({"selling_mode": "local", "city": "Pune", "area": "Baner", "delivery_areas": "Baner"}, True),
    ({"selling_mode": "local", "city": "Pune", "area": "Baner", "delivery_areas": "411045", "delivery_fee_inr": 0}, True),
    ({"selling_mode": "india", "city": "Pune", "area": "Baner", "dispatch_days": 3, "shipping_fee_inr": 0}, True),
    ({"selling_mode": "pickup_india", "city": "Pune", "area": "Baner", "dispatch_days": 2}, True),
    ({"selling_mode": "", "pickup_available": False, "delivery_available": False}, False),
    ({"selling_mode": "pickup", "city": "", "area": "Baner"}, False),
    ({"selling_mode": "pickup", "city": "Pune", "area": ""}, False),
    ({"selling_mode": "local", "city": "Pune", "area": "Baner", "delivery_areas": ""}, False),
    ({"selling_mode": "pickup_local", "city": "Pune", "area": "Baner", "delivery_areas": "4110"}, False),
    ({"selling_mode": "india", "city": "Pune", "area": "Baner", "dispatch_days": 0}, False),
])
def test_go_live_selling_rule(profile, ok):
    base = {"area": "", "city": "", "delivery_areas": ""}
    assert (ful.selling_problem(Profile.model_validate({**OLD, **base, **profile})) == "") is ok


def test_go_live_blocks_only_a_real_launch(client, engine):
    sign_in(client, "owner@example.org")
    set_user(engine, "owner@example.org", status="approved")
    biz = shop(client, publish_it=False, selling_mode="local", delivery_areas="")
    assert client.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox"}).status_code == 201  # practice: never blocked
    r = client.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True})
    assert r.status_code == 409 and "fulfilment" in r.headers["x-missing"]
    ready_for_real(client, biz["id"], delivery_areas="Baner")
    assert client.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True}).status_code == 201


# ---------- the order form, on the server ----------

def test_a_customer_outside_the_area_is_told_politely_and_nothing_is_stored(client, engine):
    shop(client)
    r = order(client, **delivery(delivery_pin="560001", delivery_address="12 MG Road, Bengaluru"))
    assert r.status_code == 422
    assert "Meera&#39;s Eggless Bakes delivers only in Baner, Aundh and 411045. You could choose pickup instead." in r.text
    assert stored(engine) == []
    assert order(client, **pickup()).status_code == 200  # ...and then she chooses pickup
    assert [o.fulfilment for o in stored(engine)] == ["pickup"]


def test_no_pickup_sentence_when_the_shop_has_no_pickup(client):
    shop(client, selling_mode="local")
    r = order(client, **delivery(delivery_pin="560001", delivery_address="12 MG Road"))
    assert r.status_code == 422 and "delivers only in" in r.text and "choose pickup" not in r.text


def test_pin_or_locality_in_the_address_is_enough(client, engine):
    shop(client)
    assert order(client, **delivery(delivery_pin="411045", delivery_address="Some lane")).status_code == 200  # listed PIN
    assert order(client, **delivery(delivery_pin="411099", delivery_address="12 Pashan Rd, near AUNDH gate",
                                    order_token="t" * 20)).status_code == 200  # listed locality, any case
    assert order(client, **delivery(delivery_pin="411099", delivery_address="Bannerghatta Road")).status_code == 422  # whole word only
    assert len(stored(engine)) == 2


@pytest.mark.parametrize("form,msg", [
    ({"delivery_address": ""}, "address"),
    ({"delivery_address": "x"}, "address"),
    ({"delivery_pin": ""}, "PIN"),
    ({"delivery_pin": "41104"}, "PIN"),
    ({"delivery_pin": "011045"}, "PIN"),
    ({"delivery_pin": "41104a"}, "PIN"),
])
def test_delivery_needs_an_address_and_a_6_digit_pin(client, engine, form, msg):
    shop(client)
    r = order(client, **{**delivery(), **form})
    assert r.status_code == 422 and msg in r.text and stored(engine) == []


def test_two_ways_means_the_customer_must_choose_and_only_offered_ways_work(client, engine):
    shop(client)
    assert order(client, wanted_date=day(5)).status_code == 422
    assert order(client, fulfilment="courier", wanted_date=day(5)).status_code == 422
    assert order(client, **pickup()).status_code == 200


def test_pickup_only_shop_refuses_a_delivery_form(client, engine):
    shop(client, selling_mode="pickup")
    assert order(client, **delivery()).status_code == 422
    assert order(client, wanted_date=day(5)).status_code == 200  # one way only: no need to say it
    assert stored(engine)[0].fulfilment == "pickup"


def test_shipping_across_india_takes_any_valid_pin(client, engine):
    shop(client, selling_mode="india", shipping_fee_inr=99, dispatch_days=3, shipping_note="Ships via courier, tracking on WhatsApp")
    r = order(client, **delivery(delivery_pin="560001", delivery_address="12 MG Road, Bengaluru"))
    assert r.status_code == 200
    o = stored(engine)[0]
    assert (o.fulfilment, o.fee_inr, o.total_inr) == ("delivery", 99, ITEM + 99)
    assert order(client, **delivery(delivery_pin="1234", order_token="u" * 20)).status_code == 422


def test_totals_and_fees_come_from_the_menu_not_the_browser(client, engine):
    shop(client)
    r = order(client, **delivery(total_inr="1", fee_inr="0", delivery_fee_inr="0", price_0="1", pay_now_inr="1"))
    assert r.status_code == 200
    o = stored(engine)[0]
    assert (o.fee_inr, o.total_inr) == (80, ITEM + 80)


def test_free_delivery_above_a_value_and_pickup_has_no_fee(client, engine):
    shop(client, free_delivery_above_inr=1200)
    order(client, **delivery(qty_0="1"))
    order(client, **delivery(qty_0="2", order_token="a" * 20))  # 1300 >= 1200: free
    order(client, **pickup(order_token="b" * 20))
    got = sorted((o.total_inr, o.fee_inr) for o in stored(engine))
    assert got == [(ITEM, 0), (ITEM + 80, 80), (2 * ITEM, 0)]


def test_zero_rupee_delivery_is_allowed(client, engine):
    shop(client, delivery_fee_inr=0)
    assert order(client, **delivery()).status_code == 200 and stored(engine)[0].fee_inr == 0


# ---------- the date rules ----------

def test_notice_rule_is_enforced_on_the_server(client, engine):
    shop(client, min_notice_days=3)
    for n in (0, 1, 2):
        r = order(client, **pickup(wanted_date=day(n)))
        assert r.status_code == 422 and f"earliest date you can pick is {ful.nice_date(ful.today_ist() + timedelta(days=3))}" in r.text
    assert order(client, **pickup(wanted_date=day(3))).status_code == 200 and len(stored(engine)) == 1


def test_a_date_is_needed_when_the_shop_has_a_rule_and_optional_otherwise(client, engine):
    shop(client)  # notice 2 days: a date is needed
    assert order(client, fulfilment="pickup").status_code == 422
    change(client, client.get("/api/businesses").json()[0], min_notice_days=0)
    assert order(client, fulfilment="pickup").status_code == 200  # no rule: a date is optional
    assert stored(engine)[0].wanted_date == ""


def test_days_off_are_refused_on_the_server(client, engine):
    off = weekday_of(5)
    shop(client, days_off=[off])
    r = order(client, **pickup(wanted_date=day(5)))
    assert r.status_code == 422 and ful.WEEKDAYS[off] in r.text and stored(engine) == []
    assert order(client, **pickup(wanted_date=day(6))).status_code == 200


def test_a_bad_or_far_off_date_is_refused(client):
    shop(client)
    assert order(client, **pickup(wanted_date="soon")).status_code == 422
    assert order(client, **pickup(wanted_date="2026-13-40")).status_code == 422
    assert order(client, **pickup(wanted_date=day(400))).status_code == 422


def test_daily_limit_closes_a_full_date_and_a_cancelled_order_frees_it(client, engine):
    biz = shop(client, max_orders_per_day=2)
    sign_in(client, "owner@example.org")
    when = day(6)
    for i in range(2):
        assert order(client, **pickup(wanted_date=when, order_token=f"{i}" * 20)).status_code == 200
    r = order(client, **pickup(wanted_date=when, order_token="z" * 20))
    assert r.status_code == 422 and "fully booked" in r.text and len(stored(engine)) == 2
    assert order(client, **pickup(wanted_date=day(7), order_token="y" * 20)).status_code == 200  # another day is fine
    assert f'data-full="{when}"' in client.get("/", headers=HOST).text  # the picker knows this day is full
    first = client.get(f"/api/businesses/{biz['id']}/orders").json()
    one = next(o for o in first if o["wanted_date"] == when)
    assert client.post(f"/api/businesses/{biz['id']}/orders/{one['id']}/status", json={"status": "cancelled"}).status_code == 200
    assert order(client, **pickup(wanted_date=when, order_token="w" * 20)).status_code == 200


def test_time_slots_only_from_the_list(client, engine):
    shop(client, time_slots=["10am-1pm", "4pm-7pm"])
    assert 'value="4pm-7pm"' in client.get("/", headers=HOST).text
    assert order(client, **pickup(time_slot="midnight")).status_code == 422
    assert order(client, **pickup(time_slot="4pm-7pm", order_token="s" * 20)).status_code == 200
    assert order(client, **pickup(order_token="r" * 20)).status_code == 200  # a slot is optional
    assert sorted(o.time_slot for o in stored(engine)) == ["", "4pm-7pm"]
    change(client, client.get("/api/businesses").json()[0], time_slots=[])
    order(client, **pickup(time_slot="4pm-7pm", order_token="q" * 20))
    assert stored(engine)[-1].time_slot == ""  # no slots offered: a stray value is dropped


# ---------- taking a break ----------

def test_a_shop_on_a_break_refuses_orders_politely_on_the_server(client, engine):
    shop(client, on_break=True, back_on=day(10))
    page = client.get("/", headers=HOST).text
    assert f"Taking a break, back on {ful.nice_date(ful.today_ist() + timedelta(days=10))}" in page
    assert "disabled>Not taking orders right now" in page
    r = order(client, **pickup())
    assert r.status_code == 409 and "is taking a break and isn&#39;t taking orders right now" in r.text and stored(engine) == []
    with Session(engine) as s:
        assert any(a.result == "blocked" and a.detail == "shop is taking a break" for a in s.exec(select(AuditEvent)).all())


def test_a_break_with_no_date_and_a_break_that_has_ended(client, engine):
    biz = shop(client, on_break=True)
    assert "Taking a break" in client.get("/", headers=HOST).text and "back on" not in client.get("/", headers=HOST).text.split("break-note")[1][:200]
    assert order(client, **pickup()).status_code == 409
    change(client, biz, back_on=day(0))  # back today: orders open again
    assert order(client, **pickup()).status_code == 200
    change(client, biz, on_break=False, back_on="")
    assert order(client, **pickup(order_token="k" * 20)).status_code == 200


def test_break_text_and_rule_are_plain(client):
    p = Profile.model_validate({**OLD, "on_break": True, "back_on": "2026-11-05"})
    assert ful.break_line(p) == "Taking a break, back on 5 Nov" and ful.on_break(p, ful.parse_date("2026-11-04"))
    assert not ful.on_break(p, ful.parse_date("2026-11-05")) and not ful.on_break(Profile.model_validate(OLD))


# ---------- payment ----------

@pytest.mark.parametrize("terms,pct,total,now,later", [
    ("upfront", 0, 730, 730, 0), ("advance", 30, 730, 219, 511), ("advance", 50, 1, 1, 0), ("advance", 90, 730, 657, 73),
    ("advance", 10, 5, 1, 4), ("on_delivery", 0, 730, 0, 730), ("upfront", 0, 0, 0, 0),
])
def test_payment_split_rounds_up_to_whole_rupees(terms, pct, total, now, later):
    p = Profile.model_validate({**OLD, "payment_terms": terms, "advance_percent": pct})
    assert ful.pay_split(p, total) == (now, later) and now + later == total


def uri_params(html: str) -> dict:
    from html import unescape
    from urllib.parse import parse_qs, unquote, urlsplit

    link = unescape(html.split('href="upi://pay?', 1)[1].split('"', 1)[0])
    return {k: unquote(v[0]) for k, v in parse_qs(urlsplit("upi://pay?" + link).query).items()}


def test_the_upi_link_asks_for_the_advance_with_the_order_ref(client, engine):
    shop(client, payment_terms="advance", advance_percent=30, accepts_cash=True)
    r = order(client, **delivery())
    assert r.status_code == 200
    o = stored(engine)[0]
    assert (o.pay_now_inr, o.pay_later_inr, o.payment_terms) == (219, 511, "advance")
    q = uri_params(r.text)
    assert q["am"] == "219.00" and q["tn"] == f"Order {o.ref}" and q["pa"] == "meera.cakes@okaxis" and q["cu"] == "INR"
    assert "Pay now: ₹219" in r.text and "₹511" in r.text and "Cash is fine" in r.text and 'aria-label="UPI payment QR code"' in r.text


def test_full_payment_upfront_asks_for_the_whole_total(client, engine):
    shop(client, payment_terms="upfront")
    r = order(client, **pickup(qty_0="2"))
    assert uri_params(r.text)["am"] == "1300.00" and "Pay now: ₹1,300" in r.text
    assert stored(engine)[0].pay_later_inr == 0


def test_pay_on_delivery_asks_for_nothing_now(client, engine):
    shop(client, payment_terms="on_delivery", accepts_cash=True)
    r = order(client, **pickup())
    assert "upi://pay" not in r.text and "Nothing to pay now" in r.text and "₹650" in r.text and "when you collect" in r.text
    o = stored(engine)[0]
    assert (o.pay_now_inr, o.pay_later_inr) == (0, ITEM)


def test_the_thank_you_page_says_what_is_due_on_delivery(client):
    shop(client, payment_terms="advance", advance_percent=50)
    r = order(client, **delivery())
    assert "when you receive your order" in r.text


def test_the_orders_page_reads_where_the_money_stands(client):
    biz = shop(client, payment_terms="advance", advance_percent=50)
    sign_in(client, "owner@example.org")
    order(client, **pickup())
    o = client.get(f"/api/businesses/{biz['id']}/orders").json()[0]
    assert o["payment_label"] == "Waiting for the advance (₹325)" and o["paid_action"] == "Advance received"
    walk = [("confirmed", "Waiting for the advance (₹325)"), ("paid", "Advance paid · ₹325 due on delivery"), ("done", "Fully paid")]
    for to, label in walk:
        got = client.post(f"/api/businesses/{biz['id']}/orders/{o['id']}/status", json={"status": to}).json()
        assert got["payment_label"] == label
    assert ful.payment_label("on_delivery", "new", 0, 650, 650) == "Due on delivery (₹650)"
    assert ful.payment_label("on_delivery", "paid", 0, 650, 650) == "Paid"
    assert ful.payment_label("upfront", "paid", 650, 0, 650) == "Fully paid"
    assert ful.payment_label("advance", "cancelled", 1, 1, 2) == "Cancelled"


# ---------- cancellation, food marks, where we sell: what the shop says ----------

def test_cancellation_presets_and_a_custom_line_are_shown_and_escaped(client, engine):
    for key, line in ful.CANCELLATION_PRESETS.items():
        p = Profile.model_validate({**OLD, "cancellation_preset": key})
        assert ful.cancellation_line(p) == line and line in render_site(p)
    p = Profile.model_validate({**OLD, "cancellation_preset": "custom", "cancellation_text": "<b>No</b> refunds <script>alert(1)</script>"})
    assert "<script>alert(1)" not in render_site(p) and "No refunds" in render_site(p)
    assert ful.cancellation_line(Profile.model_validate({**OLD, "cancellation_preset": "custom"})) == ""
    shop(client, cancellation_preset="full_24h")
    assert ful.CANCELLATION_PRESETS["full_24h"] in order(client, **pickup()).text  # also on the thank-you page


def test_cancellation_text_is_length_capped_and_plain():
    p = Profile.model_validate({**OLD, "cancellation_preset": "custom", "cancellation_text": "<i>" + "x" * 500 + "</i>"})
    assert len(p.cancellation_text) <= 140 and "<" not in p.cancellation_text


def test_food_marks_come_with_a_word(client):
    p = Profile.model_validate({**OLD, "allergens": "Contains <b>nuts</b> and dairy",
                                "products": [{"name": "Salad", "price_inr": 90, "food_mark": "veg"},
                                             {"name": "Egg puff", "price_inr": 30, "food_mark": "egg"},
                                             {"name": "Chicken roll", "price_inr": 80, "food_mark": "Non-Veg"},
                                             {"name": "Candle", "price_inr": 200}]})
    html = render_site(p)
    for k, word in ful.FOOD_MARK_WORDS.items():
        assert f'class="fm fm-{k}"' in html and f'aria-label="{word}"' in html and f'<span class="fm-t">{word}</span>' in html
    assert html.count('class="fm-row"') == 3  # the candle has no mark
    assert "Allergens:</b> Contains nuts and dairy" in html and "<b>nuts</b>" not in html


def test_where_we_sell_reads_right_in_every_mode():
    base = {**OLD, "city": "Pune", "area": "Baner", "delivery_areas": "Baner, 411045", "delivery_fee_inr": 40,
            "free_delivery_above_inr": 500, "shipping_fee_inr": 90, "dispatch_days": 3, "shipping_note": "Tracking on WhatsApp"}
    html = render_site(Profile.model_validate({**base, "selling_mode": "pickup"}))
    assert "Pickup in Baner, Pune" in html and "exact pickup address is shared on WhatsApp" in html and "Local delivery" not in html
    html = render_site(Profile.model_validate({**base, "selling_mode": "local"}))
    assert "Local delivery in Baner and 411045" in html and "Delivery ₹40, free above ₹500" in html and "Pickup in" not in html
    html = render_site(Profile.model_validate({**base, "selling_mode": "pickup_india"}))
    assert "Ships across India" in html and "Shipping ₹90" in html and "Sent within 3 days" in html and "Tracking on WhatsApp" in html
    assert "Pickup in Baner, Pune" in html and "Local delivery" not in html
    assert "Free shipping" in render_site(Profile.model_validate({**base, "selling_mode": "india", "shipping_fee_inr": 0}))


# ---------- privacy of the address ----------

def test_the_address_is_shown_to_the_owner_only(client, engine, mailer):
    biz = shop(client)
    sign_in(client, "owner@example.org")
    r = order(client, **delivery())
    assert r.status_code == 200
    assert "Secret Lane" not in r.text and "PIN code 411045" in r.text  # the customer's own page keeps the street out
    assert "Secret Lane" not in client.get("/", headers=HOST).text and "Secret Lane" not in client.get("/privacy", headers=HOST).text
    o = client.get(f"/api/businesses/{biz['id']}/orders").json()[0]  # the owner's Orders page
    assert o["delivery_address"] == ADDRESS and o["delivery_pin"] == "411045"
    body = "\n".join(m["body"] for m in mailer.sent if "New order" in m["subject"])  # the order email
    assert "Secret Lane" in body and "PIN code: 411045" in body and "LOCAL DELIVERY" in body
    with Session(engine) as s:  # no audit row, no evidence row, anywhere
        blob = json.dumps([e.model_dump(mode="json") for e in s.exec(select(AuditEvent)).all()]
                          + [e.model_dump(mode="json") for e in s.exec(select(Evidence)).all()])
        assert "Secret Lane" not in blob and "411045" not in blob and "Flat 4B" not in blob
        assert any(a.action == "order_placed" and a.detail.endswith(", delivery") for a in s.exec(select(AuditEvent)).all())


def test_a_second_owner_cannot_read_the_address(client, new_client, engine):
    biz = shop(client)
    sign_in(client, "owner@example.org")
    order(client, **delivery())
    other = new_client()
    sign_in(other, "nosy@example.org")
    assert other.get(f"/api/businesses/{biz['id']}/orders").status_code in (403, 404)


def test_the_shared_report_never_carries_the_address(client, engine):
    biz = shop(client)
    sign_in(client, "owner@example.org")
    order(client, **delivery())
    url = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]
    path = "/r/" + url.rsplit("/r/", 1)[1]
    for p in (path, path + "/verify"):
        text = client.get(p).text
        assert "Secret Lane" not in text and "411045" not in text and "Flat 4B" not in text


def test_the_address_is_deleted_with_the_shop(client, engine):
    biz = shop(client)
    sign_in(client, "owner@example.org")
    order(client, **delivery())
    assert client.delete(f"/api/businesses/{biz['id']}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Order)).all() == []


def test_the_privacy_pages_say_so():
    html = render_site(Profile.model_validate(OLD), page="privacy")
    assert "delivery address and PIN code" in html and "never shown on this website" in html
    assert "never ask for Aadhaar, PAN or bank details" in html and "deleted with it" in html
    legal = (Path(__file__).parents[2] / "frontend" / "src" / "Legal.tsx").read_text(encoding="utf-8")
    assert "delivery address and PIN code" in legal and "shown only to the shop owner" in legal and "Aadhaar" in legal


# ---------- the checker's test order, in every selling mode ----------

@pytest.mark.parametrize("changes", [
    {"selling_mode": "pickup"},
    {"selling_mode": "pickup_local"},
    {"selling_mode": "local", "delivery_areas": "Baner, Aundh"},  # a test address in her area, no PIN listed
    {"selling_mode": "local", "delivery_areas": "411045, 411007"},  # her first listed PIN
    {"selling_mode": "india", "dispatch_days": 3, "shipping_fee_inr": 90},
    {"selling_mode": "pickup_india", "dispatch_days": 3},
    {"selling_mode": "pickup", "on_break": True},  # a break doesn't stop the proof
    {"selling_mode": "pickup", "days_off": [0, 1, 2, 3, 4, 5], "max_orders_per_day": 1, "min_notice_days": 30},
    {"selling_mode": "india", "dispatch_days": 3, "payment_terms": "upfront", "time_slots": ["10am-1pm"]},
])
def test_the_test_order_still_passes_in_every_mode(client, engine, changes):
    biz = shop(client, publish_it=False, **changes)
    approve(client, plan(client, biz))
    with Session(engine) as s:
        o = s.exec(select(Order)).one()
        assert o.is_test and o.email_status == "sent"
        want = "pickup" if changes["selling_mode"].startswith("pickup") else "delivery"
        assert o.fulfilment == want
        if want == "delivery":
            assert o.delivery_pin and "Automatic test order" in o.delivery_address
        steps = [e.step for e in s.exec(select(Evidence).where(Evidence.check == "test_order").order_by(Evidence.id)).all()]
    assert steps == ["form_post", "smtp_accepted", "imap_seen"]
    assert client.get(f"/api/businesses/{biz['id']}/orders").json() == []  # still hidden from her list


def test_a_break_does_not_apply_to_the_test_order_but_does_to_everyone_else(client, engine):
    biz = shop(client, publish_it=False, on_break=True, selling_mode="pickup")
    approve(client, plan(client, biz))
    with Session(engine) as s:
        assert s.exec(select(Order)).one().is_test
    publish_client(client, biz["id"])
    assert order(client, **pickup()).status_code == 409  # a customer is still refused


def test_a_test_order_never_counts_toward_the_daily_limit(client, engine):
    biz = shop(client, publish_it=False, max_orders_per_day=1, selling_mode="pickup", min_notice_days=0)
    approve(client, plan(client, biz))
    publish_client(client, biz["id"])
    assert order(client, **pickup(wanted_date=day(3))).status_code == 200  # the limit is for real orders only
    assert order(client, **pickup(wanted_date=day(3), order_token="n" * 20)).status_code == 422


# ---------- hostile text, every theme, old orders ----------

EVIL = '"><img src=x onerror=alert(1)><script>alert(1)</script>'


@pytest.mark.parametrize("theme", ["bakery", "kitchen", "handmade", "tailor", "gifts", "general"])
def test_every_theme_shows_every_new_section(theme):
    p = Profile.model_validate({
        **OLD, "theme": theme, "selling_mode": "pickup_local", "city": "Pune", "area": "Baner", "delivery_areas": "Baner, 411045",
        "payment_terms": "advance", "advance_percent": 30, "accepts_cash": True, "upi_id": "meera.c@okaxis", "upi_display_name": "Meera",
        "cancellation_preset": "full_24h", "allergens": "Contains nuts", "on_break": True, "back_on": "2099-01-05",
        "days_off": [0, 6], "time_slots": ["10am-1pm"], "max_orders_per_day": 3, "min_notice_days": 2, "free_delivery_above_inr": 900,
        "products": [{"name": "Cake", "price_inr": 500, "food_mark": "veg"}, {"name": "Roll", "price_inr": 90, "food_mark": "nonveg"}]})
    html = render_site(p, full_dates=["2099-01-02"])
    assert f"theme-{theme}" in html
    for needle in ("Where we sell", "How to pay", "Cancellations", "Good to know", "Taking a break, back on 5 Jan", 'class="fm fm-veg"',
                   'id="delivery-fields"', 'name="wanted_date"', 'name="time_slot"', 'data-full="2099-01-02"', "Closed on Monday, Sunday",
                   "Please pay 30% now by UPI", "free above ₹900"):
        assert needle in html, (theme, needle)


def test_hostile_text_in_every_new_field_is_inert():
    p = Profile.model_validate({
        **OLD, "selling_mode": "pickup_india", "city": EVIL, "area": EVIL, "shipping_note": EVIL, "cancellation_preset": "custom",
        "cancellation_text": EVIL, "allergens": EVIL, "time_slots": [EVIL], "dispatch_days": 2, "delivery_areas": "Baner",
        "products": [{"name": EVIL, "price_inr": 10, "food_mark": EVIL}]})
    for page in ("home", "privacy"):
        html = render_site(p, page=page, shop="x", form_error=EVIL, form_values={"delivery_address": EVIL, "delivery_pin": EVIL,
                                                                                   "wanted_date": EVIL, "time_slot": EVIL})
        assert "<img src=x" not in html and "<script>alert(1)" not in html and 'onerror=alert(1)>' not in html
    order_view = {"ref": "LW-1", "items": [{"name": EVIL, "qty": 1, "price_inr": 10}], "total_inr": 10, "customer_name": EVIL,
                  "customer_phone": "1", "note": EVIL, "fulfilment": "delivery", "delivery_pin": EVIL, "wanted_date": EVIL,
                  "time_slot": EVIL, "fee_inr": 5, "payment_terms": "advance", "pay_now_inr": 5, "pay_later_inr": 5}
    html = render_site(p, page="thanks", order=order_view)
    assert "<img src=x" not in html and "<script>alert(1)" not in html


def test_an_order_saved_before_s15_still_reads_and_lists(client, engine):
    biz = shop(client)
    sign_in(client, "owner@example.org")
    with Session(engine) as s:
        s.add(Order(business_id=biz["id"], customer_name="Old", customer_phone="9876543210", total_inr=100, ref="LW-OLDOLDOL"))
        s.commit()
    o = client.get(f"/api/businesses/{biz['id']}/orders").json()[0]
    assert o["fulfilment"] == "" and o["delivery_address"] == "" and o["payment_label"] == ""  # no terms were saved with it
    assert o["wanted_date"] == "" and o["paid_action"] == "Mark paid"


def test_the_order_email_lists_how_when_and_what_is_due(client, mailer):
    shop(client, payment_terms="advance", advance_percent=50, cancellation_preset="full_24h", time_slots=["10am-1pm"])
    order(client, **delivery(time_slot="10am-1pm"))
    body = next(m["body"] for m in mailer.sent if "New order" in m["subject"])
    for needle in ("Total: ₹730", "- Delivery: ₹80", "Paid now (asked of the customer): ₹365", "Due on delivery: ₹365",
                   "How: LOCAL DELIVERY", ADDRESS.split(",")[0], "PIN code: 411045", f"Wanted by: {ful.nice_date(ful.today_ist() + timedelta(days=5))}, 10am-1pm",
                   ful.CANCELLATION_PRESETS["full_24h"]):
        assert needle in body, needle


def test_the_fixture_marks_are_labelled_placeholders():
    for name in ("meera_cakes", "tiffin_service", "tiffin_hinglish"):
        raw = json.loads((Path(__file__).parent / "fixtures" / "claude" / f"reader_{name}.json").read_text(encoding="utf-8"))
        # S16: re-captured live files drop the label; any file still hand-written must keep it.
        assert "allergens" in raw and (not raw.get("_food_placeholder") or "_note" in raw)
        assert any(x["food_mark"] == "veg" for x in raw["products"])
    assert GO_LIVE["selling_mode"] == "pickup_local"
