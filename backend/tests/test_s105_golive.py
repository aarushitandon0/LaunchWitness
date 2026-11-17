"""S10.5 §5: the go-live checklist. Only "Launch for real" is gated; drafts and practice stay easy."""

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app.agents.reader import Profile, indian_mobile, instagram_handle
from app.models import AuditEvent, Business
from app.sites.hosts import slug_problem
from app.sites.render import render_site
from tests.conftest import ADMIN_TOKEN, GO_LIVE, ready_for_real, set_user, sign_in
from tests.test_m3_launch import approve, meera, plan


@pytest.fixture
def owner(client, engine):
    sign_in(client, "owner@example.org")
    set_user(engine, "owner@example.org", status="approved")
    return client


def real(client, biz_id):
    return client.post(f"/api/businesses/{biz_id}/plans", json={"mode": "sandbox", "real": True})


def missing_keys(r) -> set[str]:
    return set(filter(None, r.headers.get("x-missing", "").split(",")))


def test_ready_shop_can_launch_for_real(owner):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    assert real(owner, biz["id"]).status_code == 201


def test_fresh_shop_is_refused_with_everything_missing_in_plain_words(owner):
    biz = meera(owner)
    r = real(owner, biz["id"])
    assert r.status_code == 409
    assert missing_keys(r) == {"whatsapp", "upi", "fulfilment", "agreements", "preview"}  # Meera gave her hours
    assert r.json()["detail"].startswith("Before your shop can go live, please finish:")
    assert "whatsapp number" in r.json()["detail"]


def undo(client, biz_id, **profile):
    biz = client.get(f"/api/businesses/{biz_id}").json()
    r = client.put(f"/api/businesses/{biz_id}", json={"profile": {**biz["profile"], **profile}, "subdomain": biz["subdomain"]})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("change,key", [
    ({"whatsapp": ""}, "whatsapp"),
    ({"whatsapp": "91234 56789"}, "whatsapp"),  # a different number: the old confirmation no longer counts
    ({"upi_id": "other@okicici"}, "upi"),
    ({"upi_display_name": "Someone Else"}, "upi"),
    ({"upi_display_name": ""}, "upi"),
    ({"pickup_available": False, "delivery_available": False}, "fulfilment"),
    ({"delivery_areas": ""}, "fulfilment"),  # Meera delivers: areas are needed
    ({"pickup_available": True, "delivery_available": False, "area": ""}, "fulfilment"),
    ({"hours": ""}, "rules"),
])
def test_each_missing_profile_item_refuses_a_real_launch(owner, change, key):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    undo(owner, biz["id"], **change)
    r = real(owner, biz["id"])
    assert r.status_code == 409 and key in missing_keys(r), r.text


def test_no_priced_item_refuses(owner):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    products = [{**p, "price_inr": 0} for p in owner.get(f"/api/businesses/{biz['id']}").json()["profile"]["products"]]
    undo(owner, biz["id"], products=products)
    assert "shop" in missing_keys(real(owner, biz["id"]))


def test_agreements_and_preview_are_needed(owner, engine):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.terms_at, b.previewed_at = None, None
        s.add(b)
        s.commit()
    assert missing_keys(real(owner, biz["id"])) == {"agreements", "preview"}
    assert owner.post(f"/api/businesses/{biz['id']}/confirm", json={"what": "agreements", "own_goods": True}).status_code == 422


def test_checklist_is_checked_again_at_approval(owner):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    p = real(owner, biz["id"]).json()
    undo(owner, biz["id"], hours="")
    r = owner.post(f"/api/plans/{p['id']}/approve", json={"approved_by": "M"})
    assert r.status_code == 409 and "rules" in missing_keys(r)


def test_drafts_and_practice_are_never_blocked(owner):
    biz = meera(owner)  # nothing of the checklist done
    assert approve(owner, plan(owner, biz))["status"] == "done"  # practice launch works
    assert owner.put(f"/api/businesses/{biz['id']}", json={"profile": owner.get(f"/api/businesses/{biz['id']}").json()["profile"],
                                                            "subdomain": biz["subdomain"]}).status_code == 200


def test_confirmation_resets_when_the_number_or_upi_changes(owner, engine):
    biz = meera(owner)
    out = ready_for_real(owner, biz["id"])
    assert out["confirmed"]["whatsapp_at"] and out["confirmed"]["upi_at"]
    undo(owner, biz["id"], whatsapp="91234 56789", upi_id="new@okhdfc")
    out = owner.get(f"/api/businesses/{biz['id']}/golive").json()
    assert out["confirmed"]["whatsapp_at"] is None and out["confirmed"]["upi_at"] is None
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        assert (b.wa_confirmed, b.upi_confirmed) == ("", "")
        resets = s.exec(select(AuditEvent).where(AuditEvent.action == "confirmation_reset")).all()
    assert {r.detail.split(" changed")[0] for r in resets} == {"WhatsApp number", "UPI ID or name"}
    # the same number written differently is the same number: no reset
    ready_for_real(owner, biz["id"])
    undo(owner, biz["id"], whatsapp="+91 98765-43210")
    assert owner.get(f"/api/businesses/{biz['id']}/golive").json()["confirmed"]["whatsapp_at"]


