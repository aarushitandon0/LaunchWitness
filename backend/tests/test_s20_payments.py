"""Session 20 Part A: private UPI and "customer says paid".

The UPI ID, name and QR are not on any public shop page: they appear only after a real order (thank-you page, the
order's own unguessable status page) with the exact amount and the order reference. After paying in her own UPI app the
customer may say so (12-digit UTR + one optional screenshot): a CLAIM the owner sees as "Customer says paid" and checks
in her own UPI app before she marks the order Paid. Nothing here ever says "paid" or "verified" on its own.
"""

import io
import json
import re
from datetime import timedelta

import pytest
from PIL import Image
from sqlmodel import Session, select

from app import payclaims
from app.models import AuditEvent, Evidence, Order, Outbox, PaymentClaim, utcnow
from app.sites import demo as demo_mod
from app.sites.render import render_site
from app.sites.themes import THEMES
from tests.conftest import publish, ready_for_real, sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_s9_phase1 import HOST, ORDER
from tests.test_s12_photos import jpeg, png

UPI = "meera.cakes@okaxis"
UTR = "731908265514"
EVIL = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'


def live_shop(client, engine, **profile) -> dict:
    sign_in(client, "meera@example.org")
    biz = meera(client)
    ready_for_real(client, biz["id"], payment_terms="upfront", **profile)
    assert approve(client, plan(client, biz))["status"] == "done"
    publish(engine, biz["id"])
    return client.get(f"/api/businesses/{biz['id']}").json()


def place(client, **extra) -> tuple[str, str]:
    """(thank-you html, status token)"""
    r = client.post("/order", data={**ORDER, **extra}, headers=HOST)
    assert r.status_code == 200, r.text
    m = re.search(r'href="/order/([A-Za-z0-9_-]{24,64})"', r.text)
    assert m, "the thank-you page links to the order's own page"
    return r.text, m.group(1)


def claim(client, token, utr=UTR, shot: bytes | None = None, host=HOST):
    files = {"screenshot": ("pay.png", shot, "image/png")} if shot else None
    return client.post(f"/order/{token}/paid", data={"utr": utr}, files=files, headers=host, follow_redirects=False)


def order_id(engine) -> int:
    with Session(engine) as s:
        return s.exec(select(Order).where(Order.is_test == False)).first().id  # noqa: E712


# ---------- the shop page keeps UPI private ----------

def test_public_shop_pages_never_carry_the_upi_in_any_theme(client, engine):
    biz = live_shop(client, engine)
    for key, theme in THEMES.items():
        cur = client.get(f"/api/businesses/{biz['id']}").json()
        r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], "theme": key,
                       "accent": theme.accents[0].key}, "subdomain": cur["subdomain"]})
        assert r.status_code == 200, r.text
        for path in ("/", "/privacy"):
            html = client.get(path, headers=HOST).text
            assert f"theme-{key}" in html or path == "/privacy"
            low = html.lower()
            assert UPI not in html and "upi://" not in low and "UPI payment QR" not in html
            assert "Your UPI app should show" not in html and 'id="pay"' not in html and "Meera Joshi" not in html
        home = client.get("/", headers=HOST).text
        assert "How to pay" in home and "never on this page" in home  # it says HOW payment works, with no ID


def test_demo_shops_show_no_upi_and_say_when_it_appears():
    for name in ("meera", "imran", "sunita"):
        html = render_site(demo_mod.demo_profile(name), demo=True, base=f"/demo/{name}")
        assert "upi://" not in html and "UPI payment QR" not in html and 'id="pay"' not in html
    html = render_site(demo_mod.demo_profile("meera"), demo=True, base="/demo/meera")
    assert "you'll see the UPI details after ordering" in html


def test_owner_preview_has_no_upi_either_but_her_golive_test_still_works(client, engine):
    biz = live_shop(client, engine)
    prev = client.get(f"/api/businesses/{biz['id']}/preview").text
    assert UPI not in prev and "upi://" not in prev.lower()
    gl = client.get(f"/api/businesses/{biz['id']}/golive").json()
    assert gl["ready"]
    t = gl["upi_test"]  # the owner-only go-live screen still gets the Rs 1 link + QR (not a public page)
    assert t["uri"].startswith("upi://pay?pa=" + UPI) and "am=1.00" in t["uri"] and "<svg" in t["qr_svg"]
    assert client.get(f"/api/businesses/{biz['id']}/golive", headers=HOST).status_code in (401, 403, 404)


# ---------- after a real order ----------

