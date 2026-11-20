"""S22: custom orders. An item marked "Takes custom requests" makes the order form ask what the customer wants (a note per
item) and allow ONE reference photo, through the S20 screenshot gate. The owner sees both on Orders; the email has the
notes and says where the photo is; the thank-you / status pages show her notes but never the photo."""

import io
import json
import re

import pytest
from PIL import Image
from sqlmodel import Session, select

from app.agents.reader import PROFILE_SCHEMA, SYSTEM, Product
from app.models import AuditEvent, Evidence, Order, Outbox
from app.sites import demo as demo_mod
from app.sites.render import render_site
from app.sites.themes import THEMES
from tests.conftest import sign_in
from tests.test_s9_phase1 import HOST, ORDER
from tests.test_s12_photos import jpeg, png
from tests.test_s20_payments import EVIL, live_shop, order_id

WISH = "Write Happy Birthday Riya, unicorn theme, pink and gold"


def make_custom(client, biz: dict, index: int = 0) -> dict:
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    products = cur["profile"]["products"]
    products[index]["custom"] = True
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], "products": products},
                                                          "subdomain": cur["subdomain"]})
    assert r.status_code == 200, r.text
    assert r.json().get("held") in (None, False) or "pending" not in json.dumps(r.json()).lower()
    return r.json()


def send(client, *, note: str = WISH, photo: bytes | None = None, name="cake.jpg", ctype="image/jpeg", **extra):
    files = {"reference_photo": (name, photo, ctype)} if photo is not None else None
    return client.post("/order", data={**ORDER, "custom_0": note, **extra}, files=files, headers=HOST)


def the_order(engine) -> Order:
    with Session(engine) as s:
        return s.exec(select(Order).where(Order.is_test == False)).one()  # noqa: E712


# ---------- the Reader ----------

def test_reader_custom_flag_is_from_her_words_only_and_defaults_false():
    assert Product(name="Truffle cake", price_inr=650).custom is False
    item = PROFILE_SCHEMA["properties"]["products"]["items"]
    assert "custom" in item["properties"] and "custom" in item["required"]
    assert "custom: true ONLY when her own words" in SYSTEM and "Never guess" in SYSTEM


def test_toggle_on_a_live_shop_is_not_a_word_change(client, engine):
    biz = live_shop(client, engine)
    out = make_custom(client, biz)
    assert out["profile"]["products"][0]["custom"] is True
    with Session(engine) as s:
        from app.models import Business
        b = s.get(Business, biz["id"])
        assert not b.pending_profile_json  # not held for the team: a switch, not words
    assert 'name="custom_0"' in client.get("/", headers=HOST).text


# ---------- the form ----------

def test_form_is_multipart_and_asks_only_for_custom_items(client, engine):
    biz = live_shop(client, engine)
    html = client.get("/", headers=HOST).text
    assert 'id="order-form" enctype="multipart/form-data"' in html
    assert 'name="reference_photo"' not in html and 'name="custom_' not in html  # no custom item: nothing extra
    make_custom(client, biz)
    html = client.get("/", headers=HOST).text
    assert 'name="custom_0"' in html and 'maxlength="500"' in html and "Tell us what you want" in html
    assert html.count('name="reference_photo"') == 1 and 'accept="image/jpeg,image/png,image/webp"' in html
    assert 'name="order_token"' in html and 'name="lw-shop"' in html


def test_order_with_note_and_photo_reaches_the_owner(client, engine):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    r = send(client, photo=jpeg(1600, 1200, gps=True))
    assert r.status_code == 200, r.text
    assert f"Your request: {WISH}" in r.text and "Your reference photo was sent to the shop." in r.text
    assert "reference-photo" not in r.text and "/api/" not in r.text
    o = the_order(engine)
    assert o.ref_photo and o.ref_photo_w == 900
    img = Image.open(io.BytesIO(o.ref_photo))
    assert img.format == "WEBP" and not img.getexif() and "exif" not in img.info and "icc_profile" not in img.info
    assert b"SecretPhone" not in o.ref_photo and b"PhoneMaker" not in o.ref_photo
    items = json.loads(o.items_json)
    assert items[0]["custom_note"] == WISH
    # Orders page data (owner)
    rows = client.get(f"/api/businesses/{biz['id']}/orders").json()
    assert rows[0]["has_ref_photo"] is True and rows[0]["items"][0]["custom_note"] == WISH
    url = f"/api/businesses/{biz['id']}/orders/{o.id}/reference-photo"
    got = client.get(url)
    assert got.status_code == 200 and got.headers["content-type"] == "image/webp"
    assert got.headers["cache-control"] == "private, no-store"
    # the email: notes + where the photo is; no attachment, no link to the photo
    with Session(engine) as s:
        mail = s.exec(select(Outbox).where(Outbox.kind == "order")).one()
    assert "Custom requests:" in mail.body and WISH in mail.body
    assert "Reference photo: open it in Orders" in mail.body and "reference-photo" not in mail.body
    # audited without the note or the picture
    with Session(engine) as s:
        blob = json.dumps([a.model_dump(mode="json") for a in s.exec(select(AuditEvent)).all()]
                          + [e.model_dump(mode="json") for e in s.exec(select(Evidence)).all()], default=str)
    assert WISH not in blob and "with a reference photo" in blob


