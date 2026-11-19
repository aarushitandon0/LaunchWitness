"""S21 STEP 5: eight demo shops (every look has at least one) and the landing page's strip that links to them.
Kept apart from the S21 item tests so these commits can be merged on their own."""

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, func, select

from app.models import AuditEvent, Business, Order
from app.sites import demo, motifs, themes

ROOT = Path(__file__).resolve().parents[2]
NAMES = list(demo.DEMOS)


def raw(name: str) -> dict:
    return json.loads((demo.FIXTURES / f"{demo.DEMOS[name]}.json").read_text(encoding="utf-8"))


def test_every_look_has_a_demo_and_every_demo_its_own_motif():
    assert 6 <= len(NAMES) <= 8
    looks = {themes.resolve(demo.demo_shop(n))[0].key for n in NAMES}
    assert looks == set(themes.THEME_KEYS)
    sigs = [motifs.signature(themes.resolve(demo.demo_shop(n))[0].key, demo.demo_shop(n).name, demo.demo_shop(n).motif,
                             demo.demo_shop(n).art)[0] for n in NAMES]
    assert len(set(sigs)) == len(sigs), sigs
    for n, (motif, art) in demo.DEMO_SIGNATURES.items():  # explicit keys are real keys of that demo's own look
        theme = demo.DEMO_LOOKS[n][0]
        assert motifs.clean_motif(theme, motif) == motif and motifs.clean_arrangement(art) == art


@pytest.mark.parametrize("name", NAMES)
def test_every_demo_renders_labelled_noindex_with_no_contact_or_upi(client, name):
    r = client.get(f"/demo/{name}")
    assert r.status_code == 200, name
    html = r.text
    assert "Demo shop: orders here are not real" in html and r.headers["x-robots-tag"] == "noindex"
    assert f'action="/demo/{name}/order"' in html and 'action="/order"' not in html and "Report this shop" not in html
    assert "upi://" not in html and 'id="pay"' not in html and "wa.me" not in html and 'href="tel:' not in html
    assert "instagram.com" not in html and "Kind words" not in html
    sample = raw(name)
    shown = re.sub(r'placeholder="[^"]*"', "", html)  # the form's own example number is not the sample's phone
    for key in ("upi_id", "phone", "whatsapp", "instagram"):
        value = str(sample.get(key) or "").strip()
        if value:
            assert value not in shown, (name, key)
    assert "<meta name=\"lw-shop\"" not in html  # a demo is never mistaken for a launched shop by the checker
    assert client.get(f"/demo/{name}/privacy").status_code == 200


@pytest.mark.parametrize("name", NAMES)
def test_a_demo_order_places_nothing(client, engine, mailer, name):
    before = len(getattr(mailer, "sent", []))
    form = {"customer_name": "Asha", "customer_phone": "98765 43210", "note": "Two of the first item please",
            "fulfilment": "pickup", "wanted_date": "2099-01-01"}
    r = client.post(f"/demo/{name}/order", data=form)
    assert r.status_code in (200, 422), r.text
    assert "Demo shop" in r.text or "This is a demo" in r.text
    with Session(engine) as s:
        for table in (Order, Business, AuditEvent):
            assert s.exec(select(func.count()).select_from(table)).one() == 0
    assert len(getattr(mailer, "sent", [])) == before


def test_demo_never_on_a_shop_host(client, settings):
    for name in NAMES:
        assert client.get(f"/demo/{name}", headers={"host": f"anything.{settings.app_domain}"}).status_code == 404


# ---------- the landing strip ----------

STRIP = ROOT / "frontend" / "src" / "landing" / "demoShops.ts"


def strip_entries() -> list[dict]:
    text = STRIP.read_text(encoding="utf-8")
    return [{"slug": m[0], "name": m[1], "look": m[2], "thumb": m[3]}
            for m in re.findall(r'\{ slug: "([a-z]+)", name: "([^"]+)", look: "([^"]+)", thumb: "([^"]+)" \}', text)]


def test_the_strip_lists_every_demo_with_its_real_name_look_and_a_small_thumbnail():
    entries = strip_entries()
    assert [e["slug"] for e in entries] == NAMES
    for e in entries:
        shop = demo.demo_shop(e["slug"])
        assert e["name"] == shop.name.replace("—", "-")
        assert e["look"] == re.split(r" & |, ", themes.resolve(shop)[0].label)[0]
        thumb = ROOT / "frontend" / "public" / e["thumb"].lstrip("/")
        assert thumb.exists() and thumb.stat().st_size <= 60 * 1024, e["thumb"]


def test_thumbnails_are_served_on_the_app_host_only(tmp_path, client):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_s11d_chain import launched

    (tmp_path / "demos").mkdir()
    (tmp_path / "demos" / "meera.webp").write_bytes(b"RIFFxxxxWEBP")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    app = create_app(frontend_dist=tmp_path, replay_page=tmp_path / "none.html", run_lifespan=False)
    app.dependency_overrides.update(client.app.dependency_overrides)
    launched(client, "meera")
    with TestClient(app) as c:
        r = c.get("/demos/meera.webp")
        assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content == b"RIFFxxxxWEBP"
        assert "spa" in c.get("/demos/nobody.webp").text  # not a file: the app's page, never a directory listing
        assert c.get("/demos/meera.webp", headers={"host": "meera.localhost"}).status_code == 404  # never on a shop
