"""Session 19D (Part 7c): edits to a LIVE shop's words go through the policy check again.

- OK -> published at once. Hold -> the shop stays LIVE with its last approved version; her edit is saved as pending
  for the team and she is told plainly. Never unpublished because of an edit.
- Claude unavailable -> held (fail closed), old version stays live.
- Words unchanged (prices, hours, New badge) -> no check, published at once.
- The team publishes or discards a held edit (Team page); both audited, without customer data.
"""

import pytest
from sqlmodel import Session, select

from app.agents.claude_client import ClaudeError
from app.models import AuditEvent, Business
from tests.conftest import ADMIN_TOKEN
from tests.test_s19d_live_contact import edit, live_shop, shop

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def audit_rows(engine, bid: int, action: str) -> list[AuditEvent]:
    with Session(engine) as s:
        return list(s.exec(select(AuditEvent).where(AuditEvent.business_id == bid, AuditEvent.action == action)).all())


def test_clean_word_edit_publishes_at_once(client, engine):
    biz = live_shop(client, engine)
    out = edit(client, biz, tagline="Fresh eggless mango cakes this week")
    assert out["pending_edit"] is None
    assert "Fresh eggless mango cakes this week" in shop(client)
    (row,) = [r for r in audit_rows(engine, biz["id"], "profile_saved") if "tagline" in r.detail]
    assert "fields: tagline" in row.detail and "mango" not in row.detail  # field names only, never the words


def test_held_edit_keeps_the_old_version_live(client, engine):
    biz = live_shop(client, engine)
    before = shop(client)
    out = edit(client, biz, tagline="Cakes, and whisky bottles on order")  # out of scope: plain code holds it
    assert out["pending_edit"] and out["pending_edit"]["reason"]
    assert out["status"] == "live" and out["public"] is True  # never unpublished by an edit
    assert out["profile"]["tagline"] == "Cakes, and whisky bottles on order"  # she keeps editing her own version
    page = shop(client)
    assert "whisky" not in page and page.count('name="lw-shop"') == before.count('name="lw-shop"') == 1
    assert audit_rows(engine, biz["id"], "edit_held")
    # a price-only change while held still carries the held words, so it waits too
    products = out["profile"]["products"]
    again = edit(client, biz, products=[{**products[0], "price_inr": products[0]["price_inr"] + 50}, *products[1:]])
    assert again["pending_edit"] is not None and "whisky" not in shop(client)
    # she takes the words back out: the edit goes up and nothing waits any more
    clean = edit(client, biz, tagline="Fresh eggless cakes, made to order")
    assert clean["pending_edit"] is None and "Fresh eggless cakes, made to order" in shop(client)


def test_claude_unavailable_holds_the_edit(client, engine, claude, monkeypatch):
    biz = live_shop(client, engine)

    def down(**_kw):
        raise ClaudeError("down")

    monkeypatch.setattr(claude, "ask_json", down)
    out = edit(client, biz, about="We now also bake for birthdays.")
    assert out["pending_edit"] is not None
    assert "We now also bake for birthdays." not in shop(client)


def test_non_word_edits_are_not_checked(client, engine, claude, monkeypatch):
    biz = live_shop(client, engine)

    def boom(**_kw):
        raise AssertionError("no policy call for a price change")

    monkeypatch.setattr(claude, "ask_json", boom)
    products = client.get(f"/api/businesses/{biz['id']}").json()["profile"]["products"]
    out = edit(client, biz, products=[{**products[0], "price_inr": 999}, *products[1:]], hours="Mon-Sat, 9am-8pm")
    assert out["pending_edit"] is None and "999" in shop(client)


@pytest.mark.parametrize("decision", ["publish", "discard"])
def test_team_publishes_or_discards_a_held_edit(client, engine, decision):
    biz = live_shop(client, engine)
    edit(client, biz, tagline="Cakes, and whisky bottles on order")
    shops = client.get("/api/admin/businesses", headers=ADMIN).json()
    (row,) = [s for s in shops if s["id"] == biz["id"]]
    assert row["pending_edit"] and row["pending_edit"]["reason"]
    r = client.post(f"/api/admin/businesses/{biz['id']}/{decision}-edit", headers=ADMIN)
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        assert b.pending_profile_json == "" and b.status == "live" and not b.practice
    assert ("whisky" in shop(client)) is (decision == "publish")
    assert audit_rows(engine, biz["id"], "profile_saved" if decision == "publish" else "edit_discarded")
    assert client.post(f"/api/admin/businesses/{biz['id']}/{decision}-edit", headers=ADMIN).status_code == 409


def test_only_the_team_can_publish_a_held_edit(client, new_client, engine):
    biz = live_shop(client, engine)
    edit(client, biz, tagline="Cakes, and whisky bottles on order")
    for c in (client, new_client()):  # the owner herself, and a stranger
        assert c.post(f"/api/admin/businesses/{biz['id']}/publish-edit").status_code in (401, 403, 404)
    assert "whisky" not in shop(client)


def test_practice_shops_are_never_held(client):
    from tests.conftest import sign_in
    from tests.test_m3_launch import meera

    sign_in(client, "meera@example.org")
    biz = meera(client)
    out = edit(client, biz, tagline="Cakes, and whisky bottles on order")
    assert out["pending_edit"] is None  # not on the internet: the go-live check runs at launch