def test_whatsapp_send_this_order_line_has_the_notes(client, engine):
    biz = live_shop(client, engine, whatsapp="+91 98765 43210")
    make_custom(client, biz)
    r = send(client)
    m = re.search(r'href="(https://wa\.me/[^"]+)"[^>]*>[^<]*<svg[^>]*>.*?</svg>Send this order', r.text, re.S)
    link = m.group(1) if m else next(x for x in re.findall(r'href="(https://wa\.me/[^"]+)"', r.text) if "order" in x)
    from urllib.parse import unquote
    assert "Happy Birthday Riya" in unquote(link)


def test_status_page_shows_her_note_not_the_photo(client, engine):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    r = send(client, photo=png(400, 300, "RGB"))
    tok = re.search(r'href="/order/([A-Za-z0-9_-]{24,64})"', r.text).group(1)
    page = client.get(f"/order/{tok}", headers=HOST).text
    assert WISH in page and "reference-photo" not in page and "Your reference photo was sent" in page


@pytest.mark.parametrize("theme", sorted(THEMES))
def test_hostile_note_is_escaped_in_every_look_and_the_email(client, engine, theme):
    biz = live_shop(client, engine)
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    products = cur["profile"]["products"]
    products[0]["custom"] = True
    client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], "products": products, "theme": theme,
               "accent": THEMES[theme].accents[0].key}, "subdomain": cur["subdomain"]})
    r = send(client, note=EVIL)
    assert r.status_code == 200, r.text
    assert "<script>alert(1)</script>" not in r.text and "<img src=x" not in r.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in r.text
    with Session(engine) as s:
        mail = s.exec(select(Outbox).where(Outbox.kind == "order")).one()
    from app.mail.layout import wrap
    html = wrap("order", mail.subject, mail.body)
    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html and "&lt;script&gt;" in html


def test_note_is_plain_text_and_capped():
    from app.sites.orders import CUSTOM_NOTE_MAX, custom_note
    assert custom_note("a\r\nb\tc\x00d\x7f") == "a b c d"
    assert len(custom_note("x" * 2000)) == CUSTOM_NOTE_MAX == 500


# ---------- refusals ----------

POLYGLOT = b"GIF89a/*<svg onload=alert(1)>*/=1;alert(1)//" + b"\x00" * 64
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"


@pytest.mark.parametrize("data,name,ctype,words", [
    (SVG, "cake.svg", "image/svg+xml", "Please choose a photo"),
    (SVG, "cake.jpg", "image/jpeg", "Please choose a photo"),  # the name lies
    (b"just some text", "notes.txt", "text/plain", "Please choose a photo"),
    (POLYGLOT, "cake.gif", "image/gif", "Please choose a photo"),
    (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 200, "IMG_1.HEIC", "image/heic", "HEIC"),
])
def test_bad_photo_is_refused_and_nothing_is_stored(client, engine, data, name, ctype, words):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    r = send(client, photo=data, name=name, ctype=ctype)
    assert r.status_code == 422 and words in r.text
    assert WISH in r.text  # her words are kept on the form
    with Session(engine) as s:
        assert s.exec(select(Order).where(Order.is_test == False)).first() is None  # noqa: E712


def test_photo_over_5_mb_is_refused(client, engine):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    big = jpeg(400, 300) + b"\x00" * (5 * 1024 * 1024)
    r = send(client, photo=big)
    assert r.status_code in (413, 422) and "under 5 MB" in r.text
    with Session(engine) as s:
        assert s.exec(select(Order).where(Order.is_test == False)).first() is None  # noqa: E712


def test_jpeg_with_a_hidden_payload_is_re_encoded_clean(client, engine):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    r = send(client, photo=jpeg(800, 600, gps=False) + b"<html><script>alert(1)</script></html>")
    assert r.status_code == 200, r.text
    assert b"<script" not in the_order(engine).ref_photo


