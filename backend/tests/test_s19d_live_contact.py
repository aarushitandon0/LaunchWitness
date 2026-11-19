"""Session 19D (Part 7a): customers only ever see a live shop's last CONFIRMED WhatsApp number and UPI ID / name.

Changing them on a live shop keeps the shop live, resets her confirmation (as before) and keeps the old, confirmed
values on every customer-facing page (shop, order thank-you, UPI link) until she confirms the new ones. My shops
says what she still has to confirm. A practice shop shows changes at once (nobody else sees it).
"""

from sqlmodel import Session, select

from app.models import AuditEvent
from tests.conftest import publish, ready_for_real, sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_s9_phase1 import HOST, ORDER

OLD_UPI, NEW_UPI = "meera.cakes@okaxis", "someone.else@ybl"
OLD_WA_DIGITS, NEW_WA = "9876543210", "91234 56789"


def live_shop(client, engine) -> dict:
    sign_in(client, "meera@example.org")
    biz = meera(client)
    ready_for_real(client, biz["id"])
    assert approve(client, plan(client, biz))["status"] == "done"
    publish(engine, biz["id"])
    return client.get(f"/api/businesses/{biz['id']}").json()


def edit(client, biz: dict, **changes) -> dict:
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], **changes}, "subdomain": cur["subdomain"]})
    assert r.status_code == 200, r.text
    return r.json()


def shop(client) -> str:
    r = client.get("/", headers=HOST)
    assert r.status_code == 200
    return r.text


def order_page(client) -> str:
    r = client.post("/order", data=ORDER, headers=HOST)
    assert r.status_code == 200, r.text
    return r.text


def wa(html: str, number: str) -> bool:
    return f"wa.me/91{number}" in html


def test_changed_upi_stays_old_for_customers_until_she_confirms(client, engine):
    biz = live_shop(client, engine)
    assert OLD_UPI in shop(client)
    edit(client, biz, payment_terms="upfront")  # so the thank-you page carries a UPI link for the full amount
    out = edit(client, biz, upi_id=NEW_UPI, upi_display_name="Someone Else")
    assert out["status"] == "live" and out["public"] is True  # still live
    assert out["confirm_new"] == ["upi"]
    page, thanks = shop(client), order_page(client)
    for html in (page, thanks):
        assert NEW_UPI not in html and "Someone Else" not in html
    assert f"upi://pay?pa={OLD_UPI}" in thanks.replace("&amp;", "&")  # the payment link carries the confirmed ID
    # she sees her own new value (Review), only customers get the confirmed one
    assert out["profile"]["upi_id"] == NEW_UPI
    assert client.post(f"/api/businesses/{biz['id']}/confirm", json={"what": "upi"}).status_code == 200
    assert client.get(f"/api/businesses/{biz['id']}").json()["confirm_new"] == []
    assert NEW_UPI in shop(client)


def test_changed_whatsapp_stays_old_until_confirmed(client, engine):
    biz = live_shop(client, engine)
    out = edit(client, biz, whatsapp=NEW_WA)
    assert out["confirm_new"] == ["whatsapp"]
    page = shop(client)
    assert not wa(page, "9123456789") and wa(page, OLD_WA_DIGITS)
    assert client.post(f"/api/businesses/{biz['id']}/confirm", json={"what": "whatsapp"}).status_code == 200
    assert wa(shop(client), "9123456789")


def test_both_changed_twice_keeps_the_first_confirmed_values(client, engine):
    biz = live_shop(client, engine)
    edit(client, biz, upi_id=NEW_UPI, whatsapp=NEW_WA)
    out = edit(client, biz, upi_id="third.one@okicici", whatsapp="99999 11111")
    assert out["confirm_new"] == ["upi", "whatsapp"]
    page = shop(client)
    assert OLD_UPI in page and "third.one" not in page and NEW_UPI not in page
    assert wa(page, OLD_WA_DIGITS)


def test_edit_is_audited_without_the_values(client, engine):
    biz = live_shop(client, engine)
    edit(client, biz, upi_id=NEW_UPI)
    with Session(engine) as s:
        rows = s.exec(select(AuditEvent).where(AuditEvent.business_id == biz["id"],
                                               AuditEvent.action == "confirmation_reset")).all()
    assert rows and "customers still see the confirmed one" in rows[-1].detail
    assert all(NEW_UPI not in r.detail and OLD_UPI not in r.detail for r in rows)


def test_marker_and_orders_still_work_after_an_edit(client, engine):
    biz = live_shop(client, engine)
    edit(client, biz, upi_id=NEW_UPI, tagline="Fresh eggless cakes, made to order")
    assert 'name="lw-shop"' in shop(client)
    assert "Thank you" in order_page(client) or "thank" in order_page(client).lower()
    r = client.post(f"/api/businesses/{biz['id']}/checks")
    assert r.status_code in (202, 409), r.text  # a manual check round starts (409 = one already running)


def test_practice_shop_shows_changes_at_once(client):
    sign_in(client, "meera@example.org")
    biz = meera(client)
    ready_for_real(client, biz["id"])
    out = edit(client, biz, upi_id=NEW_UPI)
    assert out["confirm_new"] == []  # nothing held back: no customer sees a practice shop
    html = client.get(f"/api/businesses/{biz['id']}/preview").text
    assert NEW_UPI in html


def test_removing_whatsapp_takes_effect_at_once(client, engine):
    biz = live_shop(client, engine)
    edit(client, biz, whatsapp=NEW_WA)
    out = edit(client, biz, whatsapp="")
    assert out["confirm_new"] == []
    assert "wa.me/" not in shop(client)
