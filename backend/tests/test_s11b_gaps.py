"""S11b Part 2: the gaps in the Doctor and monitoring. Each test was written failing first."""

import json

import httpx
import pytest
from sqlmodel import Session, select

from app.agents import launch_check
from app.agents.checker import CHECKS, run_check
from app.agents.claude_client import ClaudeUnavailable
from app.agents.launch_check import run_checks
from app.checks.dns_resolver import Answer, AuthoritativeResolver
from app.checks.http_probe import RealHttpProbe
from app.models import Alert, AuditEvent, Business, CheckResult, CheckRun, Evidence
from app.monitor import scheduler
from app.monitor.scheduler import Monitor
from tests.conftest import ADMIN_TOKEN, sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_m4_repair import DOMAIN, ScriptedDoctor, ctx_for, launched
from tests.test_m4_report import alerts, full_launch, set_email

SHOP = "meera.launchwitness.com"


class ClaudeDown:
    def __init__(self):
        self.calls = 0

    def ask_json(self, **_kw):
        self.calls += 1
        raise ClaudeUnavailable("down")

    live = ask_json


@pytest.fixture
def monitor(engine, settings, integ, claude):
    return Monitor(engine, settings, lambda _b: integ, claude)


def told(integ) -> list[dict]:
    """Emails to the owner about a problem (not the test-order emails a check sends)."""
    return [m for m in integ.mailer.sent if "TEST, not a real order:" not in m["subject"]]


def last_run(engine) -> CheckRun:
    with Session(engine) as s:
        return s.exec(select(CheckRun).order_by(CheckRun.id.desc())).first()


def plan_id(engine, business_id: int) -> int:
    with Session(engine) as s:
        return launch_check.latest_launched_plan(s, business_id).id


# ---------- 2. the checker's own HTTPS probe goes through the SSRF guard ----------

IPS = {SHOP: ["93.184.216.34"], "inside.example": ["10.0.0.5"], "evil.example": ["93.184.216.35"]}


def probe(location: str | None):
    asked = []

    def handler(request):
        asked.append(request.headers["host"])
        if location and request.url.path == "/":
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(200, text="<html>shop</html>")

    return RealHttpProbe(transport=httpx.MockTransport(handler), resolve=lambda h: IPS.get(h, [])), asked


@pytest.mark.parametrize("location", ["https://10.0.0.1/", "http://meera.launchwitness.com/x", "https://evil.example/",
                                      "https://inside.example/", "https://169.254.169.254/latest/meta-data/"])
def test_https_probe_never_follows_a_redirect_off_the_shop(location):
    p, asked = probe(location)
    r = p.fetch(f"https://{SHOP}/")
    assert not r.ok and r.status is None
    assert asked == [SHOP]  # one request to the shop itself; the redirect was never followed


def test_https_probe_refuses_private_addresses_and_still_works_for_the_shop():
    p, asked = probe(None)
    assert not p.fetch("https://inside.example/").ok and asked == []
    assert p.cert_expires("inside.example") is None  # no handshake with a private address either
    r = p.fetch(f"https://{SHOP}/")
    assert r.ok and r.status == 200 and r.cert_valid and "shop" in r.body_snippet
    p2, _ = probe("/home")  # a redirect on the shop's own host is fine
    assert p2.fetch(f"https://{SHOP}/").ok


# ---------- 5. a DNS failure on OUR side is never blamed on the seller ----------

def test_authoritative_resolver_tells_no_answer_from_our_failure():
    def finder(records):
        return type("F", (), {"resolve": lambda self, n, t: records.get((n, t), [])})()

    def boom(*_a):
        raise TimeoutError

    ns = {("launchwitness.com", "NS"): ["ns1.example."], ("ns1.example", "A"): ["192.0.2.53"]}
    assert AuthoritativeResolver(finder=finder(ns), query=boom).lookup(SHOP, "A") == Answer("error")
    assert AuthoritativeResolver(finder=finder({}), query=boom).lookup(SHOP, "A") == Answer("error")  # no nameservers found
    assert AuthoritativeResolver(finder=finder(ns), query=lambda *_a: []).lookup(SHOP, "A") == Answer("nodata")
    assert AuthoritativeResolver(finder=finder(ns), query=lambda *_a: ["1.2.3.4"]).lookup(SHOP, "A").values == ("1.2.3.4",)


