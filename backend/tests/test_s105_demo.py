"""S10.5 §1: demo shops at /demo/<name>: sample profiles, no database row, no real orders."""

from sqlmodel import Session, func, select

from app.models import AuditEvent, Business, Order


def test_demo_shop_is_served_logged_out_and_labelled(client):
    for name in ("meera", "imran", "sunita"):
        r = client.get(f"/demo/{name}")
        assert r.status_code == 200, name
        assert "Demo shop: orders here are not real" in r.text
        assert r.headers["x-robots-tag"] == "noindex"
        # the shop's own links stay inside the demo, never the app's pages
        assert f'action="/demo/{name}/order"' in r.text
        assert f'href="/demo/{name}/privacy"' in r.text
        assert 'href="/privacy"' not in r.text and 'action="/order"' not in r.text
        assert "Report this shop" not in r.text
    assert client.get("/demo/meera/privacy").status_code == 200


def test_unknown_demo_is_404(client):
    assert client.get("/demo/nobody").status_code == 404
    assert client.get("/demo/reader_meera_cakes").status_code == 404  # only the fixed names


def test_demo_order_places_nothing(client, engine, mailer):
    before = len(getattr(mailer, "sent", []))
    r = client.post("/demo/meera/order", data={"customer_name": "Asha", "customer_phone": "98765 43210", "qty_0": "1"})
    assert r.status_code == 200
    assert "This is a demo" in r.text and "no order was placed" in r.text
    with Session(engine) as s:
        assert s.exec(select(func.count()).select_from(Order)).one() == 0
        assert s.exec(select(func.count()).select_from(Business)).one() == 0
        assert s.exec(select(func.count()).select_from(AuditEvent)).one() == 0
    assert len(getattr(mailer, "sent", [])) == before


def test_demo_order_form_errors_like_a_real_shop(client):
    r = client.post("/demo/meera/order", data={"customer_name": "", "customer_phone": "1"})
    assert r.status_code == 422 and "Please add your name" in r.text and "Demo shop" in r.text


def test_demo_never_on_a_shop_host(client, settings):
    host = f"anything.{settings.app_domain}"
    assert client.get("/demo/meera", headers={"host": host}).status_code == 404


def test_demo_has_no_contact_details_even_if_a_sample_gains_them():
    from app.sites.demo import DEMOS, demo_profile

    for name in DEMOS:
        p = demo_profile(name)
        assert (p.phone, p.whatsapp, p.upi_id) == ("", "", "")


def test_shop_says_where_to_resume(client):
    """S10.5 §2: My shops resumes a half-finished shop at the right step, from the shop's latest plan."""
    from tests.test_m3_launch import meera, plan

    biz = meera(client)
    assert biz["latest_plan"] is None  # → resume at Review
    p = plan(client, biz)
    listed = {b["id"]: b for b in client.get("/api/businesses").json()}
    assert listed[biz["id"]]["latest_plan"] == {"id": p["id"], "status": "draft", "practice": True}  # → Approve


def test_head_on_pages_is_not_405(client, settings):
    """Uptime monitors send HEAD /: it used to answer 405 (open bug from S10)."""
    assert client.head("/").status_code == 200
    assert client.head("/", headers={"host": f"nobody.{settings.app_domain}"}).status_code == 404
