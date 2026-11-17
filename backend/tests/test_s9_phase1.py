"""Session 9F, Phase 1: make the current claims true (audit B1-B9, S2, S5-S8, app-zone guard)."""

import json
from datetime import timedelta

import httpx
import pytest
from sqlmodel import Session, select

from app.agents.checker import checks_for, run_check
from app.agents.launch_check import AlreadyChecking, start_run
from app.agents.playbook import fixes_for
from app.godaddy.client import AppZoneWriteRefused, FakeGoDaddyClient, GoDaddyClient
from app.mail.imap import FakeInboxReader
from app.mail.providers import PROVIDERS
from app.models import AuditEvent, Business, CheckRun, Order, Plan, utcnow
from app.routers.internal import is_allowed_tls_domain
from app.sites.orders import order_recipients
from app.startup import reconcile
from tests.conftest import pickup, publish, sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_m4_repair import ctx_for

HOST = {"host": "meera.localhost"}
ORDER = {"qty_0": "1", "customer_name": "Asha Rao", "customer_phone": "98765 43210", **pickup()}


def launched_shop(client, engine, owner_email: str | None = None) -> tuple[dict, dict]:
    """A sandbox-launched, public (live, not practice) shop at meera.localhost."""
    if owner_email:
        sign_in(client, owner_email)
    biz = meera(client)
    p = approve(client, plan(client, biz))
    assert p["status"] == "done", p["steps"]
    publish(engine, biz["id"])
    return biz, p


# ---------- B1: orders go to the right person, same function + recipients as the test order ----------

def test_b1_real_and_test_orders_share_recipients(client, engine, integ, settings):
    biz, _p = launched_shop(client, engine, owner_email="meera@example.org")
    test_mail = next(m for m in integ.mailer.sent if "[TEST]" in m["subject"])
    r = client.post("/order", data=ORDER, headers=HOST)
    assert r.status_code == 200, r.text
    real_mail = integ.mailer.sent[-1]
    assert "[TEST]" not in real_mail["subject"]
    assert real_mail["to"] == test_mail["to"] == "meera@example.org"  # her verified sign-in address, nobody else
    with Session(engine) as s:
        assert order_recipients(s, settings, s.get(Business, biz["id"])) == ["meera@example.org"]


def test_b1_guest_practice_orders_stay_in_the_app_mailbox_and_team_shops_get_both(client, new_client, engine, settings):
    biz = meera(client)  # guest: no owner yet
    with Session(engine) as s:
        assert order_recipients(s, settings, s.get(Business, biz["id"])) == [settings.smtp_user]
    from app.models import Membership, User

    with Session(engine) as s:  # a shop the team runs itself
        admin = User(email="team@example.org", status="approved", role="admin")
        s.add(admin)
        s.commit()
        s.add(Membership(user_id=admin.id, business_id=biz["id"]))
        s.commit()
        assert order_recipients(s, settings, s.get(Business, biz["id"])) == ["team@example.org", settings.smtp_user]


# ---------- B2: public-shop gate ----------

def test_b2_draft_and_practice_shops_are_not_public(client, engine, settings):
    biz = meera(client)  # draft, practice
    assert client.get("/", headers=HOST).status_code == 404
    assert client.post("/order", data=ORDER, headers=HOST).status_code == 404
    with Session(engine) as s:
        assert not is_allowed_tls_domain("meera.localhost", settings, s)
    approve(client, plan(client, biz))  # practice launch: "live" but still practice
    assert client.get("/", headers=HOST).status_code == 404
    with Session(engine) as s:
        assert not is_allowed_tls_domain("meera.localhost", settings, s)
    publish(engine, biz["id"])
    assert client.get("/", headers=HOST).status_code == 200
    with Session(engine) as s:
        assert is_allowed_tls_domain("meera.localhost", settings, s)


def test_b2_paused_shop_shows_neutral_page_and_gets_no_certificate(client, engine, settings):
    biz, _ = launched_shop(client, engine)
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.paused = True
        s.add(b)
        s.commit()
        assert not is_allowed_tls_domain("meera.localhost", settings, s)
    r = client.get("/", headers=HOST)
    assert r.status_code == 503 and "This shop is paused" in r.text and "Meera" not in r.text
    assert client.post("/order", data=ORDER, headers=HOST).status_code == 503


def test_b2_owner_preview_needs_the_owner(client):
    biz = meera(client)
    r = client.get(f"/api/businesses/{biz['id']}/preview")
    assert r.status_code == 200 and "Eggless" in r.text and "Preview" in r.text
    client.cookies.clear()
    assert client.get(f"/api/businesses/{biz['id']}/preview").status_code == 401