def test_thank_you_and_status_page_show_the_upi_with_the_exact_amount(client, engine):
    live_shop(client, engine)
    html, tok = place(client)
    with Session(engine) as s:
        o = s.exec(select(Order).where(Order.is_test == False)).first()  # noqa: E712
        ref, now = o.ref, o.pay_now_inr
    assert now > 0
    flat = html.replace("&amp;", "&")
    assert f"upi://pay?pa={UPI}" in flat and f"am={now}.00" in flat and f"Order%20{ref}" in flat
    assert "UPI payment QR code" in html and 'id="claim"' in html and f"/order/{tok}/paid" in html
    page = client.get(f"/order/{tok}", headers=HOST)
    assert page.status_code == 200 and f"am={now}.00" in page.text.replace("&amp;", "&")
    assert page.headers["cache-control"] == "no-store" and "noindex" in page.headers["x-robots-tag"]
    assert "script-src 'none'" in page.headers["content-security-policy"] or "sha256-" in page.headers["content-security-policy"]
    assert client.get("/order/" + "x" * 30, headers=HOST).status_code == 404
    assert "Thank you" not in client.get(f"/order/{tok}").text  # the app host has no such page (it answers with the app shell)


def test_live_contact_rule_still_applies_after_ordering(client, engine):
    biz = live_shop(client, engine)
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    client.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], "upi_id": "someone.else@ybl",
               "upi_display_name": "Someone Else"}, "subdomain": cur["subdomain"]})
    html, tok = place(client)
    for h in (html, client.get(f"/order/{tok}", headers=HOST).text):
        assert "someone.else@ybl" not in h and "Someone Else" not in h and f"pa={UPI}" in h.replace("&amp;", "&")


def test_pay_on_delivery_can_still_pay_by_upi_for_the_whole_amount(client, engine):
    live_shop(client, engine)
    cur = client.get("/api/businesses").json()[0]
    prof = client.get(f"/api/businesses/{cur['id']}").json()["profile"]
    client.put(f"/api/businesses/{cur['id']}", json={"profile": {**prof, "payment_terms": "on_delivery"},
                                                       "subdomain": client.get(f"/api/businesses/{cur['id']}").json()["subdomain"]})
    html, _ = place(client)
    assert "Prefer to pay by UPI" in html and "upi://pay" in html.replace("&amp;", "&")


def test_test_orders_never_show_upi_or_the_form(client, engine):
    from app.sites.orders import order_view

    live_shop(client, engine)
    o = Order(business_id=1, customer_name="T", customer_phone="1", ref="LW-TESTTEST", is_test=True, total_inr=500,
              payment_terms="upfront", pay_now_inr=500)
    v = order_view(o)
    assert v["status_url"] == "" and v["is_test"]
    p = demo_mod.demo_profile("meera").model_copy(update={"upi_id": UPI, "upi_display_name": "X", "payment_terms": "upfront"})
    html = render_site(p, page="thanks", order={**v, "customer_name": "T", "items": [], "total_inr": 500})
    assert "upi://" not in html and 'id="claim"' not in html and "/paid" not in html


# ---------- UTR ----------

@pytest.mark.parametrize("text", [UTR, "7319 0826 5514", " 7319 0826 5514 ", "7319-0826-5514", "7319\t0826 5514"])
def test_utr_good(text):
    assert payclaims.parse_utr(text) == UTR


@pytest.mark.parametrize("text", ["", "12345678901", "1234567890123", "40215678901a", "UTR731908265514", "abcdefghijkl",
                                  "7319 0826 55 14 3", "４０２１５６７８９０１２".replace("４", "x"), EVIL, "٤٠٢١٥٦٧٨٩٠١٢"])
def test_utr_bad(text):
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.parse_utr(text)


def test_a_bad_utr_stores_nothing_and_says_why(client, engine):
    live_shop(client, engine)
    _, tok = place(client)
    r = claim(client, tok, utr="1234")
    assert r.status_code == 422 and "12-digit" in r.text and 'id="claim"' in r.text
    with Session(engine) as s:
        assert s.exec(select(PaymentClaim)).first() is None


# ---------- the claim ----------