def test_our_dns_failure_is_couldnt_check_with_no_fix_and_no_alert(client, integ, engine, settings, monitor):
    biz = full_launch(client, integ)
    set_email(engine, biz["id"])
    ctx = ctx_for(engine, settings, integ, plan_id(engine, biz["id"]))
    integ.dns.lookup = lambda _n, _t: Answer("error")  # our resolver is down
    for name in ("site_points", "email_mx", "email_spf", "email_dkim", "email_dmarc"):
        out = run_check(ctx, name)
        assert not out.passed and out.unfinished, name  # never "passed", and never a fault of hers
        assert out.plain == ("We couldn't look this up just now. The problem is on our side, not yours, and nothing "
                             "about your shop has changed. We'll check again on the next round.")
    writes, sent = len(integ.godaddy.writes()), len(integ.mailer.sent)
    doctor = ScriptedDoctor({"plain_explanation": "x", "fix_id": "repoint_site"})
    summary = run_checks(engine, settings, integ, doctor, ctx.plan.id, trigger="manual",
                         names=["site_points", "email_mx"])
    assert not summary.passed and all(f.unfinished for f in summary.failed)
    assert doctor.calls == [] and len(integ.godaddy.writes()) == writes  # nothing "fixed" on a guess
    assert monitor.check_business(biz["id"], "quick") == []  # nothing to re-check as a failure of hers
    assert monitor.scheduler.get_jobs() == [] and alerts(engine) == []
    assert len(integ.mailer.sent) == sent and last_run(engine).passed is False


# ---------- 3. never stalls, never stale ----------

def test_a_slow_shop_is_recorded_as_couldnt_finish_never_as_passed(client, integ, engine, settings, monkeypatch):
    biz = full_launch(client, integ)
    ticks = iter(range(0, 100000, 40))
    monkeypatch.setattr(launch_check, "clock", lambda: next(ticks))  # every look at the clock is 40 s later
    summary = run_checks(engine, settings, integ, ScriptedDoctor({}), plan_id(engine, biz["id"]), trigger="monitor_daily",
                         names=scheduler.daily_checks("full"), fix=False, budget_seconds=60)
    assert not summary.passed
    unfinished = [f for f in summary.failed if f.unfinished]
    assert unfinished and all(f.plain == "This check couldn't finish in time, so we don't know yet. We'll try again "
                                         "on the next round." for f in unfinished)
    with Session(engine) as s:
        rows = s.exec(select(CheckResult).where(CheckResult.run_id == summary.run_id)).all()
        assert {r.check for r in rows} == set(scheduler.daily_checks("full"))  # every check has a row: none is silent
        assert [r.check for r in rows if r.passed] == ["site_points"]  # only what really finished counts
        assert all(json.loads(r.detail).get("unfinished") for r in rows if not r.passed)
    assert last_run(engine).finished_at is not None


def test_one_broken_shop_does_not_stop_the_others(client, new_client, integ, engine, settings, claude):
    sign_in(client, "meera@example.org")
    first = meera(client)
    approve(client, plan(client, first))
    other = new_client()
    sign_in(other, "imran@example.org")
    second = meera(other, subdomain="imran")
    approve(other, plan(other, second))

    def integ_for(b: Business):
        if b.id == first["id"]:
            raise RuntimeError("this shop's services blew up")
        return integ

    mon = Monitor(engine, settings, integ_for, claude)
    mon.run_quick()
    mon.run_daily()
    with Session(engine) as s:
        runs = s.exec(select(CheckRun).where(CheckRun.business_id == second["id"],
                                             CheckRun.trigger.like("monitor_%"))).all()
        assert len(runs) == 2 and all(r.passed for r in runs)
        failed = s.exec(select(AuditEvent).where(AuditEvent.action == "monitor_shop", AuditEvent.result == "failed")).all()
        assert len(failed) == 2 and failed[0].business_id == first["id"] and "couldn't finish" in failed[0].detail


def test_monitor_gives_each_shop_a_time_budget(client, integ, engine, settings, claude, monkeypatch):
    sign_in(client, "meera@example.org")
    biz = meera(client)
    approve(client, plan(client, biz))
    seen = {}
    real = scheduler.run_checks
    monkeypatch.setattr(scheduler, "run_checks", lambda *a, **kw: seen.update(kw) or real(*a, **kw))
    Monitor(engine, settings, lambda _b: integ, claude).run_quick()
    assert 0 < seen["budget_seconds"] <= 120
    assert scheduler.SHOP_BUDGET["daily"] >= scheduler.SHOP_BUDGET["quick"]