# ---------- B3 + S2 + S5: mailer per business, rate limits, idempotency ----------

def test_b3_practice_shop_never_uses_the_real_mailer(client, engine, integ):
    """A practice order (only possible from the launch check now) goes to the practice world's mailer."""
    from app.mail.smtp import get_mailer

    class Exploding:
        def send(self, **kw):
            raise AssertionError("real mailer used for a shop order")

    client.app.dependency_overrides[get_mailer] = lambda: Exploding()
    launched_shop(client, engine)
    assert client.post("/order", data=ORDER, headers=HOST).status_code == 200
    assert integ.mailer.sent[-1]["subject"].startswith("New order")


def test_s2_orders_are_rate_limited_per_visitor_and_per_shop(client, engine, make_settings):
    from app.config import get_settings

    launched_shop(client, engine)
    client.app.dependency_overrides[get_settings] = lambda: make_settings(orders_per_visitor_per_hour=2,
                                                                          orders_per_shop_per_day=3)
    for _ in range(2):
        assert client.post("/order", data=ORDER, headers=HOST).status_code == 200
    r = client.post("/order", data=ORDER, headers=HOST)
    assert r.status_code == 429 and "few minutes" in r.text
    other = {**HOST, "x-forwarded-for": "203.0.113.9"}
    assert client.post("/order", data=ORDER, headers=other).status_code == 200  # shop total now 3 (test order excluded)
    r = client.post("/order", data=ORDER, headers={**HOST, "x-forwarded-for": "203.0.113.10"})
    assert r.status_code == 429
    with Session(engine) as s:
        assert len(s.exec(select(Order).where(Order.is_test == False)).all()) == 3  # noqa: E712


def test_s5_double_submit_makes_one_order(client, engine, integ):
    launched_shop(client, engine)
    page = client.get("/", headers=HOST).text
    assert 'name="order_token"' in page
    token = page.split('name="order_token" value="', 1)[1].split('"', 1)[0]
    assert len(token) >= 16
    before = len(integ.mailer.sent)
    for _ in range(2):
        r = client.post("/order", data={**ORDER, "order_token": token}, headers=HOST)
        assert r.status_code == 200 and "Thank you" in r.text
    with Session(engine) as s:
        assert len(s.exec(select(Order).where(Order.is_test == False)).all()) == 1  # noqa: E712
    assert len(integ.mailer.sent) == before + 1


# ---------- B4: mail values per provider; never overwrite another provider's working records ----------

def test_b4_provider_table_default_is_secureserver(settings):
    assert settings.mail_provider == "secureserver"
    assert {h for _p, h in PROVIDERS["secureserver"].mx} == {"smtp.secureserver.net", "mailstore1.secureserver.net"}
    assert "include:secureserver.net" in PROVIDERS["secureserver"].spf
    assert "titan" in PROVIDERS


def test_b4_sandbox_checks_mail_settings_read_only(client, engine, integ, settings):
    _biz, p = launched_shop(client, engine)
    ctx = ctx_for(engine, settings, integ, p["id"])
    assert checks_for(ctx) == ["site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc",
                               "test_order"]
    writes = len(integ.godaddy.writes())
    for name in ("email_mx", "email_spf", "email_dkim", "email_dmarc"):
        out = run_check(ctx, name)
        assert out.passed, (name, out.detail)
        assert fixes_for(name, "sandbox") == set()  # nothing may write mail records on the app's own domain
    assert len(integ.godaddy.writes()) == writes


def test_b4_working_mail_of_another_provider_is_never_overwritten(client, engine, integ, settings):
    domain = "meerascakes.in"
    integ.godaddy.owned.add(domain)
    other = [{"type": "MX", "name": "@", "data": "aspmx.l.google.com", "priority": 1, "ttl": 3600}]
    integ.godaddy.zones[domain] = list(other)
    p = approve(client, plan(client, meera(client), "full", domain))
    assert p["status"] == "failed"
    failed = next(s for s in p["steps"] if s["status"] == "failed")
    assert "already" in failed["message"]
    assert [r for r in integ.godaddy.zones[domain] if r["type"] == "MX"] == other


# ---------- B5: the test order carries a nonce; an old email never passes ----------

