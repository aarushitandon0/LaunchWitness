"""S10.5b "Watch this address": up to 3 per account, read-only daily checks, one email per NEW problem."""

import pytest
from sqlmodel import Session, select

from app import watch
from app.models import AuditEvent, WatchedAddress
from app.routers.proof import get_public_dns, get_public_web
from tests.conftest import sign_in
from tests.test_s9_phase3_proof import FakeDns, FakeWeb

GOOD = {("shop.example.com", "A"): ["93.184.216.34"], ("shop.example.com", "MX"): ["10 mx.example.com."],
        ("shop.example.com", "TXT"): ['"v=spf1 include:x -all"'],
        ("_dmarc.shop.example.com", "TXT"): ['"v=DMARC1; p=none"']}


@pytest.fixture
def world(app):
    dns, web = FakeDns(dict(GOOD)), FakeWeb()
    app.dependency_overrides[get_public_dns] = lambda: dns
    app.dependency_overrides[get_public_web] = lambda: web
    return dns, web


@pytest.fixture
def me(client, world):
    sign_in(client, "watcher@example.org")
    return client


def test_add_list_remove(me, world):
    r = me.post("/api/watches", json={"address": "https://Shop.Example.com/menu"})
    assert r.status_code == 201, r.text
    w = r.json()
    assert w["address"] == "shop.example.com" and w["problems"] == [] and w["last_checked_at"]
    assert world[1].urls == ["https://shop.example.com/"]  # one read-only page load, nothing else
    listed = me.get("/api/watches").json()
    assert listed["limit"] == 3 and [x["address"] for x in listed["watches"]] == ["shop.example.com"]
    assert me.post("/api/watches", json={"address": "shop.example.com"}).status_code == 409  # already watched
    assert me.delete(f"/api/watches/{w['id']}").json() == {"ok": True, "left": 0}
    assert me.get("/api/watches").json()["watches"] == []


def test_limit_of_three(me):
    for i in range(3):
        assert me.post("/api/watches", json={"address": f"site{i}.example.com"}).status_code == 201
    r = me.post("/api/watches", json={"address": "site9.example.com"})
    assert r.status_code == 409 and "up to 3" in r.json()["detail"]


def test_adds_are_rate_limited(me, monkeypatch):
    monkeypatch.setattr(watch, "ADDS_PER_DAY", 2)
    a = me.post("/api/watches", json={"address": "a.example.com"}).json()
    me.delete(f"/api/watches/{a['id']}")
    me.post("/api/watches", json={"address": "b.example.com"})
    assert me.post("/api/watches", json={"address": "c.example.com"}).status_code == 429


def test_only_signed_in_and_only_your_own(me, new_client, world):
    w = me.post("/api/watches", json={"address": "shop.example.com"}).json()
    anon = new_client()
    assert anon.get("/api/watches").status_code == 401
    assert anon.post("/api/watches", json={"address": "x.example.com"}).status_code == 401
    other = new_client()
    sign_in(other, "other@example.org")
    assert other.get("/api/watches").json()["watches"] == []
    assert other.delete(f"/api/watches/{w['id']}").status_code == 404
    assert len(me.get("/api/watches").json()["watches"]) == 1


def test_bad_or_private_addresses_are_refused(me):
    for bad in ("not an address", "localhost", "10.0.0.1", "http://192.168.1.1/", "printer.local"):
        assert me.post("/api/watches", json={"address": bad}).status_code == 422, bad


def test_daily_run_emails_once_per_new_problem(me, world, engine, mailer):
    dns, web = world
    me.post("/api/watches", json={"address": "shop.example.com"})
    assert watch.run_daily(engine, mailer, dns, web) == 0  # all fine: nothing sent
    del dns.records[("_dmarc.shop.example.com", "TXT")]  # a problem appears
    assert watch.run_daily(engine, mailer, dns, web) == 1
    mail = mailer.sent[-1]
    assert mail["to"] == "watcher@example.org" and "shop.example.com" in mail["subject"]
    assert "fake emails" in mail["body"] and "didn't change anything" in mail["body"]
    assert watch.run_daily(engine, mailer, dns, web) == 0  # same problem tomorrow: no repeat
    dns.records[("_dmarc.shop.example.com", "TXT")] = ['"v=DMARC1; p=none"']
    assert watch.run_daily(engine, mailer, dns, web) == 0  # fixed: quiet
    del dns.records[("_dmarc.shop.example.com", "TXT")]
    assert watch.run_daily(engine, mailer, dns, web) == 1  # came back: tell them again
    # only ever emails the watcher, never the watched domain; only reads its home page
    assert all(m["to"] == "watcher@example.org" for m in mailer.sent)
    assert set(web.urls) == {"https://shop.example.com/"}


def test_first_look_is_shown_not_emailed(me, world, engine, mailer):
    dns, web = world
    del dns.records[("_dmarc.shop.example.com", "TXT")]
    w = me.post("/api/watches", json={"address": "shop.example.com"}).json()
    assert w["problems"] == ["email_dmarc"] and mailer.sent == []
    assert watch.run_daily(engine, mailer, dns, web) == 0  # already known from the first look


def test_the_address_is_not_written_to_the_audit_log(me, engine):
    me.post("/api/watches", json={"address": "secret-shop.example.com"})
    with Session(engine) as s:
        assert "secret-shop" not in " ".join(e.model_dump_json() for e in s.exec(select(AuditEvent)).all())


def test_watches_go_with_the_account(me, engine):
    me.post("/api/watches", json={"address": "shop.example.com"})
    r = me.post("/api/account/delete-request")
    token = r.json()["dev_link"].split("token=", 1)[1].split("&", 1)[0]
    assert me.post("/api/account/delete", json={"token": token}).status_code == 200
    with Session(engine) as s:
        assert s.exec(select(WatchedAddress)).all() == []


def test_null_mx_means_no_email():
    """RFC 7505: `0 .` says the domain accepts no email (found on example.com in the S10.5b screenshots)."""
    from app.routers.proof import address_results

    dns = FakeDns({("x.example.com", "MX"): ["0 ."]})
    res = {r["check"]: r for r in address_results("x.example.com", dns, FakeWeb())}
    assert res["email_mx"]["ok"] is False and "doesn't accept email" in res["email_mx"]["plain"]
    dns = FakeDns({("x.example.com", "MX"): ["10 mx.example.com."]})
    assert {r["check"]: r for r in address_results("x.example.com", dns, FakeWeb())}["email_mx"]["ok"] is True
