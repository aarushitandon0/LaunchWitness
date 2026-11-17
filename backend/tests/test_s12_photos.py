"""S12 Part C: product photos. Every rule has a test: content type, size, pixels, re-encoding, EXIF/GPS stripped,
two WebP widths, limits per shop and per item, who may upload, where they're served and with which headers, the
template (lazy, sized, placeholders kept), backups, and deletion with the shop and with the account."""

import io

import pytest
from PIL import Image
from sqlmodel import Session, select

from app import photos
from app.models import Business, Photo
from tests.test_m2_site import MEERA, create, save


def jpeg(w=1600, h=1200, *, gps=True, orientation=None, color=(200, 120, 60)) -> bytes:
    img = Image.new("RGB", (w, h), color)
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # Make
    exif[0x0110] = "SecretPhone 9"  # Model
    if gps:
        exif[0x8825] = {1: "N", 2: (18.0, 31.0, 12.34), 3: "E", 4: (73.0, 51.0, 56.78)}  # GPS IFD: Pune
    if orientation:
        exif[0x0112] = orientation
    out = io.BytesIO()
    img.save(out, "JPEG", exif=exif.tobytes(), quality=90, comment=b"secret note")
    return out.getvalue()


def png(w=800, h=600, mode="RGBA") -> bytes:
    out = io.BytesIO()
    Image.new(mode, (w, h), (10, 200, 10, 128) if mode == "RGBA" else (10, 200, 10)).save(out, "PNG")
    return out.getvalue()


def up(client, biz, data: bytes, item: str = "", name="photo.jpg", ctype="image/jpeg"):
    return client.post(f"/api/businesses/{biz['id']}/photos", files={"file": (name, data, ctype)},
                       data={"item": item} if item else {})


@pytest.fixture
def shop(client) -> dict:
    biz = create(client)
    return save(client, biz)  # live, real, on meera.localhost


# ---------- processing ----------

def test_jpeg_is_reencoded_to_two_webp_widths_with_nothing_left_of_the_original():
    raw = jpeg()
    out = photos.process(raw)
    assert (out["small_w"], out["large_w"]) == (480, 1200) and out["small_h"] == 360 and out["large_h"] == 900
    for key in ("small", "large"):
        data = out[key]
        assert data[:4] == b"RIFF" and data[8:12] == b"WEBP"
        img = Image.open(io.BytesIO(data))
        assert img.format == "WEBP" and not img.getexif() and "exif" not in img.info and "icc_profile" not in img.info
        for secret in (b"SecretPhone", b"PhoneMaker", b"secret note", b"GPS", b"Exif"):
            assert secret not in data


def test_upright_from_exif_orientation_then_the_orientation_is_dropped():
    out = photos.process(jpeg(1600, 1200, orientation=6))  # a phone held upright: stored sideways + "rotate 90"
    assert out["large_w"] < out["large_h"]  # portrait, as the phone showed it
    assert not Image.open(io.BytesIO(out["large"])).getexif()


def test_never_upscaled_and_transparency_goes_on_white():
    out = photos.process(png(300, 200))
    assert (out["small_w"], out["large_w"]) == (300, 300)
    assert Image.open(io.BytesIO(out["small"])).mode == "RGB"


@pytest.mark.parametrize("data,why", [
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "Please choose a photo"),
    (b"<html><body>hi</body></html>", "Please choose a photo"),
    (b"%PDF-1.4 fake", "Please choose a photo"),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 200, "Please choose a photo|couldn't read"),  # a JPEG header and nothing behind it
    (b"", "empty"),
])
def test_type_is_checked_by_content_not_by_name(data, why):
    with pytest.raises(photos.PhotoRefused, match=why):
        photos.process(data)


def test_gif_and_other_formats_are_refused():
    out = io.BytesIO()
    Image.new("RGB", (200, 200)).save(out, "GIF")
    with pytest.raises(photos.PhotoRefused, match="JPEG, PNG or WebP"):
        photos.process(out.getvalue())


