"""S17: back to Describe. The shop keeps her original words; "Read it again" re-reads them for THIS shop (no second
shop). The fresh reading wins where it found something; what it didn't find keeps what she set (WhatsApp, UPI,
delivery areas, address). Only before launch, same daily limit as describing a shop, item photos follow their items."""

from sqlmodel import Session, select

from app.models import AuditEvent, Business, Photo
from tests.conftest import publish_client
from tests.test_m2_site import create, sample
from tests.test_s12_photos import jpeg


def reread(client, biz_id: int, seller: str):
    s = sample(seller)
    return client.post(f"/api/businesses/{biz_id}/reread", data={"description": s["description"], "price_list": s["price_list"]})


def test_reread_replaces_the_reading_on_the_same_shop(client, engine):
    biz = create(client)
    r = reread(client, biz["id"], "tailor")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] == biz["id"] and out["subdomain"] == biz["subdomain"]  # same shop, same address
    assert out["name"] != biz["name"]
    assert out["description"] == sample("tailor")["description"]  # her words are kept for next time
    with Session(engine) as s:
        assert len(s.exec(select(Business)).all()) == 1
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "read_business",
                                               AuditEvent.detail.contains("read again"))).first()


def test_what_the_reading_did_not_find_keeps_what_she_set(client):
    biz = create(client)
    profile = {**biz["profile"], "whatsapp": "9876543210", "upi_id": "meera@okaxis", "upi_display_name": "Meera Iyer",
               "delivery_areas": "Baner, Aundh"}
    assert client.put(f"/api/businesses/{biz['id']}", json={"profile": profile, "subdomain": "meerasbakes"}).status_code == 200
    out = reread(client, biz["id"], "meera_cakes").json()
    assert out["subdomain"] == "meerasbakes"
    assert out["profile"]["upi_id"] == "meera@okaxis" and out["profile"]["upi_display_name"] == "Meera Iyer"
    assert out["profile"]["delivery_areas"]  # kept (or found again), never emptied
    assert out["profile"]["whatsapp"]


def test_item_photos_follow_their_items_and_vanish_with_them(client, engine):
    biz = create(client)
    first = biz["profile"]["products"][0]["name"]
    up = client.post(f"/api/businesses/{biz['id']}/photos", files={"file": ("a.jpg", jpeg(400, 300), "image/jpeg")},
                     data={"item": first})
    assert up.status_code == 201
    assert reread(client, biz["id"], "meera_cakes").status_code == 200  # same items: the photo stays
    with Session(engine) as s:
        assert [p.item for p in s.exec(select(Photo)).all()] == [first]
    assert reread(client, biz["id"], "tailor").status_code == 200  # no cakes any more: the photo goes
    with Session(engine) as s:
        assert s.exec(select(Photo).where(Photo.item != "")).all() == []


def test_not_after_launch(client):
    biz = create(client)
    publish_client(client, biz["id"])  # launched (live)
    r = reread(client, biz["id"], "tailor")
    assert r.status_code == 409 and "Review" in r.json()["detail"]


def test_only_the_owner(client, new_client):
    biz = create(client)
    assert reread(new_client(), biz["id"], "tailor").status_code in (401, 403, 404)


def test_counts_toward_the_daily_describe_limit(client, make_settings):
    from app.config import get_settings
    from tests.test_m4_report import sign_in

    client.app.dependency_overrides[get_settings] = lambda: make_settings(user_describes_per_day=2)
    sign_in(client, "meera@example.org")
    biz = create(client)
    assert reread(client, biz["id"], "tailor").status_code == 200  # second Claude reading today
    r = reread(client, biz["id"], "meera_cakes")
    assert r.status_code == 429 and "tomorrow" in r.json()["detail"]