def test_every_outside_call_has_a_timeout():
    """A call with no timeout can hang a job for ever; this pins the limits we rely on."""
    import inspect

    from app.agents import claude_client
    from app.checks import dns_resolver, safe_fetch
    from app.godaddy import client as godaddy
    from app.mail import imap, smtp

    assert 0 < smtp.TIMEOUT_S <= 30
    assert "timeout=" in inspect.getsource(imap) and "timeout=" in inspect.getsource(godaddy)
    assert "timeout=" in inspect.getsource(claude_client)
    assert dns_resolver.RealDnsResolver()._r.lifetime <= 10
    assert safe_fetch.MAX_SECONDS <= 30 and RealHttpProbe().timeout <= 15


# ---------- 4. flapping ----------

def test_a_check_that_keeps_breaking_stops_being_fixed_and_emails_once(client, integ, engine, monitor):
    biz = full_launch(client, integ)
    set_email(engine, biz["id"])

    def break_it():
        integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if r["name"] != "_dmarc"]

    sent = len(integ.mailer.sent)
    for _ in range(launch_check.MAX_AUTO_FIXES_PER_DAY):  # break → fixed, quietly, up to the daily cap
        break_it()
        assert monitor.recheck(biz["id"], ["email_dmarc"]) == []
    assert len(integ.mailer.sent) == sent
    break_it()
    writes = len(integ.godaddy.writes())
    assert monitor.recheck(biz["id"], ["email_dmarc"]) == ["email_dmarc"]  # the cap: no more automatic fixes today
    assert len(integ.godaddy.writes()) == writes
    mail = integ.mailer.sent[-1]
    assert len(integ.mailer.sent) == sent + 1 and "keeps breaking" in mail["subject"]
    assert "we've stopped fixing it automatically" in mail["body"]
    repairs = json.loads(last_run(engine).repairs_json)
    assert repairs[0]["doctor"]["fix_id"] == "needs_owner" and "keeps breaking" in repairs[0]["doctor"]["finding"]
    monitor.recheck(biz["id"], ["email_dmarc"])
    assert len(integ.mailer.sent) == sent + 1  # still broken: no second email


def test_fail_alert_recover_fail_again_sends_one_keeps_breaking_email_then_goes_quiet(client, integ, engine, monitor):
    biz = meera(client)
    approve(client, plan(client, biz))
    set_email(engine, biz["id"])

    def cycle():
        integ.http.broken_cert.add("meera.localhost")
        monitor.check_business(biz["id"], "quick")
        monitor.recheck(biz["id"], ["https"])
        integ.http.broken_cert.clear()
        monitor.check_business(biz["id"], "quick")  # recovers: the alert is resolved

    cycle()
    assert len(told(integ)) == 1 and "keeps breaking" not in told(integ)[-1]["subject"]
    cycle()
    assert len(told(integ)) == 2 and "keeps breaking" in told(integ)[-1]["subject"]
    for _ in range(4):
        cycle()
    assert len(told(integ)) == 2  # no email storm, however often it flaps today
    kinds = [k for k, _key, _to in alerts(engine)]
    assert kinds.count("check_flapping") == 1


# ---------- 5. failures of our own ----------

def test_alert_that_could_not_be_sent_is_recorded_retried_and_shown_to_the_team(client, integ, engine, monitor):
    biz = meera(client)
    approve(client, plan(client, biz))
    set_email(engine, biz["id"])
    integ.http.broken_cert.add("meera.localhost")
    integ.mailer.fail = True  # our own mail service is down
    assert monitor.recheck(biz["id"], ["https"]) == ["https"]
    assert alerts(engine) == []  # not marked as sent
    with Session(engine) as s:
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "alert_check_failed",
                                               AuditEvent.result == "failed")).first() is not None
    admin = {"X-Admin-Token": ADMIN_TOKEN}
    assert "alerts_unsent" in client.get("/api/health", headers=admin).json().get("warning_codes", [])
    assert "alerts_unsent" not in client.get("/api/health").json().get("warning_codes", [])  # the team only
    integ.mailer.fail = False
    assert monitor.recheck(biz["id"], ["https"]) == ["https"]  # the next run tries again
    assert [k for k, _key, _to in alerts(engine)] == ["check_failed"] and len(told(integ)) == 1
    assert "alerts_unsent" not in client.get("/api/health", headers=admin).json().get("warning_codes", [])


