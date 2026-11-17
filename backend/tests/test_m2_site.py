"""M2 acceptance: Reader -> profile -> editable -> seller site by Host -> order email."""

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.models import AuditEvent, Business, Order
from app.sites.render import format_inr, group_products, upi_uri, whatsapp_link
from tests.conftest import pickup, publish_client

SELLERS = Path(__file__).parent / "fixtures" / "sellers"
MEERA = "meera.localhost"


def sample(name="meera_cakes") -> dict:
    return json.loads((SELLERS / f"{name}.json").read_text(encoding="utf-8"))


def create(client, name="meera_cakes", **files) -> dict:
    s = sample(name)
    r = client.post("/api/businesses", data={"description": s["description"], "price_list": s["price_list"]}, files=files or None)
    assert r.status_code == 201, r.text
    return r.json()


def save(client, biz: dict, subdomain="meera", **changes) -> dict:
    profile = {**biz["profile"], **changes}
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": profile, "subdomain": subdomain})
    assert r.status_code == 200, r.text
    publish_client(client, biz["id"])  # these tests are about the PUBLIC shop: live, not practice
    return r.json()


@pytest.fixture
def meera(client) -> dict:
    biz = create(client)
    return save(client, biz, whatsapp="98765 43210", upi_id="meera.cakes@okaxis", phone="98765 43210")


# ---------- AC1: Meera's input -> profile; editing a price updates the site ----------

def test_meera_input_produces_profile(client, claude):
    biz = create(client)
    assert claude.calls == ["reader_meera_cakes"]
    assert biz["profile"]["name"] == "Meera's Eggless Bakes"
    assert biz["subdomain"] == "meeras-eggless-bakes"
    assert biz["site_url"] == "http://meeras-eggless-bakes.localhost/"
    assert len(biz["profile"]["products"]) >= 7


def test_editing_a_price_updates_rendered_site(client):
    biz = create(client)
    save(client, biz)
    assert "₹650" in client.get("/", headers={"host": MEERA}).text
    products = [dict(p) for p in biz["profile"]["products"]]
    products[0]["price_inr"] = 725
    save(client, biz, products=products)
    html = client.get("/", headers={"host": MEERA}).text
    assert "₹725" in html and "₹650" not in html
    assert client.get(f"/api/businesses/{biz['id']}").json()["profile"]["products"][0]["price_inr"] == 725


def test_profile_edit_is_validated(client):
    biz = create(client)
    bad = {**biz["profile"], "products": []}
    assert client.put(f"/api/businesses/{biz['id']}", json={"profile": bad, "subdomain": "meera"}).status_code == 422
    neg = {**biz["profile"], "products": [{"name": "x", "price_inr": -5}]}
    assert client.put(f"/api/businesses/{biz['id']}", json={"profile": neg, "subdomain": "meera"}).status_code == 422


@pytest.mark.parametrize("sub,code", [("www", 422), ("bad_name", 422), ("a.b", 422), ("Meera", 200)])
def test_subdomain_rules(client, sub, code):
    biz = create(client)
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": biz["profile"], "subdomain": sub})
    assert r.status_code == code


def test_subdomain_must_be_unique(client):
    a, b = create(client), create(client, "tailor")
    save(client, a, "meera")
    r = client.put(f"/api/businesses/{b['id']}", json={"profile": b["profile"], "subdomain": "meera"})
    assert r.status_code == 409


def test_default_subdomain_avoids_clash(client):
    assert create(client)["subdomain"] == "meeras-eggless-bakes"
    assert create(client)["subdomain"] == "meeras-eggless-bakes-2"