def test_photo_without_a_custom_item_is_dropped(client, engine):
    live_shop(client, engine)
    r = client.post("/order", data=ORDER, files={"reference_photo": ("c.jpg", jpeg(800, 600), "image/jpeg")}, headers=HOST)
    assert r.status_code == 200
    assert the_order(engine).ref_photo is None


def test_photo_is_private_to_its_owner(client, engine, new_client):
    biz = live_shop(client, engine)
    make_custom(client, biz)
    send(client, photo=png(400, 300, "RGB"))
    oid = order_id(engine)
    url = f"/api/businesses/{biz['id']}/orders/{oid}/reference-photo"
    assert client.get(url).status_code == 200
    assert client.get(url, headers=HOST).status_code == 404  # never from the shop's host
    other = new_client()
    assert other.get(url).status_code in (401, 404)  # logged out
    sign_in(other, "someone-else@example.org")
    assert other.get(url).status_code == 404  # another owner
    assert client.get(url.replace(f"/orders/{oid}/", "/orders/9999/")).status_code == 404


def test_reference_photo_is_purged_30_days_after_the_order_closed(client, engine):
    from datetime import timedelta

    from app import payclaims
    from app.models import utcnow
    biz = live_shop(client, engine)
    make_custom(client, biz)
    send(client, photo=png(400, 300, "RGB"))
    with Session(engine) as s:
        o = s.exec(select(Order).where(Order.is_test == False)).one()  # noqa: E712
        o.status, o.status_changed_at = "done", utcnow() - timedelta(days=31)
        s.add(o)
        s.commit()
        payclaims.purge_old(s)
        s.refresh(o)
        assert o.ref_photo is None and o.ref_photo_w == 0


def test_privacy_page_names_reference_photos(client, engine):
    live_shop(client, engine)
    html = client.get("/privacy", headers=HOST).text
    assert "Reference photos." in html and "deleted 30 days after your order is done or cancelled" in html


# ---------- the checker's test order and the demo ----------

def test_checker_test_order_still_passes_and_never_has_a_photo(client, engine):
    biz = live_shop(client, engine)
    make_custom(client, biz)  # the form now has the note + photo fields; the test order sends neither
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 202
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    checks = rep["run"]["checks"]
    assert rep["run"]["trigger"] == "manual" and checks and all(c["passed"] for c in checks), checks
    assert any(c["check"] == "test_order" for c in checks)
    with Session(engine) as s:
        tests = s.exec(select(Order).where(Order.is_test == True)).all()  # noqa: E712
    assert len(tests) >= 2 and all(o.ref_photo is None for o in tests)


def test_demo_custom_order_shows_fields_and_stores_nothing(client, engine):
    html = client.get("/demo/meera").text
    i = next(i for i, x in enumerate(demo_mod.demo_shop("meera").products) if x.name == "Photo print on cake")
    assert f'name="custom_{i}"' in html and 'name="reference_photo"' in html
    with Session(engine) as s:
        before = (len(s.exec(select(Order)).all()), len(s.exec(select(Outbox)).all()), len(s.exec(select(AuditEvent)).all()))
    r = client.post("/demo/meera/order", data={**ORDER, f"qty_{i}": "1", f"custom_{i}": WISH},
                    files={"reference_photo": ("c.jpg", jpeg(800, 600), "image/jpeg")})
    assert r.status_code == 200, r.text
    assert "This is a demo" in r.text and WISH in r.text and "checked and thrown away" in r.text
    assert "was sent to the shop" not in r.text
    with Session(engine) as s:
        after = (len(s.exec(select(Order)).all()), len(s.exec(select(Outbox)).all()), len(s.exec(select(AuditEvent)).all()))
    assert after == before


def test_demo_custom_items():
    names = {n: [x.name for x in demo_mod.demo_shop(n).products if x.custom] for n in demo_mod.DEMOS}
    assert names["meera"] == ["Photo print on cake", "Theme topper"]
    assert names["imran"] and all("stitch" in x.lower() or "blouse" in x.lower() or "suit" in x.lower() or "kurta" in x.lower()
                                  for x in names["imran"])
    assert names["zari"] and all("stitching" in x.lower() for x in names["zari"])
    assert names["giftgarden"] and all("hamper" in x.lower() for x in names["giftgarden"])
    assert not names["sunita"] and not names["ember"] and not names["greencorner"]


def test_render_without_custom_items_is_unchanged():
    profile = demo_mod.demo_shop("sunita")
    html = render_site(profile, shop="x")
    assert 'id="custom-box"' not in html and 'name="reference_photo"' not in html
