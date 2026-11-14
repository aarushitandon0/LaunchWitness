"""M3 acceptance: Namer, Planner, approval, Executor (sandbox + full) against the fake world."""

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.agents.executor import Ctx, DomainRefused, StepFailed, assert_can_write, run_plan, write_change
from app.agents.namer import clean_names, rank
from app.godaddy.availability import Quote
from app.models import Approval, AuditEvent, Business, DnsBackup, Plan

SELLERS = Path(__file__).parent / "fixtures" / "sellers"


def meera(client, subdomain="meera") -> dict:
    s = json.loads((SELLERS / "meera_cakes.json").read_text(encoding="utf-8"))
    biz = client.post("/api/businesses", data={"description": s["description"], "price_list": s["price_list"]}).json()
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": biz["profile"], "subdomain": subdomain})
    assert r.status_code == 200
    return r.json()


def plan(client, biz, mode="sandbox", domain=None) -> dict:
    r = client.post(f"/api/businesses/{biz['id']}/plans", json={"mode": mode, "domain": domain})
    assert r.status_code == 201, r.text
    return r.json()


def approve(client, p) -> dict:
    r = client.post(f"/api/plans/{p['id']}/approve", json={"approved_by": "Meera"})
    assert r.status_code == 200, r.text
    return client.get(f"/api/plans/{p['id']}").json()


def events(engine, action=None):
    with Session(engine) as s:
        q = select(AuditEvent)
        if action:
            q = q.where(AuditEvent.action == action)
        return s.exec(q).all()


# ---------- Namer ----------

def test_names_are_checked_and_best_three_returned(client, claude, integ):
    biz = meera(client)
    integ.availability.prices = {"meerascakes.in": 8.99, "meerabakes.in": 7.99, "meeracakes.shop": 2.99,
                                 "bakedbymeera.in": 8.99}
    integ.availability.taken = {"meerahomecakes.in"} | {n for n in json.loads(
        Path("tests/fixtures/claude/namer_meera_cakes.json").read_text())["names"] if n not in integ.availability.prices}
    out = client.get(f"/api/businesses/{biz['id']}/names").json()
    assert claude.calls[-1] == "namer_meera_cakes"
    assert out == [{"domain": "meeracakes.shop", "price_usd": 2.99}, {"domain": "meerabakes.in", "price_usd": 7.99},
                   {"domain": "meerascakes.in", "price_usd": 8.99}]
    assert len(integ.availability.calls[0]) == 10


def test_clean_names_drops_junk():
    assert clean_names(["https://www.MeerasCakes.in/", "meeras cakes.in", "x.xyz", "meerascakes.in", 3, "ok-name.com"]) == [
        "meerascakes.in", "ok-name.com"]


def test_rank_prefers_cheap_then_short():
    qs = [Quote("longername.in", True, 5.0), Quote("short.in", True, 5.0), Quote("cheap.shop", True, 1.0),
          Quote("gone.in", False), Quote("x.in", True, 9.0)]
    assert [q.domain for q in rank(qs)] == ["cheap.shop", "short.in", "longername.in"]


# ---------- Planner ----------

def test_sandbox_plan_has_steps_diff_and_zero_cost(client, integ, settings):
    integ.godaddy.zones["localhost"] = [{"type": "A", "name": "meera", "data": "10.0.0.9", "ttl": 600}]
    p = plan(client, meera(client))
    assert p["mode"] == "sandbox" and p["total_cost_usd"] == 0 and p["status"] == "draft"
    assert p["site_host"] == "meera.localhost"
    assert [s["kind"] for s in p["steps"]] == ["backup_dns", "point_site", "use_app_mailbox", "wait_dns", "go_live"]
    (ch,) = p["changes"]
    assert (ch["type"], ch["name"], ch["before_text"], ch["after_text"]) == ("A", "meera", ["10.0.0.9"], [settings.server_ip])
    assert integ.godaddy.writes() == []  # planning never writes


def test_full_plan_lists_every_setting_and_cost(client, integ):
    integ.availability.prices = {"meerascakes.in": 8.99}
    p = plan(client, meera(client), "full", "meerascakes.in")
    assert p["total_cost_usd"] == 8.99
    assert p["steps"][0]["title"] == "Buy meerascakes.in ($8.99 for the first year)"
    assert [(c["type"], c["name"]) for c in p["changes"]] == [
        ("A", "@"), ("MX", "@"), ("TXT", "@"), ("TXT", "titan1._domainkey"), ("TXT", "_dmarc")]
    assert all(c["say"] and "MX" not in c["say"] for c in p["changes"])  # plain words for the seller