def test_b5_test_order_has_a_nonce_and_old_mail_does_not_pass(client, engine, integ, settings):
    _biz, p = launched_shop(client, engine)
    with Session(engine) as s:
        first = s.exec(select(Order).where(Order.is_test)).first()
        next_id = s.exec(select(Order).order_by(Order.id.desc())).first().id + 1
    assert len(first.nonce) >= 16
    mail = next(m for m in integ.mailer.sent if "[TEST]" in m["subject"])
    assert first.nonce in mail["subject"] and first.nonce in mail["body"]
    # An old email whose subject matches the NEXT order id (as after a database reset) must not count.
    integ.inbox.deliver(sender="x", to=settings.smtp_user, subject=f"[TEST] New order (#{next_id})", body="old",
                        at=utcnow() - timedelta(days=2))
    integ.mailer.drop = True  # the new test order's email never arrives
    ctx = ctx_for(engine, settings, integ, p["id"])
    out = run_check(ctx, "test_order")
    assert not out.passed


def test_b5_inbox_search_ignores_messages_before_since():
    inbox = FakeInboxReader()
    inbox.deliver(sender="a", to="b", subject="code abc", body="", at=utcnow() - timedelta(hours=1))
    assert inbox.find(subject_contains="abc", since=utcnow() - timedelta(minutes=5)) == []
    assert len(inbox.find(subject_contains="abc", since=utcnow() - timedelta(hours=2))) == 1


# ---------- B6: startup reconciler ----------

def test_b6_reconciler_fails_orphaned_plans_and_check_runs(client, engine):
    biz, p = launched_shop(client, engine)
    with Session(engine) as s:
        orphan = Plan(business_id=biz["id"], mode="sandbox", zone="localhost", site_host="meera.localhost",
                      status="running", steps_json=json.dumps([{"id": "a", "kind": "backup_dns", "title": "t",
                                                               "detail": "", "status": "running", "message": "",
                                                               "started_at": None, "finished_at": None}]))
        s.add(orphan)
        s.add(CheckRun(business_id=biz["id"], plan_id=p["id"], trigger="manual"))
        s.commit()
        orphan_id = orphan.id
    assert reconcile(engine) == {"plans": 1, "check_runs": 1, "outbox": 0}
    with Session(engine) as s:
        pl = s.get(Plan, orphan_id)
        step = json.loads(pl.steps_json)[0]
        assert pl.status == "failed" and step["status"] == "failed" and "Resume" in step["message"]
        assert "restarted" in step["message"]
        assert s.exec(select(CheckRun).where(CheckRun.status == "running")).all() == []
        stuck = s.exec(select(CheckRun).order_by(CheckRun.id.desc())).first()
        assert stuck.status == "done" and stuck.passed is False
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "reconcile")).all()
    assert reconcile(engine) == {"plans": 0, "check_runs": 0, "outbox": 0}
    assert client.post(f"/api/plans/{orphan_id}/resume").status_code == 200


# ---------- B7: practice results are labelled ----------

def test_b7_practice_report_is_labelled(client):
    biz = meera(client)
    approve(client, plan(client, biz))
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    assert rep["practice"] is True and rep["ready"] is True
    assert rep["headline"] == "Practice run: passed (pretend GoDaddy)"
    assert "ready for customers" not in json.dumps(rep)


def test_b7_real_shop_on_real_services_says_ready(client, engine, integ):
    biz, _p = launched_shop(client, engine)
    integ.fake = False  # stands for the real GoDaddy/DNS/mail services
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    assert rep["practice"] is False and rep["headline"] == "Your business is ready for customers"


# ---------- B8: launch steps are not a check ----------

def test_b8_launch_steps_are_shown_apart_from_checks(client):
    biz = meera(client)
    approve(client, plan(client, biz))
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    assert "launch_clean" not in [c["check"] for c in rep["run"]["checks"]]
    assert rep["launch"]["status"] == "done"
    assert [s["status"] for s in rep["launch"]["steps"]] == ["done"] * 5


# ---------- B9: Doctor fixes depend on the launch mode ----------

def test_b9_fixes_depend_on_launch_mode():
    assert fixes_for("test_order", "sandbox") == set()
    assert fixes_for("site_points", "sandbox") == {"repoint_site"}
    assert fixes_for("https", "sandbox") == {"retry_certificate", "repoint_site"}
    assert fixes_for("email_dmarc", "full") == {"readd_email_auth"}
    assert fixes_for("launch_clean", "full") == set()


def test_b9_sandbox_test_order_failure_makes_no_doctor_call(client, engine, integ, settings, claude):
    from app.agents.launch_check import run_checks

    _biz, p = launched_shop(client, engine)
    integ.mailer.drop = True
    calls = len(claude.calls)
    summary = run_checks(engine, settings, integ, claude, p["id"], trigger="manual")
    assert [f.check for f in summary.failed] == ["test_order"]
    assert len(claude.calls) == calls


