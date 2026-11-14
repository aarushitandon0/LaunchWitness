"""M4 (code-only parts, fakes): Checker, playbook, Doctor — incl. refuse-outside-playbook."""

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.agents.checker import checks_for, run_all, run_check
from app.agents.claude_client import FixtureClaudeClient
from app.agents.doctor import MAX_ATTEMPTS, DoctorRefused, diagnose, repair
from app.agents.executor import Ctx
from app.agents.playbook import FIXES_FOR, PLAYBOOK, apply_fix
from app.models import AuditEvent, Business, CheckResult, Order, Plan
from tests.test_m3_launch import approve, meera, plan

FIXTURES = Path(__file__).parent / "fixtures" / "claude"
DOMAIN = "meerascakes.in"


class ScriptedDoctor:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def ask_json(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def launched(client, integ, mode="full") -> int:
    if mode == "full":
        integ.godaddy.owned.add(DOMAIN)
        integ.godaddy.zones[DOMAIN] = [{"type": "TXT", "name": "@", "data": "keep-me"}]
        p = approve(client, plan(client, meera(client), "full", DOMAIN))
    else:
        p = approve(client, plan(client, meera(client)))
    assert p["status"] == "done", p["steps"]
    return p["id"]


def ctx_for(engine, settings, integ, plan_id):
    s = Session(engine)
    pl = s.get(Plan, plan_id)
    return Ctx(s, settings, integ, pl, s.get(Business, pl.business_id))


def drop(integ, rtype, name):
    integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if not (r["type"] == rtype and r["name"] == name)]


# ---------- Checker ----------

def test_full_launch_all_checks_green(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    outs = run_all(ctx)
    assert [o.check for o in outs] == ["site_points", "https", "email_mx", "email_spf", "email_dkim", "email_dmarc",
                                       "test_order", "launch_clean"]
    assert all(o.passed for o in outs), [(o.check, o.detail) for o in outs]
    assert len(ctx.session.exec(select(CheckResult)).all()) == 8
    test_order = ctx.session.exec(select(Order).where(Order.is_test)).one()
    assert integ.inbox.find(subject_contains=f"(#{test_order.id})")[0].subject.startswith("[TEST] New order")


def test_sandbox_runs_site_checks_only(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ, "sandbox"))
    assert checks_for(ctx) == ["site_points", "https", "test_order", "launch_clean"]
    assert all(o.passed for o in run_all(ctx))


@pytest.mark.parametrize("breakage,check", [
    (lambda i: drop(i, "MX", "@"), "email_mx"),
    (lambda i: drop(i, "TXT", "_dmarc"), "email_dmarc"),
    (lambda i: drop(i, "TXT", "titan1._domainkey"), "email_dkim"),
    (lambda i: drop(i, "A", "@"), "site_points"),
    (lambda i: i.http.broken_cert.add(DOMAIN), "https"),
    (lambda i: setattr(i.mailer, "drop", True), "test_order"),
])
def test_each_check_detects_its_failure(client, integ, engine, settings, breakage, check):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    breakage(integ)
    out = run_check(ctx, check)
    assert not out.passed and out.plain
    for word in ("MX", "DNS", "TXT", "SPF", "DKIM", "DMARC"):
        assert word not in out.plain  # seller-facing text stays plain


def test_spf_check_needs_titan_include(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    integ.godaddy.set_records(DOMAIN, "TXT", "@", [{"data": "v=spf1 -all"}])
    assert not run_check(ctx, "email_spf").passed


def test_launch_clean_fails_for_unfinished_plan(client, integ, engine, settings):
    integ.dns.hide.add(("meera.localhost", "A"))
    p = approve(client, plan(client, meera(client)))
    ctx = ctx_for(engine, settings, integ, p["id"])
    assert not run_check(ctx, "launch_clean").passed


def test_crashing_check_is_a_failed_check(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))

    def boom(_url):
        raise RuntimeError("probe exploded")

    integ.http.fetch = boom
    out = run_check(ctx, "https")
    assert not out.passed and "RuntimeError" in out.detail


# ---------- Playbook ----------

def test_playbook_is_exactly_the_spec_list():
    assert set(PLAYBOOK) == {"restore_backup", "readd_mx", "readd_email_auth", "retry_certificate", "repoint_site"}
    assert all(fixes <= set(PLAYBOOK) for fixes in FIXES_FOR.values())