def test_claim_is_stored_emailed_once_and_replaced_on_a_second_submit(client, engine, mailer):
    live_shop(client, engine)
    html, tok = place(client)
    r = claim(client, tok, shot=png(400, 300, "RGB"))
    assert r.status_code == 303 and r.headers["location"].startswith(f"/order/{tok}")
    page = client.get(f"/order/{tok}", headers=HOST).text
    assert "You told the shop you paid" in page and "ending 5514" in page and "it is not marked paid" in page
    assert UTR not in page and "7319 0826 5514" not in page  # only the last 4 come back to the customer
    with Session(engine) as s:
        c = s.exec(select(PaymentClaim)).one()
        assert c.utr == UTR and c.screenshot[:4] == b"RIFF" and c.submits == 1
        mails = [m for m in s.exec(select(Outbox)).all() if m.kind == "payment_claim"]
        assert len(mails) == 1 and mails[0].business_id and mails[0].order_id is None
        assert mails[0].body == ""  # emptied once sent: no UTR kept in the outbox
    sent = [m for m in mailer.sent if "says they paid" in m["subject"]] if hasattr(mailer, "sent") else []
    assert sent and "Asha says they paid" in sent[0]["subject"] and "UTR 7319 0826 5514" in sent[0]["body"]
    assert "Check your UPI app" in sent[0]["body"] and "mark the order Paid" in sent[0]["body"]
    # second submit replaces the first, no second email, audited as a replacement
    assert claim(client, tok, utr="111122223333").status_code == 303
    with Session(engine) as s:
        c = s.exec(select(PaymentClaim)).one()
        assert c.utr == "111122223333" and c.screenshot is None and c.submits == 2
        assert len([m for m in s.exec(select(Outbox)).all() if m.kind == "payment_claim"]) == 1
        details = [a.detail for a in s.exec(select(AuditEvent).where(AuditEvent.action == "payment_claim")).all()]
        assert details == ["customer says paid, with a screenshot", "replaced an earlier claim"]


def test_claim_rate_limit_per_order(client, engine):
    live_shop(client, engine)
    _, tok = place(client)
    codes = [claim(client, tok).status_code for _ in range(payclaims.SUBMITS_PER_ORDER + 2)]
    assert codes[: payclaims.SUBMITS_PER_ORDER] == [303] * payclaims.SUBMITS_PER_ORDER and codes[-1] == 429


def test_claim_on_another_shops_or_unknown_token_is_404_and_the_app_host_has_no_form(client, engine):
    live_shop(client, engine)
    _, tok = place(client)
    assert claim(client, "A" * 30).status_code == 404
    assert client.post(f"/order/{tok}/paid", data={"utr": UTR}, follow_redirects=False).status_code == 404  # app host


def test_hostile_text_is_escaped_in_the_claim_pages(client, engine):
    live_shop(client, engine)
    html, tok = place(client, customer_name=EVIL[:60])
    page = client.get(f"/order/{tok}", headers=HOST).text
    for h in (html, page):
        assert "<script>alert(1)" not in h and "<img src=x" not in h
    r = claim(client, tok, utr=EVIL)
    assert "<script>alert(1)" not in r.text and "<img src=x" not in r.text


# ---------- screenshot pipeline ----------

def test_screenshot_is_reencoded_without_exif_or_gps():
    raw = jpeg(1600, 1200)
    assert b"SecretPhone" in raw and b"GPS" in raw or b"Exif" in raw
    data, w, h = payclaims.process_screenshot(raw)
    assert data[:4] == b"RIFF" and data[8:12] == b"WEBP" and w == payclaims.SHOT_WIDTH
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP" and not img.getexif() and "exif" not in img.info
    for secret in (b"SecretPhone", b"PhoneMaker", b"secret note", b"Exif"):
        assert secret not in data