def test_only_the_owner_confirms(owner, new_client, engine):
    biz = meera(owner)
    undo(owner, biz["id"], **GO_LIVE)
    url = f"/api/businesses/{biz['id']}/confirm"
    other = new_client()
    sign_in(other, "other@example.org")
    assert other.post(url, json={"what": "whatsapp"}).status_code == 404
    assert other.get(f"/api/businesses/{biz['id']}/golive").status_code == 404
    team = new_client()  # the team (command-line token)
    team_h = {"X-Admin-Token": ADMIN_TOKEN}
    assert team.get(f"/api/businesses/{biz['id']}/golive", headers=team_h).status_code == 200  # the team may look…
    assert team.post(url, json={"what": "whatsapp"}, headers=team_h).status_code == 404  # …but never confirms for her
    assert team.get(f"/api/businesses/{biz['id']}/preview", headers=team_h).status_code == 200
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        assert b.wa_confirmed == "" and b.previewed_at is None  # the team's look doesn't count either
    assert new_client().post(url, json={"what": "whatsapp"}).status_code == 401


def test_golive_offers_the_two_owner_tests(owner):
    biz = meera(owner)
    undo(owner, biz["id"], **GO_LIVE)
    out = owner.get(f"/api/businesses/{biz['id']}/golive").json()
    assert out["whatsapp_test_url"] == "https://wa.me/919876543210"
    assert out["upi_test"]["uri"].startswith("upi://pay?pa=meera.cakes@okaxis&") and "am=1.00" in out["upi_test"]["uri"]
    assert out["upi_test"]["qr_svg"].startswith("<svg") and out["upi_test"]["name"] == "Meera Joshi"


def test_report_shows_confirmed_by_you_lines_apart_from_proof(owner):
    biz = meera(owner)
    ready_for_real(owner, biz["id"])
    rep = owner.get(f"/api/businesses/{biz['id']}/report").json()
    lines = {x["what"]: x for x in rep["confirmed_by_you"]}
    assert lines["whatsapp"]["at"] and lines["upi"]["at"] and lines["got_it"]["at"] is None
    assert "9876543210" not in str(rep["confirmed_by_you"])


# ---------- validation ----------

@pytest.mark.parametrize("raw,want", [
    ("98765 43210", "+919876543210"), ("+91 98765-43210", "+919876543210"), ("09876543210", "+919876543210"),
    ("919876543210", "+919876543210"), ("6000000000", "+916000000000"),
    ("5876543210", None), ("98765", None), ("+1 415 555 0100", None), ("98765 4321O", None), ("+44 7700 900123", None),
])
def test_whatsapp_must_be_an_indian_mobile(raw, want):
    assert indian_mobile(raw) == want
    if want is None:
        with pytest.raises(ValidationError):
            Profile(name="x", products=[{"name": "a", "price_inr": 1}], whatsapp=raw)


@pytest.mark.parametrize("vpa,ok", [
    ("meera.cakes@okaxis", True), ("9876543210@ybl", True), ("a_b-c@paytm", True),
    ("a@b", False), ("meera@ok-axis", False), ("meera cakes@okaxis", False), ("@okaxis", False), ("meera@", False),
    ("meera@okaxis@x", False),
])
def test_upi_id_format(vpa, ok):
    if ok:
        Profile(name="x", products=[{"name": "a", "price_inr": 1}], upi_id=vpa)
    else:
        with pytest.raises(ValidationError):
            Profile(name="x", products=[{"name": "a", "price_inr": 1}], upi_id=vpa)


@pytest.mark.parametrize("raw,want", [
    ("@meera.bakes", "meera.bakes"), ("meera_bakes", "meera_bakes"), ("https://instagram.com/meera.bakes/", "meera.bakes"),
    ("https://www.instagram.com/meera.bakes?igsh=abc", "meera.bakes"),
    (".meera", None), ("meera.", None), ("mee..ra", None), ("meera bakes", None), ("<script>", None), ("x" * 31, None),
    ("javascript:alert(1)", None),
])
def test_instagram_handle(raw, want):
    assert instagram_handle(raw) == want


@pytest.mark.parametrize("slug,ok", [("meera-cakes", True), ("abc", True), ("ab", False), ("-meera", False),
                                     ("meera_cakes", False), ("Meera", False), ("api", False)])
def test_slug_rules(slug, ok):
    assert (slug_problem(slug) is None) == ok


def test_public_shop_never_shows_a_full_address():
    """There is no address field at all: an `address` sent to us is dropped, and pickup shows only the area."""
    p = Profile.model_validate({"name": "Asha", "products": [{"name": "Thali", "price_inr": 120}], "area": "Baner, Pune",
                                "pickup_available": True, "address": "Flat 4B, 12 Secret Lane, Baner, Pune 411045",
                                "instagram": "@asha.kitchen", "niche": "food"})
    assert not hasattr(p, "address")
    html = render_site(p, shop="asha")
    assert "Secret Lane" not in html and "411045" not in html
    assert "Pickup in Baner, Pune" in html and "exact pickup address is shared on WhatsApp" in html
    assert 'href="https://www.instagram.com/asha.kitchen/"' in html and 'class="theme-kitchen"' in html
