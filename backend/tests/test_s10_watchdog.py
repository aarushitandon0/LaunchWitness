"""Session 10 Part C: Renewals, zone hygiene for our own shop zone, and the dangling-CNAME finding."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlmodel import Session, select

from app import renewals
from app.checks.dns_resolver import FakeDnsResolver
from app.godaddy.client import FakeGoDaddyClient
from app.integrations import fake_integrations
from app.models import AuditEvent, Business, TeamAlert, ZoneFinding
from app.monitor.scheduler import Monitor
from app.routers.proof import address_results
from app.zone_hygiene import NoLongerTrue, approve, dismiss, scan
from tests.test_m3_launch import approve as approve_plan
from tests.test_m3_launch import meera, plan

# ---------- Renewals card ----------

def test_live_shop_report_has_a_renewals_card(client, make_settings):
    biz = meera(client)
    approve_plan(client, plan(client, biz))
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    items = {r["what"]: r for r in rep["renewals"]}
    assert set(items) == {"certificate", "domain", "mailbox"}
    assert items["certificate"]["who"] == "automatic"
    assert items["domain"]["who"] == "team" and items["domain"]["days_left"] is not None  # the app domain
    assert items["mailbox"]["who"] == "team"
    assert rep["practice"] is True  # pretend dates are labelled by the report's practice flag


def test_renewals_card_needs_a_live_shop(client):
    biz = meera(client)
    assert client.get(f"/api/businesses/{biz['id']}/report").json()["renewals"] is None


@pytest.mark.parametrize("days,state", [(None, "unknown"), (-1, "lapsed"), (0, "urgent"), (7, "urgent"),
                                        (8, "soon"), (30, "soon"), (31, "ok")])
def test_renewal_states(days, state):
    assert renewals.state(days) == state


def test_my_shops_shows_the_nearest_renewal(client, make_settings):
    biz = meera(client)
    approve_plan(client, plan(client, biz))
    shops = client.get("/api/businesses").json()
    assert shops[0]["renewal"] is None  # a year away: nothing to say
    soon = renewals.card(make_settings(mailbox_expires_on=date.today() + timedelta(days=5)), "sandbox", "x", {})
    assert renewals.nearest(soon)["what"] == "mailbox"


# ---------- Team renewals: the app domain and the team mailbox, 30 / 7 / 1, never twice ----------

def team_monitor(engine, settings):
    team = fake_integrations(settings)
    return Monitor(engine, settings, lambda b: team, None, team=team), team


@pytest.mark.parametrize("kind", ["app_domain_expiry", "mailbox_expiry"])
def test_team_alert_at_each_threshold_once(engine, make_settings, kind):
    today = date(2026, 11, 16)
    s = make_settings(admin_email="team@example.org", mailbox_expires_on=None)
    mon, team = team_monitor(engine, s)

    def at(days: int) -> list[str]:
        if kind == "app_domain_expiry":
            team.godaddy.expires[s.app_domain] = datetime.now(UTC) + timedelta(days=days, hours=12)
        else:
            mon.settings = make_settings(admin_email="team@example.org", mailbox_expires_on=today + timedelta(days=days))
        return [k for k in mon.team_renewals(today=today) if k.startswith(kind)]

    assert at(60) == []
    assert at(30) == [f"{kind}:30d"]
    assert at(29) == []  # same threshold: no repeat
    assert at(7) == [f"{kind}:7d"]
    assert at(6) == []
    assert at(1) == [f"{kind}:1d"]
    assert at(1) == []
    sent = [m for m in team.mailer.sent if m["to"] == "team@example.org"]
    assert len(sent) == 3 and all("won't do it" in m["body"] for m in sent)  # never renews or pays
    assert at(365) == []  # renewed: old alerts close ...
    assert at(30) == [f"{kind}:30d"]  # ... so the next cycle warns again


def test_team_alert_jumps_straight_to_the_nearest_threshold(engine, make_settings):
    s = make_settings(admin_email="team@example.org", mailbox_expires_on=date(2026, 11, 20))
    mon, team = team_monitor(engine, s)
    assert mon.team_renewals(today=date(2026, 11, 16)) == ["mailbox_expiry:7d"]  # 4 days: one email, not two
    assert mon.team_renewals(today=date(2026, 11, 16)) == []


def test_team_alert_without_admin_email_is_logged_not_sent(engine, make_settings):
    s = make_settings(admin_email="", mailbox_expires_on=date(2026, 11, 20))
    mon, team = team_monitor(engine, s)
    assert mon.team_renewals(today=date(2026, 11, 16)) == []
    with Session(engine) as db:
        assert db.exec(select(TeamAlert)).first() is None
        assert db.exec(select(AuditEvent).where(AuditEvent.action == "alert_mailbox_expiry",
                                                AuditEvent.result == "skipped")).first()


def test_certificate_isnt_alerted_at_30_days(engine, make_settings):
    """Caddy renews certificates ~30 days ahead by itself: only 7 and 1 days are worth an email."""
    assert renewals.crossed(30, renewals.CERT_THRESHOLDS) == []
    assert renewals.crossed(7, renewals.CERT_THRESHOLDS) == [7]
    assert renewals.crossed(30, renewals.THRESHOLDS) == [30]


# ---------- Zone hygiene ----------

def zone_world(engine, settings):
    gd = FakeGoDaddyClient(owned={settings.app_domain}, app_domain=settings.app_domain)
    ip, z = settings.server_ip, settings.app_domain
    gd.zones[z] = [
        {"type": "A", "name": "@", "data": "198.51.100.1"},  # the app: never looked at
        {"type": "A", "name": "www", "data": "198.51.100.1"},  # never looked at
        {"type": "MX", "name": "@", "data": "mail.example", "priority": 10},
        {"type": "TXT", "name": "@", "data": "v=spf1 -all"},
        {"type": "CNAME", "name": "shop-cname", "data": "elsewhere.example"},
        {"type": "A", "name": "meera", "data": ip},  # live shop, right place
        {"type": "A", "name": "oldshop", "data": ip},  # nobody has this name: dangling
        {"type": "A", "name": "drafty", "data": ip},  # a shop that isn't live: dangling
        {"type": "A", "name": "drift", "data": "203.0.113.99"},  # live shop pointing elsewhere
    ]
    with Session(engine) as s:
        for name, status in (("meera", "live"), ("drafty", "draft"), ("drift", "live"), ("nore", "live")):
            s.add(Business(name=name.title(), subdomain=name, status=status, practice=False))
        s.commit()
    return gd


def test_zone_scan_finds_dangling_missing_and_wrong_target_and_changes_nothing(engine, make_settings):
    s = make_settings(use_fakes=False, server_ip="203.0.113.7")
    gd = zone_world(engine, s)
    for rec in gd.zones[s.app_domain]:
        if rec["name"] == "meera":
            rec["data"] = s.server_ip
    found = {(f.kind, f.name): f for f in scan(engine, s, gd)}
    assert set(found) == {("dangling", "oldshop"), ("dangling", "drafty"), ("wrong_target", "drift"),
                          ("missing", "nore"), ("wrong_target", "meera")} - {("wrong_target", "meera")}
    assert gd.writes() == []  # a scan only reads
    assert found[("dangling", "oldshop")].fix == "delete" and found[("missing", "nore")].fix == "set"
    assert len(scan(engine, s, gd)) == 4  # scanning again doesn't duplicate
    with Session(engine) as db:
        assert len(db.exec(select(AuditEvent).where(AuditEvent.action == "zone_finding")).all()) == 4


def test_zone_fixes_need_approval_and_touch_only_that_shop_record(engine, make_settings):
    s = make_settings(use_fakes=False, server_ip="127.0.0.1")
    gd = zone_world(engine, s)
    found = {(f.kind, f.name): f for f in scan(engine, s, gd)}
    before = {(r["type"], r["name"]) for r in gd.zones[s.app_domain]}

    approve(engine, s, gd, found[("dangling", "oldshop")].id, by="team@example.org")
    assert gd.writes() == [("delete_records", s.app_domain, "A", "oldshop")]
    approve(engine, s, gd, found[("missing", "nore")].id, by="team@example.org")
    approve(engine, s, gd, found[("wrong_target", "drift")].id, by="team@example.org")
    after = {(r["type"], r["name"]): r for r in gd.zones[s.app_domain]}
    assert after[("A", "nore")]["data"] == after[("A", "drift")]["data"] == s.server_ip
    assert before - {("A", "oldshop")} <= set(after)  # @, www, MX, TXT, CNAME untouched
    assert all(w[2] == "A" and w[3] in ("oldshop", "nore", "drift") for w in gd.writes())

    with pytest.raises(LookupError):  # a decided finding can't be approved again
        approve(engine, s, gd, found[("dangling", "oldshop")].id, by="x")
    dismiss(engine, found[("dangling", "drafty")].id, by="team@example.org")
    with Session(engine) as db:
        assert db.get(ZoneFinding, found[("dangling", "drafty")].id).status == "dismissed"
        fixes = db.exec(select(AuditEvent).where(AuditEvent.action == "zone_fix")).all()
        assert len(fixes) == 3 and all("approved by team@example.org" in e.detail for e in fixes)
    assert ("A", "drafty") in after  # dismissed: left alone


def test_zone_fix_refused_when_no_longer_true(engine, make_settings):
    s = make_settings(use_fakes=False, server_ip="127.0.0.1")
    gd = zone_world(engine, s)
    f = next(x for x in scan(engine, s, gd) if x.name == "oldshop")
    gd.zones[s.app_domain] = [r for r in gd.zones[s.app_domain] if r["name"] != "oldshop"]  # someone fixed it by hand
    with pytest.raises(NoLongerTrue):
        approve(engine, s, gd, f.id, by="x")
    assert gd.writes() == []


def test_zone_routes_are_admin_only(client, new_client, settings):
    assert client.get("/api/admin/zone-findings").status_code in (401, 403)
    assert client.post("/api/admin/zone-check").status_code in (401, 403)
    admin = {"X-Admin-Token": settings.admin_token.get_secret_value()}
    assert client.post("/api/admin/zone-check", headers=admin).status_code == 200


# ---------- Check any address: dangling CNAME (read-only, only the typed names) ----------

class CountingDns(FakeDnsResolver):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked: list[tuple[str, str]] = []

    def resolve(self, name, rtype):
        self.asked.append((name, rtype))
        return super().resolve(name, rtype)


class NoWeb:
    def get(self, url):  # pragma: no cover - not reached: the address has no A record
        raise AssertionError("no web fetch expected")


def test_dangling_cname_is_reported():
    dns = CountingDns({("www.shop.example", "CNAME"): ["shop-old.someservice.example."]})
    out = address_results("www.shop.example", dns, NoWeb())
    hit = [r for r in out if r["check"] == "dangling_cname"]
    assert len(hit) == 1 and hit[0]["ok"] is False
    assert "Anyone who claims that service could serve pages on this address" in hit[0]["plain"]
    cname_lookups = {n for n, t in dns.asked if t == "CNAME"}
    assert cname_lookups == {"shop.example", "www.shop.example"}  # only the typed name and its www


def test_cname_to_a_name_that_exists_is_fine():
    dns = CountingDns({("www.shop.example", "CNAME"): ["host.example."], ("host.example", "A"): ["198.51.100.4"]})
    assert not [r for r in address_results("shop.example", dns, NoWeb()) if r["check"] == "dangling_cname"]
