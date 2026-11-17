"""S11: the whole system under random faults (pretend GoDaddy/DNS/mail only, no network, no Claude calls).

Each seeded run: an approved user makes a shop -> go-live checklist -> real launch -> checks + Doctor -> a quick and
a daily monitoring round -> a customer order + status changes, with failures injected at random. After every run the
eight invariants below must hold. A failing seed is a real bug: reproduce it with `one_run(seed, make_settings)`.
"""

import json
import random
import smtplib

import pytest
from sqlmodel import Session, select

from app import proof
from app.agents.claude_client import ClaudeUnavailable, FixtureClaudeClient
from app.agents.launch_check import start_run
from app.config import get_settings
from app.db import init_db, make_engine
from app.mail.smtp import FakeMailer
from app.models import Alert, AuditEvent, Business, CheckResult, CheckRun, DnsBackup, Evidence, Order, Plan
from app.monitor.scheduler import Monitor
from app.sites.orders import STATUS_STEPS, can_move
from app.startup import reconcile
from tests.conftest import AppClient, pickup, set_user, sign_in
from tests.test_m3_launch import meera
from tests.test_m4_report import real_plan, report, two_worlds_client
from tests.test_s9_phase2_access import call, owner_urls

HOST, SHOP = "meera.localhost", {"host": "meera.localhost"}
OWNER, OTHER = "a@example.org", "b@example.org"
ORDER = {"qty_0": "1", "customer_name": "Asha Rao", "customer_phone": "98765 43210", **pickup()}
FAULTS = ("dns_missing", "dns_wrong", "cert_not_ready", "smtp_down", "smtp_login", "mail_lost", "write_fails",
          "restart", "claude_down", "double_submit", "two_runs", "cert_later")
MACHINE_STEPS = {"dns_answer", "http_response", "form_post", "smtp_accepted", "imap_seen",
                 "public_resolvers"}  # S13b: a lookup through 8.8.8.8 / 1.1.1.1 / 9.9.9.9 (information only)


class AwayClaude(FixtureClaudeClient):
    """Saved answers for describing the shop; the Doctor's Claude is unavailable when `down`."""

    def __init__(self, down: bool):
        super().__init__()
        self.down = down

    def ask_json(self, *, fixture, **kw):
        if self.down and fixture.startswith(("doctor_", "investigate_")):
            raise ClaudeUnavailable("staged")
        return super().ask_json(fixture=fixture, **kw)


class BrokenMailer:
    def __init__(self, error: Exception):
        self.error = error

    def send(self, **_kw):
        raise self.error

    def login_test(self) -> str:
        return "login refused: the mail service did not accept our sign-in"


