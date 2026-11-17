"""S10.5 §3: the owner's Orders page: status (owner only, audited), WhatsApp to the customer, counts, email."""

from urllib.parse import parse_qs, unquote, urlsplit

import pytest
from sqlmodel import Session, select

from app.models import AuditEvent, Order
from app.sites.orders import STATUS_STEPS, can_move, customer_whatsapp_link
from tests.conftest import pickup, publish, sign_in
from tests.test_m3_launch import meera


def place(shopper, name="Priya", phone="9876543210", token="a" * 20):
    form = {"customer_name": name, "customer_phone": phone, "qty_0": "1", "order_token": token, **pickup()}
    r = shopper.post("/order", data=form, headers={"host": "meera.localhost"})
    assert r.status_code == 200, r.text


@pytest.fixture
def shop(client, new_client, engine):
    sign_in(client, "owner@example.org")
    biz = meera(client)
    publish(engine, biz["id"])
    place(new_client())
    return biz


def only_order(engine) -> Order:
    with Session(engine) as s:
        return s.exec(select(Order)).one()


def test_owner_sees_orders_with_full_phone_and_whatsapp(client, shop):
    rows = client.get(f"/api/businesses/{shop['id']}/orders").json()
    assert len(rows) == 1
    o = rows[0]
    assert o["status"] == "new" and o["next_statuses"] == ["confirmed", "cancelled"]
    assert o["customer_phone"] == "9876543210"
    assert o["whatsapp_url"].startswith("https://wa.me/919876543210?text=")
    assert o["tel_url"] == "tel:+919876543210"
    assert client.get("/api/businesses").json()[0]["new_orders"] == 1


def test_status_walks_forward_and_is_audited(client, shop, engine):
    oid = only_order(engine).id
    url = f"/api/businesses/{shop['id']}/orders/{oid}/status"
    for step in ("confirmed", "paid", "done"):
        r = client.post(url, json={"status": step})
        assert r.status_code == 200 and r.json()["status"] == step
    assert client.post(url, json={"status": "cancelled"}).status_code == 409  # done is final
    assert client.get("/api/businesses").json()[0]["new_orders"] == 0
    with Session(engine) as s:
        rows = s.exec(select(AuditEvent).where(AuditEvent.action == "order_status")).all()
    assert [r.detail.split(": ")[1] for r in rows] == ["new -> confirmed", "confirmed -> paid", "paid -> done"]
    assert all("9876543210" not in (r.detail + r.target) for r in rows)  # the phone never reaches the audit log


@pytest.mark.parametrize("to", ["done", "paid", "new", "shipped"])
def test_illegal_jumps_are_refused(client, shop, engine, to):
    oid = only_order(engine).id
    r = client.post(f"/api/businesses/{shop['id']}/orders/{oid}/status", json={"status": to})
    assert r.status_code in (409, 422)
    assert only_order(engine).status == "new"


def test_transition_table():
    assert can_move("new", "confirmed") and can_move("confirmed", "done") and can_move("paid", "cancelled")
    assert not can_move("new", "done") and not can_move("cancelled", "new") and not can_move("done", "paid")
    assert STATUS_STEPS["done"] == () and STATUS_STEPS["cancelled"] == ()


def test_only_the_owner_sees_and_changes_status(client, shop, engine, new_client):
    oid = only_order(engine).id
    other = new_client()
    sign_in(other, "other@example.org")
    meera(other, "other-shop")
    url = f"/api/businesses/{shop['id']}/orders/{oid}/status"
    assert other.get(f"/api/businesses/{shop['id']}/orders").status_code == 404
    assert other.post(url, json={"status": "confirmed"}).status_code == 404
    # someone else's order id under your OWN shop is 404 too
    own = other.get("/api/businesses").json()[0]["id"]
    assert other.post(f"/api/businesses/{own}/orders/{oid}/status", json={"status": "confirmed"}).status_code == 404
    assert new_client().post(url, json={"status": "confirmed"}).status_code == 401
    assert only_order(engine).status == "new"


def test_test_orders_are_hidden_and_cannot_be_changed(client, shop, engine):
    with Session(engine) as s:
        o = s.exec(select(Order)).one()
        o.is_test = True
        s.add(o)
        s.commit()
        oid = o.id
    assert client.get(f"/api/businesses/{shop['id']}/orders").json() == []
    assert client.get("/api/businesses").json()[0]["new_orders"] == 0
    assert client.post(f"/api/businesses/{shop['id']}/orders/{oid}/status", json={"status": "confirmed"}).status_code == 404


@pytest.mark.parametrize("name", ["Asha & Ravi", "Zoë 🎂 Sharma", "Mary  Ann", "R&D#1 ?x=1"])
def test_whatsapp_links_are_encoded(name):
    o = Order(business_id=1, customer_name=name, customer_phone="+91 98765-43210", ref="LW-ABCD2345", total_inr=1250)
    url = customer_whatsapp_link("Cakes & Co. 🍰", o)
    parts = urlsplit(url)
    assert parts.netloc == "wa.me" and parts.path == "/919876543210"
    assert " " not in url and "&" not in parts.query.split("=", 1)[1] and "#" not in url
    text = parse_qs(parts.query)["text"][0]
    assert text.startswith(f"Hi {name.split()[0]}, this is Cakes & Co. 🍰.")
    assert "LW-ABCD2345" in text and "₹1,250" in text
    assert unquote(parts.query.split("=", 1)[1]) == text


def test_no_whatsapp_link_for_a_bad_number():
    assert customer_whatsapp_link("Shop", Order(business_id=1, customer_name="A", customer_phone="12345")) is None


def test_order_email_has_ref_links_and_orders_page(client, shop, mailer):
    mail = next(m for m in mailer.sent if "New order" in m["subject"])
    body = mail["body"]
    assert "LW-" in body and "tel:+919876543210" in body and "https://wa.me/919876543210?text=" in body
    assert f"/#/b/{shop['id']}/orders" in body