def test_full_plan_keeps_other_txt_records(client, integ):
    integ.godaddy.owned.add("meerascakes.in")
    integ.godaddy.zones["meerascakes.in"] = [{"type": "TXT", "name": "@", "data": "google-site-verification=abc"},
                                             {"type": "TXT", "name": "@", "data": "v=spf1 -all"}]
    p = plan(client, meera(client), "full", "meerascakes.in")
    txt = next(c for c in p["changes"] if (c["type"], c["name"]) == ("TXT", "@"))
    assert txt["after_text"] == ["google-site-verification=abc", "v=spf1 include:spf.titan.email ~all"]
    assert p["total_cost_usd"] == 0 and p["steps"][0]["title"].startswith("Use meerascakes.in")


@pytest.mark.parametrize("domain,msg", [("not a domain", "doesn't look like"), ("taken.in", "no longer available"),
                                        ("localhost", "doesn't look like")])
def test_full_plan_rejects_bad_domains(client, integ, domain, msg):
    r = client.post(f"/api/businesses/{meera(client)['id']}/plans", json={"mode": "full", "domain": domain})
    assert r.status_code == 422 and msg in r.json()["detail"]


# ---------- AC: sandbox launch end to end (fakes) ----------

def test_sandbox_launch_end_to_end(client, integ, engine, settings):
    biz = meera(client)
    p = approve(client, plan(client, biz))
    assert p["status"] == "done", p["steps"]
    assert all(s["status"] == "done" for s in p["steps"])
    assert p["site_url"] == "http://meera.localhost/"
    assert integ.godaddy.zones["localhost"] == [{"type": "A", "name": "meera", "data": settings.server_ip, "ttl": 600}]
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).status == "live"
        assert s.exec(select(Approval).where(Approval.action == "launch")).one().approved_by == "Meera"
    step_events = [e for e in events(engine) if e.action.startswith("step_")]
    assert [e.action for e in step_events] == ["step_backup_dns", "step_point_site", "step_use_app_mailbox",
                                                "step_wait_dns", "step_go_live"]
    assert all(e.result == "ok" for e in step_events)
    # The live site and tls-ask both know the host now.
    assert "Meera" in client.get("/", headers={"host": "meera.localhost"}).text
    assert client.get("/internal/tls-ask", params={"domain": "meera.localhost"}).status_code == 200


def test_sandbox_live_site_with_https_needs_real_infra():
    pytest.skip("PENDING REAL INFRA: live HTTPS at <sub>.APP_DOMAIN needs the VPS + Caddy (see PROGRESS.md)")


# ---------- AC: DNS backup before any DNS write ----------

def test_backup_is_taken_before_first_dns_write(client, integ, engine):
    integ.godaddy.zones["localhost"] = [{"type": "TXT", "name": "@", "data": "keep me"}]
    approve(client, plan(client, meera(client)))
    calls = integ.godaddy.calls
    first_write = next(i for i, c in enumerate(calls) if c[0] in ("set_records", "delete_records"))
    backup_read = max(i for i, c in enumerate(calls[:first_write]) if c[0] == "get_records")
    assert backup_read < first_write
    with Session(engine) as s:
        backup = s.exec(select(DnsBackup)).one()
        assert json.loads(backup.records_json) == [{"type": "TXT", "name": "@", "data": "keep me"}]
        write_ev = s.exec(select(AuditEvent).where(AuditEvent.action == "dns_write")).first()
        backup_ev = s.exec(select(AuditEvent).where(AuditEvent.action == "step_backup_dns")).one()
        assert backup.created_at <= write_ev.created_at and backup_ev.id < write_ev.id


def test_write_without_backup_is_refused(client, integ, engine, settings):
    biz = meera(client)
    p = plan(client, biz)
    with Session(engine) as s:
        pl, b = s.get(Plan, p["id"]), s.get(Business, biz["id"])
        ctx = Ctx(s, settings, integ, pl, b)
        with pytest.raises(StepFailed, match="couldn't save a copy"):
            write_change(ctx, p["changes"][0])
    assert integ.godaddy.writes() == []


def test_failed_backup_means_no_writes(client, integ):
    biz = meera(client)
    p = plan(client, biz)
    integ.godaddy.fail_next["get_records"] = 1  # the backup step's read fails
    p = approve(client, p)
    assert p["status"] == "failed" and p["steps"][0]["status"] == "failed"
    assert integ.godaddy.writes() == []


# ---------- AC: refuses domains not in DB ----------

