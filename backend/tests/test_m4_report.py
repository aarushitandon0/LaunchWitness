"""M4 rest (fakes): owner link, approval card email line, launch report, demo fault,
"Run checks now", practice-only public path, visitor limits, light monitoring."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.integrations import fake_integrations
from app.models import Alert, AuditEvent, Business, CheckRun
from app.monitor.scheduler import Monitor
from tests.conftest import ADMIN_TOKEN, AppClient, set_user, sign_in
from tests.test_m3_launch import SELLERS, approve, meera, plan

DOMAIN = "meerascakes.in"
ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def full_launch(client, integ, price=8.99) -> dict:
    """Practice full launch: approve → stops before buying → 'Pretend I bought it' → done (+ launch checks)."""
    integ.availability.prices = {DOMAIN: price}
    biz = meera(client)
    p = approve(client, plan(client, biz, "full", DOMAIN))
    assert p["status"] == "blocked"
    r = client.post(f"/api/plans/{p['id']}/practice-buy")
    assert r.status_code == 200, r.text
    p = client.get(f"/api/plans/{p['id']}").json()
    assert p["status"] == "done", p["steps"]
    return biz


def report(client, biz) -> dict:
    r = client.get(f"/api/businesses/{biz['id']}/report")
    assert r.status_code == 200, r.text
    return r.json()


def events(engine, **where):
    with Session(engine) as s:
        q = select(AuditEvent)
        for k, v in where.items():
            q = q.where(getattr(AuditEvent, k) == v)
        return s.exec(q.order_by(AuditEvent.id)).all()


# ---------- access (the full matrix is in test_s9_phase2_access.py) ----------

def test_guest_cookie_owns_the_practice_shop_and_nothing_secret_is_returned(client, engine):
    biz = meera(client)
    assert "owner_key" not in biz and "owner_link" not in biz and biz["guest"] and biz["practice"]
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        cookie = client.cookies.get("lw_guest")
        assert cookie and b.guest_hash and cookie not in b.model_dump_json()  # only a hash is stored
    assert all(cookie not in e.detail for e in events(engine))


def test_admin_token_can_open_any_business(client, new_client):
    biz = meera(client)
    cli = new_client()  # a command-line caller: no cookies, only the emergency admin token
    assert cli.get(f"/api/businesses/{biz['id']}").status_code == 401
    assert cli.get(f"/api/businesses/{biz['id']}", headers=ADMIN).status_code == 200
    assert [b["id"] for b in cli.get("/api/admin/businesses", headers=ADMIN).json()] == [biz["id"]]
    assert cli.get("/api/businesses").json() == []  # "my shops" is only ever the caller's own


def test_default_admin_token_never_works(make_settings):
    from app.safety.access import is_admin_token as is_admin
    s = make_settings(admin_token="change-me")
    assert not is_admin(s, "change-me") and not is_admin(make_settings(admin_token="short"), "short")
    assert is_admin(make_settings(), ADMIN_TOKEN) and not is_admin(make_settings(), ADMIN_TOKEN + "x")


def test_public_site_needs_no_key(client, engine):
    from tests.conftest import publish

    publish(engine, meera(client)["id"])
    client.cookies.clear()
    r = client.get("/", headers={"host": "meera.localhost"})
    assert r.status_code == 200 and "Meera" in r.text


def test_orders_and_alerts_go_to_the_sign_in_address(client, engine):
    sign_in(client, "meera@example.org")
    biz = meera(client)
    assert biz["owner_email"] == "meera@example.org" and not biz["guest"]
    assert report(client, biz)["business"]["has_owner_email"] is True


# ---------- approval card ----------

def test_card_shows_email_plan_as_separate_estimate(client, integ, settings):
    integ.availability.prices = {DOMAIN: 8.99}
    biz = meera(client)
    full = plan(client, biz, "full", DOMAIN)
    assert full["total_cost_usd"] == 8.99  # spend guard covers only the domain
    assert full["email_plan_estimate_usd"] == settings.email_plan_estimate_usd == 23.88
    assert plan(client, biz)["email_plan_estimate_usd"] is None


# ---------- AC1: full green run on a sandbox launch ----------

def test_ac1_sandbox_launch_report_all_green_with_times(client, integ):
    biz = meera(client)
    p = approve(client, plan(client, biz))
    assert p["status"] == "done"
    rep = report(client, biz)
    assert rep["ready"] and rep["headline"] == "Practice run: passed (pretend GoDaddy)" and rep["left"] == []
    run = rep["run"]
    assert run["trigger"] == "launch" and run["status"] == "done" and run["passed"]
    assert [c["check"] for c in run["checks"]] == ["site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc", "test_order"]
    for c in run["checks"]:
        assert c["passed"] and c["at"].endswith("Z") and c["title"] and c["plain"]
    assert rep["monitoring"]["cert_days_left"] in (79, 80) and rep["monitoring"]["domain_days_left"] is None
    actions = [e["action"] for e in rep["audit"]]
    assert {"approve_plan", "step_go_live", "check_https", "check_run"} <= set(actions)


def test_report_before_launch_and_after_stop(client, integ):
    biz = meera(client)
    rep = report(client, biz)
    assert not rep["ready"] and rep["headline"] == "Your business isn't launched yet"
    integ.availability.prices = {DOMAIN: 8.99}
    approve(client, plan(client, biz, "full", DOMAIN))  # blocked before buying
    rep = report(client, biz)
    assert rep["headline"] == "Your launch stopped before the end" and "godaddy.com" in rep["left"][0]


# ---------- practice "Pretend I bought it" ----------

def test_practice_buy_then_full_launch_green(client, integ, engine):
    biz = full_launch(client, integ)
    rep = report(client, biz)
    assert rep["ready"], rep["left"]
    assert len(rep["run"]["checks"]) == 7
    assert rep["business"]["site_url"] == "http://meera.localhost/"  # never the pretend (maybe real) domain
    assert not [c for c in integ.godaddy.calls if c[0] == "purchase_domain"]  # nothing "bought", even in the fake
    (ev,) = events(engine, action="practice_buy")
    assert "nothing bought" in ev.detail


def test_practice_buy_refused_outside_practice_mode(client, integ):
    integ.availability.prices = {DOMAIN: 8.99}
    p = approve(client, plan(client, meera(client), "full", DOMAIN))
    integ.fake = False  # as on a real server
    r = client.post(f"/api/plans/{p['id']}/practice-buy")
    assert r.status_code == 409 and "only available in practice mode" in r.json()["detail"]
    assert DOMAIN not in integ.godaddy.owned


def test_practice_buy_only_when_waiting_for_purchase(client):
    p = approve(client, plan(client, meera(client)))
    assert client.post(f"/api/plans/{p['id']}/practice-buy").status_code == 409


# ---------- AC2: demo fault → Doctor → fix → green ----------

def test_ac2_demo_fault_doctor_fixes_and_report_shows_it(client, integ, engine):
    biz = full_launch(client, integ)
    assert report(client, biz)["ready"]
    r = client.put(f"/api/admin/businesses/{biz['id']}/demo-fault", json={"fault": "dmarc"}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["demo_fault"] == "dmarc"
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 202

    rep = report(client, biz)
    assert rep["ready"], rep  # fixed and re-checked green
    run = rep["run"]
    assert run["trigger"] == "manual"
    dmarc = next(c for c in run["checks"] if c["check"] == "email_dmarc")
    assert dmarc["passed"] and dmarc["fixed"] and not dmarc["first_passed"] and dmarc["attempt"] == 1
    (rep_,) = run["repairs"]
    assert rep_["check"] == "email_dmarc" and rep_["fixed"]
    sentence = json.loads((SELLERS.parent / "claude" / "doctor_email_dmarc.json").read_text())["plain_explanation"]
    assert rep_["attempts"][0]["explanation"] == sentence and rep_["attempts"][0]["fix_id"] == "readd_email_auth"
    # all in the audit log, in order
    acts = [(e.actor, e.action, e.result) for e in events(engine, business_id=biz["id"])]
    i = acts.index(("admin", "demo_fault", "ok"))
    tail = acts[i:]
    assert ("checker", "check_email_dmarc", "fail") in tail
    assert ("doctor", "diagnose", "ok") in tail and ("executor", "dns_write", "ok") in tail
    assert ("checker", "check_email_dmarc", "pass") in tail and ("doctor", "repair", "fixed") in tail
    # one-shot: the next run is clean and has no repairs
    client.post(f"/api/businesses/{biz['id']}/checks")
    assert report(client, biz)["run"]["repairs"] == []


def test_demo_fault_mx_is_also_repaired(client, integ):
    biz = full_launch(client, integ)
    client.put(f"/api/admin/businesses/{biz['id']}/demo-fault", json={"fault": "mx"}, headers=ADMIN)
    client.post(f"/api/businesses/{biz['id']}/checks")
    rep = report(client, biz)
    assert rep["ready"] and {r["check"] for r in rep["run"]["repairs"]} >= {"email_mx"}


def test_demo_fault_is_admin_only_and_needs_full_launch(client, new_client, integ):
    biz = meera(client)
    approve(client, plan(client, biz))
    url = f"/api/admin/businesses/{biz['id']}/demo-fault"
    assert client.put(url, json={"fault": "dmarc"}).status_code == 401  # guest: not signed in
    assert client.put(url, json={"fault": "dmarc"}, headers={"X-Admin-Token": "change-me"}).status_code == 401
    seller = new_client()
    sign_in(seller, "someone@example.org")
    assert seller.put(url, json={"fault": "dmarc"}).status_code == 403  # signed in, but not the team
    assert seller.delete(f"/api/admin/practice-businesses/{biz['id']}").status_code == 403
    r = client.put(url, json={"fault": "dmarc"}, headers=ADMIN)
    assert r.status_code == 409 and "own name" in r.json()["detail"]
    assert client.put(url, json={"fault": "spf"}, headers=ADMIN).status_code == 422
    assert report(client, biz)["demo_fault"] is None  # owners don't see the switch
    assert client.get(f"/api/businesses/{biz['id']}/report", headers=ADMIN).json()["demo_fault"] == ""


# ---------- AC4: "Run checks now" ----------

def test_run_checks_now(client, integ):
    biz = meera(client)
    r = client.post(f"/api/businesses/{biz['id']}/checks")
    assert r.status_code == 409 and "isn't launched" in r.json()["detail"]
    approve(client, plan(client, biz))
    integ.http.broken_cert.add("meera.localhost")
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 202
    rep = report(client, biz)
    assert not rep["ready"] and rep["headline"].startswith("Almost there")
    assert rep["left"] == ["Your website's security certificate isn't working yet."]
    https = next(r for r in rep["run"]["repairs"] if r["check"] == "https")
    assert not https["fixed"] and len(https["attempts"]) == 3  # max 3 attempts, then stop and explain
    integ.http.broken_cert.clear()
    client.post(f"/api/businesses/{biz['id']}/checks")
    assert report(client, biz)["ready"]


def test_run_checks_now_refused_while_running(client, engine):
    biz = meera(client)
    p = approve(client, plan(client, biz))
    with Session(engine) as s:
        s.add(CheckRun(business_id=biz["id"], plan_id=p["id"], trigger="manual"))
        s.commit()
    r = client.post(f"/api/businesses/{biz['id']}/checks")
    assert r.status_code == 409 and "already checking" in r.json()["detail"]
    assert report(client, biz)["headline"] == "Checking everything for you…"


# ---------- public path is practice only ----------

def two_worlds_client(make_settings, engine, mailer, claude, **settings_kw):
    from app.config import get_settings
    from app.db import get_session
    from app.integrations import get_integrations, get_practice_integrations
    from app.mail.smtp import get_mailer
    from app.main import create_app
    from app.routers.businesses import get_claude

    settings_kw.setdefault("claude_mode", "live")  # the VPS runs live Claude; the fixture client plays its answers
    settings = make_settings(use_fakes=False, **settings_kw)
    server = fake_integrations(settings)
    server.fake = False  # stands in for the REAL GoDaddy/DNS/mail on the VPS
    practice = fake_integrations(settings)
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides.update({get_settings: lambda: settings, get_session: _session,
                                     get_mailer: lambda: mailer, get_claude: lambda: claude,
                                     get_integrations: lambda: server, get_practice_integrations: lambda: practice})
    return AppClient(app), server, practice


def real_plan(c, biz) -> dict:
    from tests.conftest import ready_for_real

    ready_for_real(c, biz["id"])
    r = c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True})
    assert r.status_code == 201, r.text
    return r.json()


def test_guest_on_real_server_is_always_practice(make_settings, engine, mailer, claude):
    c, server, practice = two_worlds_client(make_settings, engine, mailer, claude)
    with c:
        assert c.get("/api/auth/me").json()["practice_server"] is False
        biz = meera(c)
        assert biz["practice"]
        assert c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True}).status_code == 403
        p = approve(c, plan(c, biz))
        assert p["status"] == "done"
        assert server.godaddy.writes() == [] and server.godaddy.calls == []  # real world untouched
        assert practice.godaddy.writes()
        assert c.get(f"/api/plans/{p['id']}").json()["practice"]
        assert c.get("/", headers={"host": "meera.localhost"}).status_code == 404  # never public


def test_pending_user_practises_and_approved_user_launches_for_real(make_settings, engine, mailer, claude):
    c, server, practice = two_worlds_client(make_settings, engine, mailer, claude)
    with c:
        sign_in(c, "meera@example.org")
        biz = meera(c)
        r = c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True})
        assert r.status_code == 403 and "waiting for approval" in r.json()["detail"]  # pending: practice only
        approve(c, plan(c, biz))  # a practice launch works
        assert practice.godaddy.writes() and not server.godaddy.writes()

        set_user(engine, "meera@example.org", status="approved")
        p = approve(c, real_plan(c, biz))
        assert p["status"] == "done" and p["practice"] is False
        assert server.godaddy.writes() == [("set_records", "localhost", "A", "meera")]
        rep = report(c, biz)
        # her own inbox: the mail server's "accepted" is not delivery, so the last hop waits for her tap
        assert rep["practice"] is False and rep["ready"] is False
        assert rep["headline"] == "Almost ready: tell us the test order reached you"
        assert rep["proof"]["needs_you"] == 1 and rep["proof"]["proven"] == rep["proof"]["total"] - 1
        mail = next(m for m in server.mailer.sent if "TEST, not a real order:" in m["subject"])
        token = mail["body"].split("#/got-it?token=", 1)[1].split()[0]
        assert c.post("/api/proof/confirm", json={"token": token}).json()["ok"] is True
        rep = report(c, biz)
        assert rep["headline"] == "Your business is ready for customers" and rep["proof"]["needs_you"] == 0
        assert rep["business"]["public"] is True
        assert c.get("/", headers={"host": "meera.localhost"}).status_code == 200  # now public
        assert c.get("/internal/tls-ask", params={"domain": "meera.localhost"}).status_code == 200
        # a real shop can't go back to practice, and real launches are on our subdomains only
        assert c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox"}).status_code == 409
        r = c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "full", "domain": DOMAIN, "real": True})
        assert r.status_code == 422 and "comes later" in r.json()["detail"]


def test_practice_results_never_count_for_a_real_shop(make_settings, engine, mailer, claude):
    c, server, practice = two_worlds_client(make_settings, engine, mailer, claude)
    with c:
        sign_in(c, "meera@example.org")
        set_user(engine, "meera@example.org", status="approved")
        biz = meera(c)
        approve(c, plan(c, biz))  # practice launch: green in the pretend world
        assert report(c, biz)["headline"] == "Practice run: passed (pretend GoDaddy)"
        server.dns.hide.add(("meera.localhost", "A"))  # the real launch will stop at "wait for DNS"
        p = approve(c, real_plan(c, biz))
        assert p["status"] == "failed"
        rep = report(c, biz)
        assert rep["ready"] is False and rep["headline"] == "Your launch stopped before the end"
        assert c.get("/", headers={"host": "meera.localhost"}).status_code == 404


def test_practice_domain_never_served_or_certified_on_real_server(make_settings, engine, mailer, claude):
    from app.routers.internal import is_allowed_tls_domain

    c, server, practice = two_worlds_client(make_settings, engine, mailer, claude)
    with c:
        full_launch(c, practice)
        with Session(engine) as s:
            assert s.exec(select(Business)).one().domain == DOMAIN
            assert not is_allowed_tls_domain(DOMAIN, make_settings(use_fakes=False), s)
        assert c.get("/", headers={"host": DOMAIN}).status_code == 200  # the app, not her pretend site
        assert "Meera" not in c.get("/", headers={"host": DOMAIN}).text


# ---------- visitor limits ----------

def test_describe_limit_per_visitor(client, make_settings):
    client.app.dependency_overrides[__import__("app.config", fromlist=["get_settings"]).get_settings] = \
        lambda: make_settings(visitor_describes_per_day=2)
    s = json.loads((SELLERS / "meera_cakes.json").read_text())
    data = {"description": s["description"], "price_list": s["price_list"]}
    assert [client.post("/api/businesses", data=data).status_code for _ in range(3)] == [201, 201, 429]
    assert "tomorrow" in client.post("/api/businesses", data=data).json()["detail"]
    other = {"X-Forwarded-For": "203.0.113.9, 198.51.100.7"}  # last entry = the client Caddy saw
    assert client.post("/api/businesses", data=data, headers=other).status_code == 201
    assert client.post("/api/businesses", data=data, headers=ADMIN).status_code == 201  # admin exempt


def test_signed_in_user_limits_shops_and_describes_per_day(client, make_settings, engine):
    from app.config import get_settings

    client.app.dependency_overrides[get_settings] = lambda: make_settings(max_shops_per_user=2, user_describes_per_day=3)
    sign_in(client, "meera@example.org")
    s = json.loads((SELLERS / "meera_cakes.json").read_text())
    data = {"description": s["description"], "price_list": s["price_list"]}
    first = client.post("/api/businesses", data=data)
    assert [first.status_code, client.post("/api/businesses", data=data).status_code] == [201, 201]
    r = client.post("/api/businesses", data=data)
    assert r.status_code == 409 and "most one account can have" in r.json()["detail"]
    assert client.delete(f"/api/businesses/{first.json()['id']}").status_code == 200
    assert client.post("/api/businesses", data=data).status_code == 201  # third describe today
    assert client.delete(f"/api/businesses/{first.json()['id'] + 1}").status_code == 200
    r = client.post("/api/businesses", data=data)  # deleting shops doesn't reset the daily count
    assert r.status_code == 429 and "tomorrow" in r.json()["detail"]


def test_launch_limit_per_visitor(client, make_settings):
    from app.config import get_settings
    client.app.dependency_overrides[get_settings] = lambda: make_settings(visitor_launches_per_day=1)
    approve(client, plan(client, meera(client)))
    p2 = plan(client, meera(client, subdomain="meera2"))
    r = client.post(f"/api/plans/{p2['id']}/approve", json={})
    assert r.status_code == 429 and "tomorrow" in r.json()["detail"]
    assert client.post(f"/api/plans/{p2['id']}/approve", json={}, headers=ADMIN).status_code == 200


# ---------- light monitoring ----------

@pytest.fixture
def monitor(engine, settings, integ, claude):
    return Monitor(engine, settings, lambda _b: integ, claude)


def set_email(engine, business_id, email="meera@example.org"):
    """Give the shop a signed-in owner (alerts go to the owner's sign-in address)."""
    from app.models import Membership, User

    with Session(engine) as s:
        u = User(email=email, status="approved")
        s.add(u)
        s.commit()
        s.add(Membership(user_id=u.id, business_id=business_id))
        b = s.get(Business, business_id)
        b.guest_hash = ""
        s.add(b)
        s.commit()


def alerts(engine):
    with Session(engine) as s:
        return [(a.kind, a.key, a.sent_to) for a in s.exec(select(Alert).order_by(Alert.id)).all()]


def test_monitor_jobs_registered_15min_and_daily(monitor):
    # S13 B: one beat a minute; each shop's stable slot spreads the 15-minute and daily checks (test_s13_scale.py)
    monitor.register()
    jobs = {j.id: j for j in monitor.scheduler.get_jobs()}
    assert set(jobs) == {"monitor_tick"}
    assert jobs["monitor_tick"].trigger.interval.total_seconds() == 60
    assert not monitor.scheduler.running


def test_scheduler_is_off_when_disabled(monkeypatch, make_settings, engine):
    import app.db as db
    import app.main as main

    monkeypatch.setattr(db, "_engine", engine)  # the startup jobs must never touch a developer's real database

    monkeypatch.setattr(main, "get_settings", lambda: make_settings(monitor_enabled=False))
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "start_monitor", lambda _s: pytest.fail("scheduler started"))
    started = []
    monkeypatch.setattr(main, "start_mail_sender", lambda _s: started.append(1))  # S13: mail still goes out
    with TestClient(main.create_app()):
        pass
    assert started == [1]