def test_watch_alert_that_could_not_be_sent_is_retried(engine, mailer):
    from app import watch
    from app.models import User, WatchedAddress
    from tests.test_s11b_matrix import TlsSeen, Web, page, zone

    with Session(engine) as s:
        u = User(email="watcher@example.org", status="approved")
        s.add(u)
        s.commit()
        s.add(WatchedAddress(user_id=u.id, host="shop.example", problems_json="[]"))
        s.commit()
    dns, web = zone("google", **{"TXT___dmarc._AT_": None}), Web(page(), tls=TlsSeen("ok"))
    mailer.fail = True
    assert watch.run_daily(engine, mailer, dns, web) == 0
    mailer.fail = False
    assert watch.run_daily(engine, mailer, dns, web) == 1  # still owed: sent now
    assert watch.run_daily(engine, mailer, dns, web) == 0  # and only once


FULL_BREAKS = {"email_mx": ("MX", "@"), "email_dmarc": ("TXT", "_dmarc"), "site_points": ("A", "@")}


@pytest.mark.parametrize("check", sorted(FULL_BREAKS))
def test_with_claude_down_the_standard_fix_still_runs(client, integ, engine, settings, check):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    rtype, name = FULL_BREAKS[check]
    integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if not (r["type"] == rtype and r["name"] == name)]
    down = ClaudeDown()
    summary = run_checks(engine, settings, integ, down, ctx.plan.id, trigger="manual", names=[check])
    assert summary.passed, summary.failed
    repairs = json.loads(last_run(engine).repairs_json)
    assert repairs[0]["fixed"] and repairs[0]["attempts"][-1]["applied"]


@pytest.mark.parametrize("mode", ["sandbox", "full"])
@pytest.mark.parametrize("check", sorted(CHECKS))
def test_every_failed_check_ends_in_a_fix_or_exact_steps_even_with_claude_down(client, integ, engine, settings, mode,
                                                                                check, monkeypatch):
    """Coverage: no check ends in a silent "unknown". Each one is forced to fail; the run must hold either an
    applied fix or a "needs you" with plain steps written by code."""
    from app.agents import checker
    from app.agents.checker import Outcome

    ctx = ctx_for(engine, settings, integ, launched(client, integ, mode))
    monkeypatch.setitem(checker.CHECKS, check, lambda _ctx: Outcome(check, False, "It failed.", "forced"))
    summary = run_checks(engine, settings, integ, ClaudeDown(), ctx.plan.id, trigger="manual", names=[check])
    assert [f.check for f in summary.failed] == [check]
    entry = next(r for r in json.loads(last_run(engine).repairs_json) if r["check"] == check)
    doctor = entry.get("doctor") or {}
    steps = doctor.get("owner_instruction", "")
    assert entry["attempts"] or (doctor.get("fix_id") == "needs_owner" and len(steps) > 40), entry
    assert "unknown" not in steps.lower() and "error" not in steps.lower()
    with Session(engine) as s:
        row = s.exec(select(CheckResult).where(CheckResult.run_id == summary.run_id, CheckResult.check == check)
                     .order_by(CheckResult.id.desc())).first()
        assert entry["attempts"] or json.loads(row.doctor_json)["owner_instruction"] == steps  # shown on the report


# ---------- 6. practice and real stay separate ----------

class Untouchable:
    """The real services. A practice shop must never reach them."""

    fake = False

    def __getattr__(self, name):
        raise AssertionError(f"a practice shop touched the real {name}")


def test_practice_shops_are_never_checked_against_real_services(client, integ, engine, settings, claude):
    from app.integrations import for_business

    sign_in(client, "meera@example.org")
    biz = meera(client)
    approve(client, plan(client, biz))
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).practice is True
    mon = Monitor(engine, settings, lambda b: for_business(b, Untouchable(), integ), claude)
    mon.run_quick()
    mon.run_daily()
    integ.http.broken_cert.add("meera.localhost")
    mon.check_business(biz["id"], "quick")
    mon.recheck(biz["id"], ["https"])
    with Session(engine) as s:
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "monitor_shop")).all() == []  # nothing blew up
        ev = s.exec(select(Evidence).where(Evidence.business_id == biz["id"])).all()
        assert ev and all(e.practice for e in ev)  # every piece of proof is labelled practice
        assert {a.business_id for a in s.exec(select(Alert)).all()} <= {biz["id"]}


def test_a_paused_shop_has_no_public_proof_page(client, new_client, engine):
    biz = meera(client)
    approve(client, plan(client, biz))
    url = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]
    path = "/r/" + url.rsplit("/r/", 1)[1]
    assert new_client().get(path).status_code == 200
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.paused = True
        s.add(b)
        s.commit()
    r = new_client().get(path)
    assert r.status_code == 404 and "Proven" not in r.text