def test_full_launch_refuses_domain_no_longer_in_db(client, integ, engine, settings):
    integ.godaddy.owned.add("meerascakes.in")
    biz = meera(client)
    p = plan(client, biz, "full", "meerascakes.in")
    client.post(f"/api/plans/{p['id']}/approve", json={})  # runs; fine
    # Fresh plan for a second launch after the domain was removed from this business in the DB.
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.domain = None
        s.add(b)
        s.commit()
    integ.godaddy.calls.clear()
    with Session(engine) as s:
        pl = s.get(Plan, p["id"])
        pl.status, pl.steps_json = "approved", json.dumps(
            [{**st, "status": "pending"} for st in json.loads(pl.steps_json)])
        s.add(pl)
        s.commit()
    assert run_plan(engine, settings, integ, p["id"]) == "failed"
    assert integ.godaddy.writes() == []
    refused = events(engine, "dns_write")
    assert any(e.result == "refused" and "meerascakes.in" in e.target for e in refused)
    final = client.get(f"/api/plans/{p['id']}").json()
    failed = next(s for s in final["steps"] if s["status"] == "failed")
    assert failed["message"].startswith("Stopped: this launch may only change settings for meerascakes.in")


@pytest.mark.parametrize("zone,name", [("localhost", "@"), ("localhost", "other"), ("evil.in", "@"),
                                       ("meerascakes.in", "@")])
def test_guard_refuses_anything_but_own_subdomain(client, integ, engine, settings, zone, name):
    biz = meera(client)
    p = plan(client, biz)
    with Session(engine) as s:
        ctx = Ctx(s, settings, integ, s.get(Plan, p["id"]), s.get(Business, biz["id"]))
        with pytest.raises(DomainRefused):
            assert_can_write(ctx, zone, name)
        assert_can_write(ctx, "localhost", "meera")  # its own label is fine


def test_sandbox_refuses_if_subdomain_changed_after_planning(client, integ, engine):
    biz = meera(client)
    p = plan(client, biz)
    client.put(f"/api/businesses/{biz['id']}", json={"profile": biz["profile"], "subdomain": "meera2"})
    p = approve(client, p)
    assert p["status"] == "failed"
    assert integ.godaddy.writes() == []


def test_plan_for_another_business_domain_is_rejected(client, integ, engine):
    integ.godaddy.owned.add("meerascakes.in")
    a = meera(client)
    approve(client, plan(client, a, "full", "meerascakes.in"))
    b = meera(client, "meera-two")
    r = client.post(f"/api/businesses/{b['id']}/plans", json={"mode": "full", "domain": "meerascakes.in"})
    assert r.status_code == 422 and "another business" in r.json()["detail"]


# ---------- AC: full mode stops at purchase when ALLOW_PURCHASE=false ----------

def test_full_mode_blocked_at_purchase_by_default(client, integ, engine, settings):
    assert settings.allow_purchase is False
    integ.availability.prices = {"meerascakes.in": 8.99}
    p = approve(client, plan(client, meera(client), "full", "meerascakes.in"))
    assert p["status"] == "blocked"
    first = p["steps"][0]
    assert first["kind"] == "get_domain" and first["status"] == "blocked"
    assert "Buying is switched off on this server, so nothing was bought" in first["message"]
    assert all(s["status"] == "pending" for s in p["steps"][1:])
    assert integ.godaddy.writes() == [] and not any(c[0] == "purchase_domain" for c in integ.godaddy.calls)
    assert any(e.result == "blocked" for e in events(engine, "authorize_buy_domain"))
    with Session(engine) as s:
        assert s.exec(select(DnsBackup)).all() == []


def test_owner_buys_manually_then_resume_adopts_and_finishes(client, integ, engine, settings):
    integ.availability.prices = {"meerascakes.in": 8.99}
    p = approve(client, plan(client, meera(client), "full", "meerascakes.in"))
    integ.godaddy.owned.add("meerascakes.in")  # bought on godaddy.com
    assert client.post(f"/api/plans/{p['id']}/resume").status_code == 200
    p = client.get(f"/api/plans/{p['id']}").json()
    assert p["status"] == "done", p["steps"]
    assert p["steps"][0]["message"].startswith("meerascakes.in is in your GoDaddy account")
    zone = {(r["type"], r["name"]): r for r in integ.godaddy.zones["meerascakes.in"]}
    assert zone[("A", "@")]["data"] == settings.server_ip
    assert zone[("TXT", "titan1._domainkey")]["data"].startswith("v=DKIM1; k=rsa; p=FAKE")
    assert zone[("TXT", "_dmarc")]["data"].startswith("v=DMARC1")
    assert ("create", "orders@meerascakes.in") in integ.mailbox.calls
    assert not any(c[0] == "purchase_domain" for c in integ.godaddy.calls)


