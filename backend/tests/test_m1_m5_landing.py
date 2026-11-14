"""M1/M5 without real infra: landing-page contact form, /build route, SMTP settings."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import AuditEvent
from tests.conftest import ADMIN_TOKEN

FORM = {"name": "Asha", "email": "asha@example.org", "message": "Can you help my tailoring shop?"}


def test_contact_form_sends_to_app_mailbox(client, mailer, settings, engine):
    r = client.post("/api/contact", json=FORM)
    assert r.status_code == 200 and r.json()["message"].startswith("Thank you!")
    (mail,) = mailer.sent
    assert mail["to"] == settings.smtp_user
    assert "Asha" in mail["subject"] and "asha@example.org" in mail["body"] and FORM["message"] in mail["body"]
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(AuditEvent.action == "contact_form")).one()
        assert ev.result == "sent" and "asha@example.org" not in ev.detail


def test_contact_form_plain_errors(client, mailer):
    r = client.post("/api/contact", json={**FORM, "email": "nope"})
    assert r.status_code == 422 and "email address" in r.json()["detail"]
    r = client.post("/api/contact", json={**FORM, "message": "  "})
    assert r.status_code == 422 and "name and a message" in r.json()["detail"]
    assert mailer.sent == []


def test_contact_honeypot_sends_nothing(client, mailer):
    r = client.post("/api/contact", json={**FORM, "website": "http://spam"})
    assert r.status_code == 200 and mailer.sent == []


def test_contact_mail_failure_is_a_plain_error(client, mailer, engine):
    def boom(**_kw):
        raise OSError("smtp down")

    mailer.send = boom
    r = client.post("/api/contact", json=FORM)
    assert r.status_code == 503 and "couldn't send" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "contact_form")).one().result == "failed"


def test_contact_daily_limit_per_visitor(client, mailer, make_settings):
    from app.config import get_settings

    client.app.dependency_overrides[get_settings] = lambda: make_settings(visitor_contacts_per_day=2)
    assert [client.post("/api/contact", json=FORM).status_code for _ in range(3)] == [200, 200, 429]
    assert client.post("/api/contact", json=FORM, headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 200
    assert len(mailer.sent) == 3


def test_smtp_mailer_logs_in_with_full_address(make_settings, monkeypatch):
    import app.mail.smtp as smtp

    seen = {}

    class FakeSSL:
        def __init__(self, host, port, context=None, timeout=None):
            seen["host"], seen["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, user, password):
            seen["user"], seen["password"] = user, password

        def send_message(self, msg):
            seen["to"] = msg["To"]

    monkeypatch.setattr(smtp.smtplib, "SMTP_SSL", FakeSSL)
    s = make_settings(smtp_user="hello@launchwitness.example", smtp_password="from-env-only")
    smtp.SmtpMailer(s).send(to="hello@launchwitness.example", subject="hi", body="x")
    assert seen == {"host": "smtpout.secureserver.net", "port": 465, "user": "hello@launchwitness.example",
                    "password": "from-env-only", "to": "hello@launchwitness.example"}


def _app(tmp_path, replay):
    from app.main import create_app

    return create_app(frontend_dist=tmp_path, replay_page=replay, run_lifespan=False)


def test_build_page_coming_soon_when_missing(tmp_path, client):
    app = _app(tmp_path, tmp_path / "missing.html")
    app.dependency_overrides.update(client.app.dependency_overrides)
    with TestClient(app) as c:
        r = c.get("/build")
        assert r.status_code == 200 and "coming soon" in r.text


def test_build_page_serves_replay(tmp_path, client):
    page = tmp_path / "build.html"
    page.write_text("<html>replay of sessions</html>")
    app = _app(tmp_path, page)
    app.dependency_overrides.update(client.app.dependency_overrides)
    with TestClient(app) as c:
        for path in ("/build", "/build/"):
            r = c.get(path)
            assert r.status_code == 200 and "replay of sessions" in r.text and r.headers["content-type"].startswith("text/html")


def test_build_is_not_on_seller_sites(tmp_path, client):
    page = tmp_path / "build.html"
    page.write_text("<html>replay</html>")
    client.post("/api/businesses", data={"description": "Meera cakes", "price_list": "Cake 500"}, headers={"X-Admin-Token": ADMIN_TOKEN})
    app = _app(tmp_path, page)
    app.dependency_overrides.update(client.app.dependency_overrides)
    with TestClient(app) as c:
        r = c.get("/build", headers={"host": "meeras-home-cakes.localhost"})
        assert "replay" not in r.text


def test_admin_deletes_practice_business_only(client, engine):
    from app.models import Business
    from tests.test_m3_launch import approve, meera, plan

    ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
    biz = meera(client)
    approve(client, plan(client, biz))
    url = f"/api/admin/practice-businesses/{biz['id']}"
    assert client.delete(url).status_code == 403
    assert client.delete(url, headers=ADMIN).json() == {"ok": True}
    with Session(engine) as s:
        assert s.get(Business, biz["id"]) is None
        assert not s.exec(select(AuditEvent).where(AuditEvent.business_id == biz["id"])).all()
        real = Business(name="Real", practice=False)
        s.add(real)
        s.commit()
        rid = real.id
    r = client.delete(f"/api/admin/practice-businesses/{rid}", headers=ADMIN)
    assert r.status_code == 409