def test_screenshot_refusals():
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.process_screenshot(b"x" * (payclaims.MAX_SHOT_BYTES + 1))
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.process_screenshot(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>")
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.process_screenshot(b"GIF89a" + b"\0" * 50)  # a GIF is not allowed, whatever its name says
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.process_screenshot(b"%PDF-1.4 " + b"0" * 100)
    big = io.BytesIO()
    Image.new("L", (9000, 5000), 1).save(big, "PNG")  # 45 million pixels: over the cap, refused without being decoded
    with pytest.raises(payclaims.ClaimRefused):
        payclaims.process_screenshot(big.getvalue())


def test_fake_type_upload_is_refused_over_http_and_nothing_is_stored(client, engine):
    live_shop(client, engine)
    _, tok = place(client)
    r = client.post(f"/order/{tok}/paid", data={"utr": UTR}, headers=HOST, follow_redirects=False,
                    files={"screenshot": ("pay.png", b"<script>alert(1)</script>", "image/png")})
    assert r.status_code == 422 and "JPEG, PNG or WebP" in r.text.replace("photo", "photo")
    with Session(engine) as s:
        assert s.exec(select(PaymentClaim)).first() is None


# ---------- the owner's side ----------

def test_owner_sees_says_paid_never_paid_and_marks_it_herself(client, engine):
    biz = live_shop(client, engine)
    _, tok = place(client)
    claim(client, tok, shot=png(400, 300, "RGB"))
    o = client.get(f"/api/businesses/{biz['id']}/orders").json()[0]
    pc = o["payment_claim"]
    assert pc["says"] == "Customer says paid · UTR 7319 0826 5514" and pc["has_screenshot"]
    assert o["status"] == "new" and "paid" not in o["payment_label"].lower().replace("waiting for full payment", "")
    shot = client.get(f"/api/businesses/{biz['id']}/orders/{o['id']}/payment-screenshot")
    assert shot.status_code == 200 and shot.headers["content-type"] == "image/webp"
    assert "no-store" in shot.headers["cache-control"] and "public" not in shot.headers["cache-control"]
    assert client.post(f"/api/businesses/{biz['id']}/orders/{o['id']}/status", json={"status": "confirmed"}).status_code == 200
    r = client.post(f"/api/businesses/{biz['id']}/orders/{o['id']}/status", json={"status": "paid"})
    assert r.status_code == 200 and r.json()["status"] == "paid"
    assert "paid" in client.get(f"/order/{tok}", headers=HOST).text.lower()


def test_screenshot_is_private_to_its_owner(client, engine, new_client):
    biz = live_shop(client, engine)
    _, tok = place(client)
    claim(client, tok, shot=png(400, 300, "RGB"))
    oid = order_id(engine)
    url = f"/api/businesses/{biz['id']}/orders/{oid}/payment-screenshot"
    assert client.get(url).status_code == 200
    assert client.get(url, headers=HOST).status_code == 404  # from the shop's own host: never
    other = new_client()
    assert other.get(url).status_code in (401, 404)  # logged out
    sign_in(other, "someone-else@example.org")
    assert other.get(url).status_code == 404  # another owner
    assert client.get(f"/photos/{tok}", headers=HOST).status_code == 404
    assert client.get(url.replace(str(oid), "9999")).status_code == 404


def test_utr_and_screenshot_are_never_in_audit_evidence_or_the_report(client, engine):
    biz = live_shop(client, engine)
    _, tok = place(client)
    claim(client, tok, shot=png(400, 300, "RGB"))
    with Session(engine) as s:
        blob = json.dumps([a.model_dump(mode="json") for a in s.exec(select(AuditEvent)).all()]
                          + [e.model_dump(mode="json") for e in s.exec(select(Evidence)).all()], default=str)
    assert UTR not in blob and "7319 0826 5514" not in blob and "731908265514" not in blob
    rep = client.get(f"/api/businesses/{biz['id']}/report")
    if rep.status_code == 200:
        assert UTR not in rep.text and "5514" not in rep.text
    assert UTR not in client.get("/", headers=HOST).text and UTR not in client.get("/privacy", headers=HOST).text


def test_says_paid_is_not_rendered_as_paid_in_the_email_or_pages(client, engine, mailer):
    live_shop(client, engine)
    html, tok = place(client)
    claim(client, tok)
    page = client.get(f"/order/{tok}", headers=HOST).text
    assert "marked paid" in page and "verified" not in page.lower()
    text = re.sub(r"<[^>]+>", " ", page)
    assert not re.search(r"\b(Paid|verified)\b", text.replace("not marked paid", "").replace("marks your order paid", ""))


# ---------- deletion and the 30-day purge ----------

def test_claims_go_with_the_shop_and_30_days_after_close(client, engine):
    biz = live_shop(client, engine)
    _, tok = place(client)
    claim(client, tok, shot=png(400, 300, "RGB"))
    oid = order_id(engine)
    with Session(engine) as s:
        assert payclaims.purge_old(s) == 0  # an open order keeps its claim
    client.post(f"/api/businesses/{biz['id']}/orders/{oid}/status", json={"status": "cancelled"})
    with Session(engine) as s:
        assert payclaims.purge_old(s) == 0  # closed today: kept 30 days
        assert payclaims.purge_old(s, now=utcnow() + timedelta(days=29)) == 0
        assert payclaims.purge_old(s, now=utcnow() + timedelta(days=31)) == 1
        assert s.exec(select(PaymentClaim)).first() is None
    # and deleting the shop removes a claim that is still there
    _, tok2 = place(client)
    claim(client, tok2)
    with Session(engine) as s:
        assert s.exec(select(PaymentClaim)).first() is not None
    assert client.delete(f"/api/businesses/{biz['id']}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(PaymentClaim)).first() is None


def test_privacy_text_names_the_utr_and_the_30_days(client, engine):
    live_shop(client, engine)
    p = client.get("/privacy", headers=HOST).text
    assert "12-digit UPI reference" in p and "30 days" in p and "only after you place an order" in p