def test_fake_purchase_when_enabled_uses_and_consumes_approval(make_settings, engine, mailer, claude, integ):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.db import get_session
    from app.integrations import get_integrations
    from app.mail.smtp import get_mailer
    from app.main import create_app
    from app.routers.businesses import get_claude

    settings = make_settings(allow_purchase=True, max_spend_usd=10)
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides.update({get_settings: lambda: settings, get_session: _session,
                                     get_mailer: lambda: mailer, get_claude: lambda: claude,
                                     get_integrations: lambda: integ})
    integ.availability.prices = {"meerascakes.in": 8.99}
    with TestClient(app) as c:
        p = approve(c, plan(c, meera(c), "full", "meerascakes.in"))
    assert p["status"] == "done"
    assert ("purchase_domain", "meerascakes.in", 8.99) in integ.godaddy.calls
    with Session(engine) as s:
        assert s.exec(select(Approval).where(Approval.action == "buy_domain")).one().used_at is not None


# ---------- Mailbox step ----------

def full_owned(client, integ):
    integ.godaddy.owned.add("meerascakes.in")
    return plan(client, meera(client), "full", "meerascakes.in")


def test_mailbox_create_is_retried(client, integ, engine):
    integ.mailbox.fail_creates = 2
    p = approve(client, full_owned(client, integ))
    assert p["status"] == "done"
    assert [c[0] for c in integ.mailbox.calls].count("create") == 3
    assert [e.result for e in events(engine, "mailbox_create")] == ["retry", "retry"]


def test_mailbox_create_gives_up_after_three_then_resume(client, integ):
    integ.mailbox.fail_creates = 3
    p = approve(client, full_owned(client, integ))
    step = next(s for s in p["steps"] if s["kind"] == "setup_mailbox")
    assert p["status"] == "failed" and "email service is busy" in step["message"]
    assert client.post(f"/api/plans/{p['id']}/resume").status_code == 200
    assert client.get(f"/api/plans/{p['id']}").json()["status"] == "done"


def test_mailbox_polls_until_ready(client, integ):
    integ.mailbox.ready_after_polls = 5
    assert approve(client, full_owned(client, integ))["status"] == "done"


def test_mailbox_not_ready_in_time_fails_softly(client, integ):
    integ.mailbox.ready_after_polls = 100
    p = approve(client, full_owned(client, integ))
    step = next(s for s in p["steps"] if s["kind"] == "setup_mailbox")
    assert step["status"] == "failed" and "still being set up" in step["message"]


def test_existing_mailbox_is_adopted(client, integ):
    integ.mailbox.boxes["orders@meerascakes.in"] = 10**6
    p = approve(client, full_owned(client, integ))
    assert p["status"] == "done" and not any(c[0] == "create" for c in integ.mailbox.calls)


# ---------- DNS wait, approval rules ----------

def test_dns_not_spread_fails_softly_and_resume_continues(client, integ):
    integ.dns.hide.add(("meera.localhost", "A"))
    p = approve(client, plan(client, meera(client)))
    wait = next(s for s in p["steps"] if s["kind"] == "wait_dns")
    assert p["status"] == "failed" and "hasn't picked up" in wait["message"]
    assert [s["status"] for s in p["steps"][:3]] == ["done", "done", "done"]
    integ.dns.hide.clear()
    client.post(f"/api/plans/{p['id']}/resume")
    p = client.get(f"/api/plans/{p['id']}").json()
    assert p["status"] == "done"
    assert len([c for c in integ.godaddy.writes()]) == 1  # resume did not redo finished writes


def test_cannot_approve_twice_or_run_without_approval(client, integ, engine, settings):
    p = plan(client, meera(client))
    assert run_plan(engine, settings, integ, p["id"]) == "draft"
    assert integ.godaddy.writes() == []
    assert any(e.result == "refused" for e in events(engine, "run_plan"))
    approve(client, p)
    assert client.post(f"/api/plans/{p['id']}/approve", json={}).status_code == 409


def test_price_change_before_approval_is_caught(client, integ):
    integ.availability.prices = {"meerascakes.in": 8.99}
    p = plan(client, meera(client), "full", "meerascakes.in")
    integ.availability.prices["meerascakes.in"] = 12.99
    r = client.post(f"/api/plans/{p['id']}/approve", json={})
    assert r.status_code == 409 and "price" in r.json()["detail"]


def test_only_stopped_plans_resume(client):
    p = approve(client, plan(client, meera(client)))
    assert client.post(f"/api/plans/{p['id']}/resume").status_code == 409


def test_practice_mode_flag(client):
    assert client.get("/api/practice-mode").json() == {"practice": True}