# ---------- S6: one running-check guard for monitoring and "Run checks now" ----------

def test_s6_one_check_run_at_a_time(client, engine, integ, settings, claude):
    from app.monitor.scheduler import Monitor

    biz, p = launched_shop(client, engine)
    with Session(engine) as s:
        start_run(s, biz["id"], p["id"], "manual")
        with pytest.raises(AlreadyChecking):
            start_run(s, biz["id"], p["id"], "monitor_quick")
        runs = len(s.exec(select(CheckRun)).all())
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 409
    assert Monitor(engine, settings, lambda b: integ, claude).check_business(biz["id"], "quick") == []
    with Session(engine) as s:
        assert len(s.exec(select(CheckRun)).all()) == runs


# ---------- S7: only an ACTIVE domain counts as owned ----------

@pytest.mark.parametrize("status,owned", [("ACTIVE", True), ("PENDING_DNS_ACTIVE", False), ("", False),
                                          ("CANCELLED", False), ("HELD_REGISTRAR", False)])
def test_s7_is_owned_needs_active(settings, status, owned):
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"domain": "x.in", "status": status}))
    assert GoDaddyClient(settings, transport=transport).is_owned("x.in") is owned


# ---------- S8: customer phone numbers stay out of the audit log ----------

def test_s8_audit_never_holds_customer_phone(client, engine):
    launched_shop(client, engine)
    assert client.post("/order", data={**ORDER, "note": "call me"}, headers=HOST).status_code == 200
    with Session(engine) as s:
        for e in s.exec(select(AuditEvent)).all():
            digits = "".join(ch for ch in e.detail + e.target if ch.isdigit())
            assert "9876543210" not in digits


# ---------- App-zone guard: only A records for shop names ----------

BAD_WRITES = [("A", "@"), ("A", "*"), ("A", "www"), ("A", "mail"), ("A", "_dmarc"), ("A", "xn--80ak6aa92e"),
              ("A", "a.b"), ("MX", "@"), ("MX", "meera"), ("TXT", "@"), ("TXT", "_dmarc"), ("TXT", "meera"),
              ("CNAME", "meera"), ("CNAME", "www"), ("NS", "@"), ("AAAA", "meera")]


@pytest.mark.parametrize("rtype,name", BAD_WRITES)
def test_app_zone_guard_refuses_everything_but_shop_a_records(make_settings, rtype, name):
    settings = make_settings(app_domain="launchwitness.com", godaddy_env="prod")
    sent = []
    real = GoDaddyClient(settings, transport=httpx.MockTransport(lambda req: sent.append(req) or httpx.Response(200)))
    fake = FakeGoDaddyClient(app_domain="launchwitness.com")
    for gd in (real, fake):
        with pytest.raises(AppZoneWriteRefused):
            gd.set_records("launchwitness.com", rtype, name, [{"data": "1.2.3.4"}])
        with pytest.raises(AppZoneWriteRefused):
            gd.delete_records("LaunchWitness.com", rtype, name)
    assert sent == [] and fake.writes() == []


def test_app_zone_guard_allows_a_shop_a_record(make_settings):
    settings = make_settings(app_domain="launchwitness.com", godaddy_env="prod")
    sent = []
    real = GoDaddyClient(settings, transport=httpx.MockTransport(lambda req: sent.append(req) or httpx.Response(200)))
    real.set_records("launchwitness.com", "A", "meeras-bakes", [{"data": "1.2.3.4", "ttl": 600}])
    assert [(r.method, r.url.path) for r in sent] == [("PUT", "/v1/domains/launchwitness.com/records/A/meeras-bakes")]
    # another domain (a seller's own, practice only) is not the app zone: the per-business guard covers it
    real.set_records("meerascakes.in", "MX", "@", [{"data": "mx.example", "priority": 0}])
    assert len(sent) == 2


@pytest.mark.parametrize("slug", ["www", "admin", "hello", "godaddy", "launchwitness", "_x", "xn--abc", "ab",
                                  "a" * 31, "Meera", "me_era", "-meera", "meera-", "paytm-offers"])
def test_shop_names_follow_the_rules(slug):
    from app.sites.hosts import slug_problem

    assert slug_problem(slug) is not None


def test_good_shop_names_pass():
    from app.sites.hosts import slug_problem

    for slug in ("meera", "meeras-eggless-bakes", "abc", "shop-24"):
        assert slug_problem(slug) is None