def test_size_pixels_and_tiny_images_are_refused(monkeypatch):
    with pytest.raises(photos.PhotoRefused, match="too big"):
        photos.process(b"\x00" * (photos.MAX_UPLOAD_BYTES + 1))
    monkeypatch.setattr(photos, "MAX_PIXELS", 1_000_000)
    with pytest.raises(photos.PhotoRefused, match="too many pixels"):
        photos.process(png(2000, 1000, "RGB"))  # small file, too many pixels: a decompression bomb's shape
    with pytest.raises(photos.PhotoRefused, match="very small"):
        photos.process(png(40, 40, "RGB"))


def test_upload_limit_fits_inside_caddys_body_limit():
    from pathlib import Path

    caddy = (Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile.prod").read_text(encoding="utf-8")
    assert "max_size 8MB" in caddy and photos.MAX_UPLOAD_BYTES < 8 * 1024 * 1024


# ---------- the routes ----------

def test_upload_on_review_then_shown_lazy_and_sized_on_the_live_shop(client, shop):
    r = up(client, shop, jpeg())
    assert r.status_code == 201, r.text
    (p,) = r.json()["shop"]
    item = shop["profile"]["products"][0]["name"]
    r = up(client, shop, png(), item=item, name="cake.png", ctype="image/png")
    assert r.status_code == 201 and r.json()["items"][item]["small"].endswith("-480.webp")
    html = client.get("/", headers={"host": MEERA}).text
    # S14: the first shop photo is the hero image (large, loaded at once); the item photo is a lazy thumbnail
    assert f'src="{p["large"]}"' in html and 'fetchpriority="high"' in html
    assert html.count('loading="lazy"') == 1 and 'width="1200" height="900"' in html
    assert 'class="item has-photo"' in html


def test_placeholders_stay_when_there_are_no_photos(client, shop):
    html = client.get("/", headers={"host": MEERA}).text
    assert '<ul class="gallery' not in html and 'class="item-photo"' not in html and 'class="mono"' in html


def test_served_from_the_shop_host_with_long_cache_headers(client, shop):
    p = up(client, shop, jpeg()).json()["shop"][0]
    r = client.get(p["large"], headers={"host": MEERA})
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert Image.open(io.BytesIO(r.content)).size == (1200, 900)
    assert client.get(p["small"]).status_code == 200  # the app's own host (the owner's preview of a draft)
    assert client.get(p["small"].replace("-480", "-481"), headers={"host": MEERA}).status_code == 404
    assert client.get("/photos/" + "0" * 32 + "-480.webp", headers={"host": MEERA}).status_code == 404
    assert client.get(p["small"], headers={"host": "nobody.localhost"}).status_code == 404


def test_another_shops_host_does_not_serve_her_photo(client, new_client, shop):
    p = up(client, shop, jpeg()).json()["shop"][0]
    other = new_client()
    biz2 = create(other, "tiffin_service")
    save(other, biz2, subdomain="sunita")
    assert other.get(p["small"], headers={"host": "sunita.localhost"}).status_code == 404


def test_a_paused_shop_serves_no_photos(client, engine, shop):
    p = up(client, shop, jpeg()).json()["shop"][0]
    with Session(engine) as s:
        b = s.get(Business, shop["id"])
        b.paused = True
        s.add(b)
        s.commit()
    assert client.get(p["small"], headers={"host": MEERA}).status_code == 404


def test_six_shop_photos_and_one_per_item(client, shop, engine):
    for _ in range(photos.MAX_SHOP_PHOTOS):
        assert up(client, shop, jpeg(400, 300, gps=False)).status_code == 201
    r = up(client, shop, jpeg(400, 300))
    assert r.status_code == 422 and "6 shop photos" in r.json()["detail"]
    item = shop["profile"]["products"][1]["name"]
    first = up(client, shop, jpeg(400, 300), item=item).json()["items"][item]["id"]
    second = up(client, shop, jpeg(500, 300), item=item).json()["items"][item]["id"]
    assert first != second
    with Session(engine) as s:
        assert len(s.exec(select(Photo).where(Photo.item == item)).all()) == 1  # replaced, not added
    assert up(client, shop, jpeg(400, 300), item="Not on the list").status_code == 422


def test_refused_upload_says_why_and_stores_nothing(client, shop, engine):
    r = up(client, shop, b"<script>alert(1)</script>", name="cake.jpg")  # the name lies
    assert r.status_code == 422 and "photo" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(Photo)).all() == []