def test_photo_upload_goes_to_reader(client, claude):
    r = client.post("/api/businesses", data={"description": "Menu in the photo"},
                    files={"photo": ("menu.png", b"\x89PNG fake", "image/png")})
    assert r.status_code == 201
    r = client.post("/api/businesses", data={"description": "x"}, files={"photo": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 422 and "JPG" in r.json()["detail"]


def test_empty_description_is_a_plain_error(client):
    r = client.post("/api/businesses", data={"description": " "})
    assert r.status_code == 422
    assert "tell us a little about your business" in r.json()["detail"]


def test_samples_endpoint(client):
    ids = [s["id"] for s in client.get("/api/samples").json()]
    assert ids == ["meera_cakes", "tailor", "tiffin_service"]


# ---------- AC2: meera.localhost shows her site ----------

def test_meera_localhost_shows_her_site(client, meera):
    r = client.get("/", headers={"host": MEERA})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    html = r.text
    assert "<h1>Fresh eggless cakes and cupcakes, baked to order in Baner</h1>" in html  # S14: the Reader's headline line
    assert "Meera&#39;s Eggless Bakes</span>" in html and 'class="eyebrow">Meera&#39;s Eggless Bakes' in html
    for section in ('id="menu"', 'id="about"', 'id="info"', 'id="pay"', 'id="order"', 'href="/privacy"'):
        assert section in html
    assert "10am to 8pm, closed on Tuesdays" in html
    assert "https://wa.me/919876543210?text=Hi%20Meera%27s%20Eggless%20Bakes" in html
    assert 'aria-label="UPI payment QR code"' in html and "<svg" in html
    assert "upi://pay?pa=meera.cakes@okaxis&amp;pn=Meera%27s%20Eggless%20Bakes&amp;cu=INR" in html


def test_host_with_port_and_case_works(client, meera):
    assert "Meera" in client.get("/", headers={"host": "Meera.LocalHost:8000"}).text


def test_menu_grouped_by_category_in_order(client, meera):
    html = client.get("/", headers={"host": MEERA}).text
    cats = ["Cakes", "Cupcakes &amp; brownies", "Extras"]
    head = '<h3 class="cat-h">'
    positions = [html.index(f"{head}{c} ") for c in cats]
    assert positions == sorted(positions)
    assert html.index("Rasmalai") < html.index(f"{head}Cupcakes")
    assert html.index(f"{head}Extras") < html.index("Photo print on cake")  # add-ons are shown as extras


def test_privacy_page(client, meera):
    r = client.get("/privacy", headers={"host": MEERA})
    assert r.status_code == 200 and "<h1>Privacy</h1>" in r.text and "does not take payments" in r.text


def test_app_host_still_serves_app(client, meera):
    assert "Meera&#39;s Eggless Bakes</h1>" not in client.get("/", headers={"host": "localhost"}).text
    assert client.get("/api/health", headers={"host": "localhost"}).json()["ok"] is True


def test_unknown_subdomain_is_404_not_the_app(client, meera):
    r = client.get("/", headers={"host": "nobody.localhost"})
    assert r.status_code == 404 and "isn't set up yet" in r.text
    assert client.get("/nope", headers={"host": MEERA}).status_code == 404


def test_custom_domain_in_db_routes_to_seller(client, engine, meera):
    with Session(engine) as s:
        b = s.get(Business, meera["id"])
        b.domain = "meerascakes.in"
        s.add(b)
        s.commit()
    assert "Meera" in client.get("/", headers={"host": "meerascakes.in"}).text


def test_no_whatsapp_or_upi_hides_those_parts(client):
    biz = create(client)
    save(client, biz)
    html = client.get("/", headers={"host": MEERA}).text
    assert "wa.me" not in html and 'id="pay"' not in html


def test_template_escapes_seller_text(client):
    biz = create(client)
    save(client, biz, about="<script>alert(1)</script>")
    html = client.get("/", headers={"host": MEERA}).text
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


# ---------- AC3: order form -> stored order -> email ----------

def order_form(**extra):
    return {"qty_0": "1", "qty_5": "2", "customer_name": "Asha Rao", "customer_phone": "+91 99887 76655",
            "note": "Happy birthday Riya on top", **pickup(), **extra}


def test_order_is_stored_and_emailed(client, engine, mailer, meera, settings):
    r = client.post("/order", data=order_form(), headers={"host": MEERA})
    assert r.status_code == 200 and "Thank you, Asha Rao!" in r.text
    assert "₹1,490" in r.text  # 650 + 2*420

    assert len(mailer.sent) == 1
    mail = mailer.sent[0]
    assert mail["to"] == settings.smtp_user
    assert mail["subject"].startswith("New order for Meera's Eggless Bakes from Asha Rao")
    assert "1 x Chocolate truffle cake 1/2 kg" in mail["body"]
    assert "2 x Cupcakes box of 6 @ ₹420 = ₹840" in mail["body"]
    assert "+91 99887 76655" in mail["body"] and "Happy birthday Riya" in mail["body"]

    with Session(engine) as s:
        order = s.exec(select(Order)).one()
        assert (order.business_id, order.total_inr, order.email_status) == (meera["id"], 1490, "sent")
        assert order.email_message_id == mail["message_id"]
        actions = {e.action: e.result for e in s.exec(select(AuditEvent)).all()}
        assert actions["order_placed"] == "ok" and actions["order_email"] == "sent"  # S13: the outbox's words

    assert client.get(f"/api/businesses/{meera['id']}/orders").json()[0]["total_inr"] == 1490


def test_note_only_order_is_ok(client, mailer, meera):
    form = {"customer_name": "Ravi", "customer_phone": "9876543210", "note": "2 kg custom cake for Sunday", **pickup()}
    assert client.post("/order", data=form, headers={"host": MEERA}).status_code == 200
    assert "(no items chosen; see note)" in mailer.sent[0]["body"]


@pytest.mark.parametrize("bad", [
    {"customer_name": ""},
    {"customer_phone": "123"},
    {"qty_0": "-1"},
    {"qty_0": "500"},
    {"qty_0": "0", "qty_5": "0", "note": ""},
    {"website": "http://spam"},
])
def test_invalid_orders_are_rejected_and_not_emailed(client, engine, mailer, meera, bad):
    r = client.post("/order", data=order_form(**bad), headers={"host": MEERA})
    assert r.status_code == 422 and 'class="error"' in r.text
    assert mailer.sent == []
    with Session(engine) as s:
        assert s.exec(select(Order)).all() == []


def test_invalid_order_keeps_what_customer_typed(client, meera):
    r = client.post("/order", data=order_form(customer_phone="12"), headers={"host": MEERA})
    assert 'value="Asha Rao"' in r.text and re.search(r'name="qty_5" type="number"[^>]*value="2"', r.text)


def test_order_saved_even_if_email_fails(client, engine, mailer, meera):
    def boom(**_):
        raise OSError("smtp down")

    mailer.send = boom
    assert client.post("/order", data=order_form(), headers={"host": MEERA}).status_code == 200
    with Session(engine) as s:
        # S13: kept and retried by the outbox (dead letters are "failed": test_s13_outbox.py)
        assert s.exec(select(Order)).one().email_status == "retrying"
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "order_email")).one().result == "failed"


def test_order_endpoint_only_on_seller_hosts(client, mailer, meera):
    assert client.post("/order", data=order_form(), headers={"host": "localhost"}).status_code == 404
    assert mailer.sent == []


# ---------- helpers ----------

@pytest.mark.parametrize("n,out", [(0, "₹0"), (80, "₹80"), (1200, "₹1,200"), (150000, "₹1,50,000"), (12345678, "₹1,23,45,678")])
def test_format_inr(n, out):
    assert format_inr(n) == out


def test_whatsapp_and_upi_helpers():
    from app.agents.reader import Profile

    p = Profile(name="A & B", products=[{"name": "x", "price_inr": 1}], whatsapp="+91 98765-43210", upi_id="ab@upi")
    assert whatsapp_link(p).startswith("https://wa.me/919876543210?text=Hi%20A%20%26%20B")
    assert upi_uri(p) == "upi://pay?pa=ab@upi&pn=A%20%26%20B&cu=INR"
    assert whatsapp_link(p.model_copy(update={"whatsapp": "", "phone": "12345"})) is None
    assert [c.name for c in group_products(p.products)] == ["Menu"]