def test_restore_backup_puts_settings_back(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    apply_fix(ctx, "restore_backup")
    assert integ.godaddy.zones[DOMAIN] == [{"type": "TXT", "name": "@", "data": "keep-me"}]


def test_fix_writes_stay_guarded(client, integ, engine, settings):
    from app.agents.executor import StepFailed

    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    ctx.business.domain = None
    ctx.session.add(ctx.business)
    ctx.session.commit()
    before = len(integ.godaddy.writes())
    with pytest.raises(StepFailed):
        apply_fix(ctx, "readd_mx")
    assert len(integ.godaddy.writes()) == before


def test_apply_fix_rejects_unknown_ids(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    with pytest.raises(ValueError):
        apply_fix(ctx, "rm_rf")


# ---------- Doctor ----------

@pytest.mark.parametrize("path", sorted(FIXTURES.glob("doctor_*.json")))
def test_doctor_fixtures_are_valid_and_plain(path):
    d = json.loads(path.read_text())
    check = path.stem.removeprefix("doctor_")
    assert d["fix_id"] in FIXES_FOR[check]
    assert not any(w in d["plain_explanation"] for w in ("MX", "DNS", "TXT", "SPF", "DKIM", "DMARC"))


def test_missing_dmarc_is_explained_fixed_and_rechecked(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    drop(integ, "TXT", "_dmarc")
    failed = run_check(ctx, "email_dmarc")
    claude = FixtureClaudeClient()
    result = repair(claude, ctx, failed)
    assert result.fixed and len(result.attempts) == 1
    a = result.attempts[0]
    assert a["fix_id"] == "readd_email_auth" and a["applied"] and a["passed"]
    assert a["explanation"] == "A missing protection setting means order emails could land in spam."
    assert claude.calls == ["doctor_email_dmarc"]
    acts = [(e.action, e.result) for e in ctx.session.exec(select(AuditEvent).order_by(AuditEvent.id)).all()]
    tail = acts[acts.index(("check_email_dmarc", "fail")):]
    assert ("diagnose", "ok") in tail and ("fix_readd_email_auth", "ok") in tail
    assert ("check_email_dmarc", "pass") in tail and tail[-1] == ("repair", "fixed")
    assert ("TXT", "@") in {(r["type"], r["name"]) for r in integ.godaddy.zones[DOMAIN]}  # other TXT kept


def test_doctor_fix_outside_playbook_is_refused(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    drop(integ, "TXT", "_dmarc")
    failed = run_check(ctx, "email_dmarc")
    writes = len(integ.godaddy.writes())
    evil = ScriptedDoctor({"plain_explanation": "I'll just delete everything.", "fix_id": "delete_all_records"})
    with pytest.raises(DoctorRefused):
        diagnose(evil, ctx, failed)
    result = repair(evil, ctx, failed)
    assert not result.fixed and len(result.attempts) == MAX_ATTEMPTS
    assert all(not a["applied"] for a in result.attempts)
    assert len(integ.godaddy.writes()) == writes  # nothing touched
    refused = ctx.session.exec(select(AuditEvent).where(AuditEvent.action == "diagnose",
                                                        AuditEvent.result == "refused")).all()
    assert len(refused) == 1 + MAX_ATTEMPTS and "delete_all_records" in refused[0].detail


def test_doctor_playbook_fix_that_doesnt_fit_the_check_is_refused(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    drop(integ, "TXT", "_dmarc")
    failed = run_check(ctx, "email_dmarc")
    with pytest.raises(DoctorRefused):
        diagnose(ScriptedDoctor({"plain_explanation": "x", "fix_id": "restore_backup"}), ctx, failed)


def test_doctor_stops_after_three_attempts(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    integ.dns.hide.add((f"_dmarc.{DOMAIN}", "TXT"))  # fix can't help: record never "spreads"
    failed = run_check(ctx, "email_dmarc")
    result = repair(FixtureClaudeClient(), ctx, failed)
    assert not result.fixed and len(result.attempts) == MAX_ATTEMPTS
    assert [r.attempt for r in ctx.session.exec(select(CheckResult).where(CheckResult.check == "email_dmarc"))
            .all()] == [0, 1, 2, 3]


def test_certificate_retry_then_green(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    integ.http.broken_cert.add(DOMAIN)
    failed = run_check(ctx, "https")
    real_fetch = integ.http.fetch

    def heal_on_retry(url):  # the retry_certificate fix's request "issues" the certificate
        integ.http.broken_cert.discard(DOMAIN)
        return real_fetch(url)

    integ.http.fetch = heal_on_retry
    result = repair(FixtureClaudeClient(), ctx, failed)
    assert result.fixed and result.attempts[0]["fix_id"] == "retry_certificate"
