"""Session 19D: "View shop" / "Preview" on My shops.

`live_url` is the shop's real public address, built on the server from the launch plan / subdomain and
APP_DOMAIN. It is set only for a real launched shop (also when paused, so the owner can see what customers
see); a practice or draft shop gets None (it is not on the internet: the owner uses the private preview).
Only the shop's owner gets it: another seller, a guest and a logged-out visitor never see the shop at all.
"""

from sqlmodel import Session

from app.models import Business
from app.sites.hosts import site_url
from tests.conftest import sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_s9_phase1 import launched_shop

OWNER = "meera@example.org"


def mine(client, bid: int) -> dict:
    (row,) = [b for b in client.get("/api/businesses").json() if b["id"] == bid]
    return row


def test_draft_shop_has_no_live_url(client):
    sign_in(client, OWNER)
    biz = meera(client)
    assert biz["live_url"] is None
    assert mine(client, biz["id"])["live_url"] is None


def test_practice_launch_never_links_a_public_address(client):
    sign_in(client, OWNER)
    biz = meera(client)
    p = approve(client, plan(client, biz))
    assert p["status"] == "done"
    row = mine(client, biz["id"])
    assert row["status"] == "live" and row["practice"] is True
    assert row["live_url"] is None and row["public"] is False


def test_real_live_shop_gets_its_address_from_the_server(client, engine, settings):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    row = mine(client, biz["id"])
    assert row["live_url"] == site_url(biz["subdomain"], settings)
    assert row["live_url"].endswith(f"://{biz['subdomain']}.{settings.app_domain}/")
    assert client.get(f"/api/businesses/{biz['id']}").json()["live_url"] == row["live_url"]


def test_paused_or_held_live_shop_keeps_its_address(client, engine, settings):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.paused, b.review = True, "held"
        s.add(b)
        s.commit()
    row = mine(client, biz["id"])
    assert row["public"] is False and row["paused"] is True
    assert row["live_url"] == site_url(biz["subdomain"], settings)


def test_only_the_owner_sees_it(client, new_client, engine):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    other = new_client()
    sign_in(other, "imran@example.org")
    assert all(b["id"] != biz["id"] for b in other.get("/api/businesses").json())
    assert other.get(f"/api/businesses/{biz['id']}").status_code == 404
    stranger = new_client()
    assert stranger.get("/api/businesses").json() == []
    assert stranger.get(f"/api/businesses/{biz['id']}").status_code in (401, 403, 404)