def one_run(seed: int, make_settings) -> dict:
    rng = random.Random(seed)
    on = {f for f in FAULTS if rng.random() < 0.3}
    engine = make_engine("sqlite://")
    init_db(engine)
    claude = AwayClaude("claude_down" in on)
    a, server, practice = two_worlds_client(make_settings, engine, FakeMailer(), claude)
    settings = a.app.dependency_overrides[get_settings]()
    good_mailer = server.mailer
    why = f"seed {seed}, faults {sorted(on)}"

    def strangers_get_404(plan_id: int) -> None:  # invariant 8, at any point in the run
        for method, url in owner_urls(biz["id"], plan_id):
            assert call(b, method, url).status_code == 404, (why, method, url)

    with a:
        b = AppClient(a.app)
        for client, email in ((a, OWNER), (b, OTHER)):
            sign_in(client, email)
            set_user(engine, email, status="approved")
        biz = meera(a)
        # ----- launch, with launch-time faults -----
        if "dns_missing" in on:
            server.dns.hide.add((HOST, "A"))
        if "write_fails" in on:
            server.godaddy.fail_next["set_records"] = 1
        if "cert_not_ready" in on:
            server.http.broken_cert.add(HOST)
        if "smtp_down" in on:
            server.mailer = BrokenMailer(ConnectionError("staged"))
        elif "smtp_login" in on:
            server.mailer = BrokenMailer(smtplib.SMTPAuthenticationError(535, b"staged"))
        if "mail_lost" in on:
            good_mailer.drop = True
        p = real_plan(a, biz)
        assert a.post(f"/api/plans/{p['id']}/approve", json={"approved_by": "A"}).status_code == 200, why
        strangers_get_404(p["id"])
        if "restart" in on:
            reconcile(engine)
        p = a.get(f"/api/plans/{p['id']}").json()
        resumed = p["status"] == "failed"
        if resumed:  # invariant 4: every failed plan can be resumed
            server.dns.hide.discard((HOST, "A"))
            server.godaddy.fail_next.clear()
            r = a.post(f"/api/plans/{p['id']}/resume")
            assert r.status_code == 200, (why, r.text)
            p = a.get(f"/api/plans/{p['id']}").json()
        assert p["status"] in ("done", "failed"), (why, p["status"])
        expected_status, posted = None, False
        if p["status"] == "done":
            # ----- after launch: break things, check, monitor -----
            if "dns_wrong" in on:
                zone = server.godaddy.zones[settings.app_domain]
                server.godaddy.zones[settings.app_domain] = [
                    {**r, "data": "203.0.113.9"} if r["type"] == "A" and r["name"] == "meera" else r for r in zone]
            if "cert_later" in on:  # the padlock breaks after launch, and asking again doesn't help
                server.http.broken_cert.add(HOST)
            if "two_runs" in on:
                with Session(engine) as s:
                    start_run(s, biz["id"], p["id"], "manual")
                assert a.post(f"/api/businesses/{biz['id']}/checks").status_code == 409, why  # one at a time
                reconcile(engine)  # the first one "died": the restart closes it
            assert a.post(f"/api/businesses/{biz['id']}/checks").status_code == 202, why
            mon = Monitor(engine, settings, lambda _b: server, claude)
            for kind in ("quick", "daily"):
                failing = mon.check_business(biz["id"], kind)
                for _ in range(2 if failing else 0):  # the same problem twice: one alert
                    mon.recheck(biz["id"], failing)
            # ----- a customer order and the owner's status changes -----
            page = a.get("/", headers=SHOP)
            if page.status_code == 200 and 'name="order_token" value="' in page.text:
                token = page.text.split('name="order_token" value="', 1)[1].split('"', 1)[0]
                for _ in range(2 if "double_submit" in on else 1):
                    posted = a.post("/order", data={**ORDER, "order_token": token}, headers=SHOP).status_code == 200
            with Session(engine) as s:
                real_orders = s.exec(select(Order).where(Order.business_id == biz["id"], Order.is_test == False)).all()  # noqa: E712
            if posted:
                assert len(real_orders) == 1, (why, "invariant 6: a double submit made", len(real_orders), "orders")
                expected_status = "new"
                for to in rng.choices(sorted(STATUS_STEPS), k=4):
                    r = a.post(f"/api/businesses/{biz['id']}/orders/{real_orders[0].id}/status", json={"status": to})
                    allowed = can_move(expected_status, to)
                    assert (r.status_code == 200) if allowed else (r.status_code in (409, 422)), (why, expected_status, to, r.status_code)
                    expected_status = to if allowed else expected_status
        reconcile(engine)
        strangers_get_404(p["id"])
        rep = report(a, biz)

    with Session(engine) as s:
        shop = s.get(Business, biz["id"])
        ev = s.exec(select(Evidence).where(Evidence.business_id == shop.id)).all()
        # 0. (S11d) the proof log is one unbroken hash chain, whatever failed along the way
        from app import chain

        assert chain.verify(s, shop.id) == {"intact": True, "rows": len(ev), "head": max(ev, key=lambda e: e.id).hash if ev else ""}, (why, "invariant 0: proof chain")
        # 1. nothing is "proven" without its stored evidence; "accepted" is never "delivered"
        for c in (rep.get("run") or {}).get("checks", []):
            mine = [e for e in ev if e.run_id == rep["run"]["id"] and e.check == c["check"]]
            if c.get("state") == "proven":
                assert mine, (why, "invariant 1: proven without evidence", c["check"])
                if c["check"] == "test_order":
                    assert any(e.step in proof.DELIVERED for e in mine), (why, "invariant 1: accepted shown as delivered")
        # 2. practice never counts for a real shop; owner-confirmed steps are never machine-verified
        if not shop.practice:
            real_runs = {r.id for r in s.exec(select(CheckRun).where(CheckRun.plan_id == p["id"])).all()}
            assert not [e for e in ev if e.run_id in real_runs and e.practice], (why, "invariant 2: practice evidence on a real shop")
            assert rep["practice"] is False, why
        assert {e.step for e in ev} <= MACHINE_STEPS, (why, "invariant 2: a step no machine saw", {e.step for e in ev})
        # 3. every DNS write: this shop's own A record in the app zone, through the guard, after a backup
        writes = server.godaddy.writes()
        assert all(w[1:] == (settings.app_domain, "A", "meera") for w in writes), (why, "invariant 3", writes)
        assert practice.godaddy.writes() == [], (why, "invariant 3: a real launch wrote to the pretend world")
        if writes:
            backups = s.exec(select(DnsBackup).where(DnsBackup.business_id == shop.id)).all()
            first = s.exec(select(AuditEvent).where(AuditEvent.business_id == shop.id, AuditEvent.action == "dns_write")
                           .order_by(AuditEvent.id)).first()
            assert backups, (why, "invariant 3: a write without a backup")
            assert first is None or min(x.created_at for x in backups) <= first.created_at, (why, "invariant 3: backup after the write")
        assert not s.exec(select(AuditEvent).where(AuditEvent.action == "dns_write", AuditEvent.result == "refused")).all(), why
        # 4. nothing is left "running" after the reconciler
        assert not s.exec(select(Plan).where(Plan.status.in_(("approved", "running")))).all(), (why, "invariant 4: plan")
        assert not s.exec(select(CheckRun).where(CheckRun.status == "running")).all(), (why, "invariant 4: check run")
        # 5. at most one alert email per problem, and only to the shop's owners
        alerts = s.exec(select(Alert).where(Alert.business_id == shop.id)).all()
        keys = [(x.kind, x.key) for x in alerts if x.resolved_at is None]
        assert len(keys) == len(set(keys)), (why, "invariant 5: two open alerts for one problem", keys)
        mails = [m for m in good_mailer.sent if m["subject"].startswith("Something needs attention")]
        emailed = [x for x in alerts if x.kind == "check_failed" and not x.sent_to.startswith("(")]
        assert len(mails) == len(emailed), (why, "invariant 5: alert emails", len(mails))
        # 9 (S11b). a problem that keeps coming back gets at most ONE "keeps breaking" email per check per day
        flapping = [x.key for x in alerts if x.kind == "check_flapping"]
        storms = [m for m in good_mailer.sent if m["subject"].startswith("Something keeps breaking")]
        assert len(storms) == len(flapping) == len(set(flapping)), (why, "invariant 9: keeps-breaking emails", flapping)
        # 10 (S11b). a check that couldn't finish is never recorded as passed, and neither is its run
        for row in s.exec(select(CheckResult).where(CheckResult.business_id == shop.id)).all():
            if json.loads(row.detail).get("unfinished"):
                assert not row.passed, (why, "invariant 10: an unfinished check counted as passed", row.check)
                assert not s.get(CheckRun, row.run_id).passed, (why, "invariant 10: a run with an unfinished check passed")
        assert all(m["to"] == OWNER for m in good_mailer.sent), (why, "invariant 5: mail to someone else",
                                                                 {m["to"] for m in good_mailer.sent})
        # 6. the order's status only moved along allowed steps
        if expected_status is not None:
            assert s.exec(select(Order).where(Order.business_id == shop.id, Order.is_test == False)).one().status == expected_status, why  # noqa: E712
        # 7. money is never spent
        for world in (server, practice):
            assert not [x for x in world.godaddy.calls if x[0] == "purchase_domain"], (why, "invariant 7: a purchase call")
        assert not s.exec(select(AuditEvent).where(AuditEvent.action.like("%purchase%"), AuditEvent.result == "ok")).all(), why
    proven = sum(1 for c in (rep.get("run") or {}).get("checks", []) if c.get("state") == "proven")
    return {"faults": on, "launched": p["status"] == "done", "proven": proven, "writes": len(writes),
            "alerts": len(mails), "ordered": posted, "evidence": len(ev), "resumed": resumed}


def test_invariants_hold_under_random_faults(make_settings):
    runs = [one_run(seed, make_settings) for seed in range(20)]
    assert set().union(*(r["faults"] for r in runs)) == set(FAULTS)  # every kind of fault was really injected
    # ...and the invariants weren't true only because nothing happened
    for what in ("launched", "proven", "writes", "alerts", "ordered", "evidence", "resumed"):
        assert any(r[what] for r in runs), f"no run had any {what}"


@pytest.mark.slow
def test_invariants_hold_under_random_faults_long(make_settings):
    for seed in range(20, 260):
        one_run(seed, make_settings)