def test_only_the_owner_uploads_lists_or_removes(client, new_client, shop):
    pid = up(client, shop, jpeg()).json()["shop"][0]["id"]
    stranger = new_client()
    create(stranger, "tiffin_service")  # a workspace of her own, so she isn't simply "not signed in"
    assert up(stranger, shop, jpeg()).status_code == 404
    assert stranger.get(f"/api/businesses/{shop['id']}/photos").status_code == 404
    assert stranger.delete(f"/api/businesses/{shop['id']}/photos/{pid}").status_code == 404
    assert client.delete(f"/api/businesses/{shop['id']}/photos/{pid}").json()["shop"] == []


def test_alt_text_is_escaped(client, shop):
    r = client.post(f"/api/businesses/{shop['id']}/photos", files={"file": ("a.jpg", jpeg(), "image/jpeg")},
                    data={"alt": '"><script>alert(1)</script>'})
    assert r.status_code == 201
    html = client.get("/", headers={"host": MEERA}).text
    assert "<script>alert(1)" not in html and "&#34;&gt;&lt;script&gt;" in html


def test_photos_go_with_the_shop(client, shop, engine):
    up(client, shop, jpeg())
    assert client.delete(f"/api/businesses/{shop['id']}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Photo)).all() == []


def test_photos_go_with_the_account(make_settings, engine, mailer, claude):
    from tests.test_s9_phase2_access import AppClient, approved_shop, real_approve, real_world

    app, _server = real_world(make_settings, engine, mailer, claude)
    with AppClient(app) as c:
        biz = approved_shop(c, engine)
        assert real_approve(c, biz).status_code == 200
        assert up(c, biz, jpeg()).status_code == 201
        token = c.post("/api/account/delete-request").json()["dev_link"].split("token=", 1)[1]
        assert c.post("/api/account/delete", json={"token": token}).json() == {"ok": True}
    with Session(engine) as s:
        assert s.exec(select(Photo)).all() == []


def test_photos_are_in_the_backup(client, shop, engine, tmp_path):
    import sqlite3

    from app import backup

    up(client, shop, jpeg())
    live = tmp_path / "live.db"  # the test database is in memory: copy it to a file, then back it up as the VPS does
    raw = engine.raw_connection()
    try:
        dst = sqlite3.connect(live)
        raw.driver_connection.backup(dst)
        dst.close()
    finally:
        raw.close()
    counts = backup.create(str(live), str(tmp_path / "b.db"))
    assert counts["photo"] == 1
    con = sqlite3.connect(tmp_path / "b.db")
    assert len(con.execute("SELECT large FROM photo").fetchone()[0]) > 1000  # the image itself, not a pointer
    con.close()


def test_a_renamed_item_keeps_its_photo_and_a_removed_item_loses_it(client, shop, engine):
    products = [dict(p) for p in shop["profile"]["products"]]
    up(client, shop, jpeg(400, 300), item=products[0]["name"])
    up(client, shop, jpeg(400, 300), item=products[1]["name"])
    gone = products[1]["name"]
    products[0]["name"] = "Chocolate truffle cake (1 kg)"
    put = lambda ps: client.put(f"/api/businesses/{shop['id']}",  # noqa: E731
                                json={"profile": {**shop["profile"], "products": ps}, "subdomain": "meera"})
    assert put(products).status_code == 200  # a rename: same length
    with Session(engine) as s:
        assert sorted(p.item for p in s.exec(select(Photo)).all()) == sorted(["Chocolate truffle cake (1 kg)", gone])
    assert put([p for p in products if p["name"] != gone]).status_code == 200  # removed
    with Session(engine) as s:
        assert [p.item for p in s.exec(select(Photo)).all()] == ["Chocolate truffle cake (1 kg)"]