def test_quick_check_ok_schedules_nothing(client, integ, monitor):
    sign_in(client, "meera@example.org")  # guest practice shops aren't watched
    biz = meera(client)
    approve(client, plan(client, biz))
    assert monitor.live_business_ids() == [biz["id"]]
    monitor.run_quick()
    assert monitor.scheduler.get_jobs() == []
    assert report(client, biz)["monitoring"]["last_quick"]["passed"] is True


def test_failure_rechecked_after_a_minute_then_fixed_without_alert(client, integ, engine, monitor):
    biz = full_launch(client, integ)
    set_email(engine, biz["id"])
    integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if r["name"] != "_dmarc"]
    assert monitor.check_business(biz["id"], "daily") == ["email_dmarc", "settings_match"]
    (job,) = monitor.scheduler.get_jobs()
    assert job.id == f"recheck-{biz['id']}" and job.args == (biz["id"], ["email_dmarc", "settings_match"])
    sent_before = len(integ.mailer.sent)
    assert monitor.recheck(*job.args) == []  # Doctor re-added DMARC; settings match again
    assert len(integ.mailer.sent) == sent_before and alerts(engine) == []


def test_unfixable_failure_alerts_owner_personal_email_once(client, integ, engine, monitor):
    biz = meera(client)
    approve(client, plan(client, biz))
    set_email(engine, biz["id"])
    integ.http.broken_cert.add("meera.localhost")
    assert monitor.check_business(biz["id"], "quick") == ["https"]
    assert monitor.recheck(biz["id"], ["https"]) == ["https"]
    mail = integ.mailer.sent[-1]
    assert mail["to"] == "meera@example.org" and "security certificate" in mail["body"]
    n = len(integ.mailer.sent)
    monitor.recheck(biz["id"], ["https"])
    assert len(integ.mailer.sent) == n  # same problem: no second email
    integ.http.broken_cert.clear()
    monitor.check_business(biz["id"], "quick")
    with Session(engine) as s:
        assert s.exec(select(Alert)).one().resolved_at is not None


