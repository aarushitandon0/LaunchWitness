"""Session 20B: fixes to S20 Part A before it goes live.

- the status link's token is stored only as its SHA-256 (like every other token);
- the thank-you / status page greets the customer by first name only;
- pay-on-delivery orders never get UPI details or the "I've paid" form;
- shop hosts answer /favicon.ico with 204 (the app host keeps its own).
"""

import hashlib

from sqlmodel import Session, select

from app.models import Order
from tests.test_s20_payments import HOST, ORDER, claim, live_shop, place


def real_order(engine) -> Order:
    with Session(engine) as s:
        return s.exec(select(Order).where(Order.is_test == False)).first()  # noqa: E712


# ---------- 1. the status token is stored hashed ----------

def test_status_token_is_stored_only_as_its_sha256(client, engine):
    live_shop(client, engine)
    html, tok = place(client)
    o = real_order(engine)
    assert o.status_token == hashlib.sha256(tok.encode()).hexdigest()
    assert tok not in o.status_token and tok not in o.model_dump_json()  # the raw token is nowhere in the row
    page = client.get(f"/order/{tok}", headers=HOST)
    assert page.status_code == 200 and f'href="/order/{tok}"' in page.text  # the link on the page is the raw one
    # the stored hash is not itself a key to the page
    assert client.get(f"/order/{o.status_token}", headers=HOST).status_code == 404
    assert claim(client, o.status_token).status_code == 404
    assert claim(client, tok).status_code == 303


def test_a_resent_form_issues_a_fresh_link_and_the_old_one_stops(client, engine):
    live_shop(client, engine)
    form = {**ORDER, "order_token": "resend-token-0123456789"}
    _, first = place(client, **form)
    _, second = place(client, **form)  # the same form sent again: no new order, a fresh link
    with Session(engine) as s:
        assert len(s.exec(select(Order).where(Order.is_test == False)).all()) == 1  # noqa: E712
    assert first != second
    assert client.get(f"/order/{second}", headers=HOST).status_code == 200
    assert client.get(f"/order/{first}", headers=HOST).status_code == 404


# ---------- 2. first name only ----------

def test_thank_you_and_status_page_show_the_first_name_only(client, engine):
    live_shop(client, engine)
    html, tok = place(client, customer_name="Riya Sharma Kapoor", customer_phone="91234 00077")
    page = client.get(f"/order/{tok}", headers=HOST).text
    for h in (html, page):
        assert "<h1>Thank you, Riya!</h1>" in h
        assert "Sharma" not in h and "Kapoor" not in h
        assert "00077" not in h and "9123400077" not in h  # the phone was never on the page
    assert real_order(engine).customer_name == "Riya Sharma Kapoor"  # the shop still has the full name


# ---------- 3. privacy text names the team's access ----------

def test_privacy_text_says_the_team_can_open_a_screenshot_and_it_is_logged(client, engine):
    live_shop(client, engine)
    page = client.get("/privacy", headers=HOST).text
    assert "The LaunchWitness team can also open a screenshot when it is helping the shop" in page
    assert "that is logged" in page


# ---------- 5. pay on delivery: no UPI details at all ----------

def test_pay_on_delivery_gets_no_upi_details_and_no_claim_form(client, engine):
    from tests.conftest import publish, ready_for_real, sign_in
    from tests.test_m3_launch import approve, meera, plan
    from tests.test_s20_payments import UPI

    sign_in(client, "meera@example.org")
    biz = meera(client)
    ready_for_real(client, biz["id"], payment_terms="on_delivery", upi_display_name="MEERA BAKES")
    assert approve(client, plan(client, biz))["status"] == "done"
    publish(engine, biz["id"])
    assert client.get(f"/api/businesses/{biz['id']}").json()["profile"]["upi_id"] == UPI  # she does have a UPI ID
    html, tok = place(client)
    page = client.get(f"/order/{tok}", headers=HOST)
    assert page.status_code == 200
    for h in (html, page.text):
        assert "upi://" not in h.lower() and UPI not in h and "MEERA BAKES" not in h
        assert "UPI payment QR code" not in h
        assert "claim-form" not in h and "/paid" not in h and 'id="claim"' not in h
        assert "Nothing to pay now" in h  # the page still says when to pay
    assert claim(client, tok).status_code == 409  # and a hand-made claim is refused: nothing to pay now
    from app.models import PaymentClaim

    with Session(engine) as s:
        assert s.exec(select(PaymentClaim)).first() is None


# ---------- 7. favicon on shop hosts ----------

def test_shop_host_answers_favicon_with_204_and_the_app_host_does_not(client, engine):
    live_shop(client, engine)
    r = client.get("/favicon.ico", headers=HOST)
    assert r.status_code == 204 and r.content == b""
    assert client.get("/favicon.ico").status_code != 204  # the app's own icon is untouched
    assert client.get("/favicon.ico", headers={"host": "nobody-here.localhost"}).status_code == 404  # no such shop
    assert client.get("/favicon.icox", headers=HOST).status_code == 404  # exactly that one path
