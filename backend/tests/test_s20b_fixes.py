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