def test_changed_setting_is_alert_only(client, integ, engine, monitor):
    biz = full_launch(client, integ)
    set_email(engine, biz["id"])
    integ.godaddy.set_records(DOMAIN, "TXT", "_dmarc", [{"data": "v=DMARC1; p=none"}])  # still valid, but changed
    assert monitor.check_business(biz["id"], "daily") == ["settings_match"]
    assert monitor.recheck(biz["id"], ["settings_match"]) == ["settings_match"]
    assert "changed since launch" in integ.mailer.sent[-1]["body"]
    assert integ.godaddy.get_records(DOMAIN)  # nothing was undone silently
    assert any(r["data"] == "v=DMARC1; p=none" for r in integ.godaddy.get_records(DOMAIN) if r["name"] == "_dmarc")


def test_no_personal_email_means_no_alert_but_logged(client, integ, engine, monitor):
    biz = meera(client)
    approve(client, plan(client, biz))
    integ.http.broken_cert.add("meera.localhost")
    monitor.recheck(biz["id"], ["https"])
    assert alerts(engine) == []
    assert events(engine, action="alert_check_failed")[-1].result == "skipped"


@pytest.mark.parametrize("days,expect", [(40, []), (25, ["30d"]), (5, ["7d"]), (0, ["1d"])])
def test_domain_expiry_warnings(client, integ, engine, monitor, days, expect):
    from datetime import UTC, datetime, timedelta

    biz = full_launch(client, integ)
    set_email(engine, biz["id"])
    integ.godaddy.expires[DOMAIN] = datetime.now(UTC) + timedelta(days=days, hours=12)
    monitor.run_daily()
    got = [k for kind, k, to in alerts(engine) if kind == "domain_expiry" and to != "(skipped)"]
    assert got == expect
    if expect:
        assert "renew it on godaddy.com" in integ.mailer.sent[-1]["body"]
        monitor.run_daily()  # not sent twice
        assert [k for kind, k, to in alerts(engine) if kind == "domain_expiry" and to != "(skipped)"] == expect


