"""S17: a photo with each item on the Describe step.

The seller types an item and adds its photo in the same row. The shop is made first (the Reader may tidy the item's
name: "Chocolate truffle cake 1/2 kg" -> "Chocolate Truffle Cake (½ kg)"), then each photo is uploaded with what she
TYPED as `item_hint`; the server finds the item the Reader made from it. No match: a plain refusal, nothing stored
(the Review page has the item's own photo button).
"""

from sqlmodel import Session, select

from app import photos
from app.models import Photo
from tests.test_m2_site import create, save
from tests.test_s12_photos import jpeg

MENU = ["Chocolate Truffle Cake (½ kg)", "Chocolate Truffle Cake (1 kg)", "Pineapple Cake (½ kg)",
        "Red Velvet with Cream Cheese (½ kg)", "Assorted Cupcakes, box of 6", "Brownies (box of 9)",
        "Photo print on cake"]


def test_match_finds_the_item_the_reader_made_from_her_words():
    m = photos.match_item
    assert m("Chocolate truffle cake 1/2 kg", MENU) == ["Chocolate Truffle Cake (½ kg)"]
    assert m("chocolate truffle cake 1 kg", MENU) == ["Chocolate Truffle Cake (1 kg)"]
    assert m("Brownies box of 9", MENU) == ["Brownies (box of 9)"]
    assert m("Cupcakes box of 6 (assorted)", MENU) == ["Assorted Cupcakes, box of 6"]
    assert m("Pineapple cake", MENU) == ["Pineapple Cake (½ kg)"]
    assert m("Pineapple cake 1/2 kg", ["Pineapple cake", "Red velvet cake"]) == ["Pineapple cake"]  # S21B: size moved out
    assert m("  RED VELVET  ", MENU) == ["Red Velvet with Cream Cheese (½ kg)"]


def test_one_photo_for_every_size_when_she_named_no_size():
    assert photos.match_item("Chocolate truffle cake", MENU) == ["Chocolate Truffle Cake (½ kg)",
                                                                  "Chocolate Truffle Cake (1 kg)"]


def test_no_match_rather_than_a_wrong_one():
    m = photos.match_item
    assert m("Paneer tikka", MENU) == []
    assert m("", MENU) == []
    assert m("Cake", []) == []
    assert m("Samosa", ["Samosa (2 pcs)", "Kachori (2 pcs)"]) == ["Samosa (2 pcs)"]
    assert m("Kachori", ["Samosa (2 pcs)", "Kachori (2 pcs)"]) == ["Kachori (2 pcs)"]


def up_hint(client, biz, data: bytes, hint: str):
    return client.post(f"/api/businesses/{biz['id']}/photos", files={"file": ("cake.jpg", data, "image/jpeg")},
                       data={"item_hint": hint})


def test_upload_with_what_she_typed_lands_on_the_readers_item(client, engine):
    shop = save(client, create(client))
    names = [p["name"] for p in shop["profile"]["products"]]
    target = names[0]
    r = up_hint(client, shop, jpeg(400, 300), target.lower() + "  ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["matched"] == [target] and target in body["items"]
    assert body["shop"] == []  # an item photo, never a shop photo
    with Session(engine) as s:
        assert len(s.exec(select(Photo).where(Photo.item == target)).all()) == 1


def test_upload_with_a_hint_that_matches_nothing_stores_nothing(client, engine):
    shop = save(client, create(client))
    r = up_hint(client, shop, jpeg(400, 300), "Something she never sells xyz")
    assert r.status_code == 422
    assert "next page" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(Photo)).all() == []


def test_exact_item_still_wins_and_old_callers_still_work(client):
    shop = save(client, create(client))
    item = shop["profile"]["products"][1]["name"]
    r = client.post(f"/api/businesses/{shop['id']}/photos", files={"file": ("c.jpg", jpeg(400, 300), "image/jpeg")},
                    data={"item": item, "item_hint": "anything else"})
    assert r.status_code == 201 and r.json()["matched"] == [item]
    shop_photo = client.post(f"/api/businesses/{shop['id']}/photos",
                             files={"file": ("c.jpg", jpeg(400, 300), "image/jpeg")})
    assert shop_photo.status_code == 201 and len(shop_photo.json()["shop"]) == 1


def test_only_the_owner_can_attach_by_hint(client, new_client, engine):
    shop = save(client, create(client))
    other = new_client()
    r = up_hint(other, shop, jpeg(400, 300), shop["profile"]["products"][0]["name"])
    assert r.status_code in (401, 403, 404)
    with Session(engine) as s:
        assert s.exec(select(Photo)).all() == []