def test_domain_expiry_steps_30_then_7(client, integ, engine, monitor):
    from datetime import UTC, datetime, timedelta

    biz = full_launch(client, integ)
    set_email(engine, biz["id"])
    integ.godaddy.expires[DOMAIN] = datetime.now(UTC) + timedelta(days=20, hours=1)
    monitor.run_daily()
    integ.godaddy.expires[DOMAIN] = datetime.now(UTC) + timedelta(days=6, hours=1)
    monitor.run_daily()
    assert [k for kind, k, _ in alerts(engine) if kind == "domain_expiry"] == ["30d", "7d"]


def test_cert_expiry_warning(client, integ, engine, monitor):
    from datetime import UTC, datetime, timedelta

    sign_in(client, "meera@example.org")  # alerts go to the owner's sign-in address
    biz = meera(client)
    approve(client, plan(client, biz))
    integ.http.cert_end["meera.localhost"] = datetime.now(UTC) + timedelta(days=3, hours=1)
    monitor.run_daily()
    assert [(k, kind) for kind, k, to in alerts(engine)] == [("7d", "cert_expiry")]
    assert report(client, biz)["monitoring"]["cert_days_left"] == 3


@pytest.mark.skip(reason="PENDING REAL INFRA: monitoring against real authoritative DNS, real HTTPS cert dates "
                         "(RealHttpProbe.cert_expires), GoDaddy domain expiry and SMTP alerts — needs the VPS")
def test_monitoring_against_real_infra():
    pass
