"""Session 10: production readiness (database settings, one process, row deletes, migrations)."""

import sqlite3

import pytest
from sqlmodel import Session, select

from app import singleton
from app.db import BUSY_TIMEOUT_MS, init_db, make_engine
from app.models import Business, Evidence, ReportShare, TestTicket


def test_sqlite_pragmas_on_every_connection(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/lw.db")
    for _ in range(2):  # a fresh pool connection each time
        with engine.connect() as c:
            assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert c.exec_driver_sql("PRAGMA busy_timeout").scalar() == BUSY_TIMEOUT_MS
            assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        engine.dispose()


def test_foreign_keys_enforced_in_memory_too():
    engine = make_engine("sqlite://")
    init_db(engine)
    with Session(engine) as s:
        s.add(Evidence(business_id=999, check="https", step="http_response"))
        with pytest.raises(Exception):
            s.commit()


def test_second_process_refused(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/lw.db"
    monkeypatch.setattr(singleton, "_held", None)
    assert singleton.acquire(url)
    held = singleton._held
    monkeypatch.setattr(singleton, "_held", None)  # pretend to be a second process
    with pytest.raises(singleton.SecondProcess):
        singleton.acquire(url)
    held.close()


def test_many_workers_refused(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(singleton.SecondProcess):
        singleton.acquire("sqlite://")


def test_admin_practice_delete_removes_proof_rows(client, engine, settings):
    """Bug fixed in S10: the demo-reset delete left Evidence / TestTicket / ReportShare rows behind."""
    with Session(engine) as s:
        b = Business(name="Gone", description="", subdomain="gone-shop", practice=True)
        s.add(b)
        s.commit()
        s.refresh(b)
        s.add(Evidence(business_id=b.id, check="https", step="http_response"))
        s.add(TestTicket(business_id=b.id, nonce="n-gone"))
        s.add(ReportShare(business_id=b.id, token_hash="h-gone"))
        s.commit()
        bid = b.id
    r = client.delete(f"/api/admin/practice-businesses/{bid}", headers={"X-Admin-Token": settings.admin_token.get_secret_value()})
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        for table in (Evidence, TestTicket, ReportShare):
            assert s.exec(select(table).where(table.business_id == bid)).first() is None


OLD_SCHEMA = """
CREATE TABLE business (id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, description VARCHAR NOT NULL,
  subdomain VARCHAR, domain VARCHAR, status VARCHAR NOT NULL, created_at DATETIME NOT NULL);
INSERT INTO business (id, name, description, subdomain, domain, status, created_at)
  VALUES (1, 'Meera''s Bakes', 'cakes', 'meera', NULL, 'draft', '2026-11-14 10:00:00');
INSERT INTO business (id, name, description, subdomain, domain, status, created_at)
  VALUES (2, 'Old Shop', 'pickles', 'oldshop', NULL, 'live', '2026-11-14 11:00:00');
CREATE TABLE auditevent (id INTEGER PRIMARY KEY, business_id INTEGER, actor VARCHAR NOT NULL, action VARCHAR NOT NULL,
  target VARCHAR NOT NULL, result VARCHAR NOT NULL, detail VARCHAR NOT NULL, created_at DATETIME NOT NULL);
INSERT INTO auditevent VALUES (1, 1, 'system', 'describe', 'business:1', 'ok', '', '2026-11-14 10:00:00');
"""


def test_pre_s9f_database_starts_and_keeps_rows(tmp_path):
    """A database from before accounts (no user/session tables, old business columns) upgrades in place."""
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript(OLD_SCHEMA)
    con.close()
    engine = make_engine(f"sqlite:///{path}")
    init_db(engine)
    init_db(engine)  # twice: idempotent
    with Session(engine) as s:
        rows = s.exec(select(Business).order_by(Business.id)).all()
        assert [b.name for b in rows] == ["Meera's Bakes", "Old Shop"]
        assert rows[0].practice is True and rows[1].status == "live"  # old rows become practice: the safe default
    with engine.connect() as c:
        tables = {r[0] for r in c.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"user", "sessions", "membership", "evidence"} <= tables
        assert c.exec_driver_sql("SELECT count(*) FROM auditevent").scalar() == 1


@pytest.mark.parametrize("host,code", [("app:8000", 200), ("app", 200), ("127.0.0.1:8000", 200),
                                        ("localhost", 200), ("launchwitness.com", 404), ("meera.localhost", 404),
                                        ("evil.example", 404)])
def test_internal_only_for_private_host_names(client, settings, host, code):
    r = client.get("/internal/tls-ask", params={"domain": settings.app_domain}, headers={"host": host})
    assert r.status_code == code


def test_plain_smtp_refused_for_real_host(make_settings):
    with pytest.raises(Exception):
        make_settings(smtp_security="plain", smtp_host="smtpout.secureserver.net")
    assert make_settings(smtp_security="plain", smtp_host="mailpit").smtp_security == "plain"


# ---------- Part B: backups ----------

def _db_with_rows(path, n):
    engine = make_engine(f"sqlite:///{path}")
    init_db(engine)
    with Session(engine) as s:
        for i in range(n):
            s.add(Business(name=f"Shop {i}", subdomain=f"shop-{i}"))
        s.commit()
    return engine


def test_backup_then_restore_gives_back_the_same_rows(tmp_path):
    from app import backup

    live = tmp_path / "live.db"
    engine = _db_with_rows(live, 3)
    with engine.connect() as c:  # the app is "running": an open WAL connection with recent writes
        c.exec_driver_sql("SELECT 1")
        snap = backup.create(str(live), str(tmp_path / "b.db"))
        assert snap["business"] == 3
    with Session(engine) as s:  # life goes on after the backup
        s.add(Business(name="After", subdomain="after"))
        s.commit()
    engine.dispose()
    assert backup.counts(str(live))["business"] == 4
    restored = backup.restore(str(tmp_path / "b.db"), str(live))
    assert restored == snap and restored["business"] == 3
    assert not (tmp_path / "live.db-wal").exists()  # an old WAL never survives a restore
    names = [b.name for b in Session(make_engine(f"sqlite:///{live}")).exec(select(Business)).all()]
    assert names == ["Shop 0", "Shop 1", "Shop 2"]


def test_backup_refuses_to_overwrite_and_restore_refuses_a_broken_file(tmp_path):
    from app import backup

    _db_with_rows(tmp_path / "live.db", 1).dispose()
    backup.create(str(tmp_path / "live.db"), str(tmp_path / "b.db"))
    with pytest.raises(SystemExit):
        backup.create(str(tmp_path / "live.db"), str(tmp_path / "b.db"))
    (tmp_path / "junk.db").write_bytes(b"not a database at all" * 100)
    with pytest.raises(Exception):
        backup.restore(str(tmp_path / "junk.db"), str(tmp_path / "live.db"))
    assert backup.counts(str(tmp_path / "live.db"))["business"] == 1  # untouched


# ---------- Part B: startup self-check ----------

def codes(settings):
    from app.selfcheck import warnings

    return {w.code for w in warnings(settings)}


def test_selfcheck_names_each_wrong_setting(make_settings):
    from datetime import date, timedelta

    bad = make_settings(use_fakes=False, claude_mode="fixture", admin_email="", dev_mode=True, allow_purchase=True,
                        admin_token="change-me",
                        server_ip="127.0.0.1", mailbox_expires_on=date.today() + timedelta(days=3))
    assert {"admin_email_unset", "admin_token_weak", "dev_mode_on", "claude_fixture_on_real_server",
            "mailbox_expiring", "server_ip_missing", "purchases_on"} <= codes(bad)
    good = make_settings(use_fakes=False, claude_mode="live", admin_email="team@example.org", dev_mode=False,
                         admin_token="x" * 32, server_ip="203.0.113.7", smtp_password="pw-for-test-only")
    assert codes(good) == set()
    assert "smtp_not_configured" in codes(make_settings(dev_mode=False, smtp_password=""))


def test_selfcheck_never_contains_a_secret(make_settings):
    from app.selfcheck import warnings

    s = make_settings(use_fakes=False, admin_token="short-tok", smtp_password="hunter2-not-real", allow_purchase=True)
    text = " ".join(w.text for w in warnings(s))
    assert "short-tok" not in text and "hunter2" not in text


def test_public_health_hides_admin_only_warnings(new_client, make_settings, engine, mailer, claude, integ):
    from datetime import date, timedelta

    from fastapi.testclient import TestClient

    from tests.test_s9_phase2_access import make_app

    app, s = make_app(make_settings, engine, mailer, claude, integ, dev_mode=False, admin_email="",
                      admin_token="t" * 20, mailbox_expires_on=date.today() + timedelta(days=2),
                      smtp_password="pw-for-test-only")
    with TestClient(app) as c:
        pub = c.get("/api/health").json()
        assert pub["warning_codes"] == ["mailbox_expiring"]  # harmless to anyone
        full = c.get("/api/health", headers={"X-Admin-Token": "t" * 20}).json()
        assert "admin_email_unset" in full["warning_codes"]


# ---------- Part B: fixture-mode real launches are held (fail closed) ----------

def test_fixture_mode_on_a_real_server_holds_real_launches(make_settings, engine, mailer, claude):
    from app.models import AuditEvent
    from tests.conftest import set_user, sign_in
    from tests.test_m3_launch import meera
    from tests.test_m4_report import real_plan, two_worlds_client

    c, server, _ = two_worlds_client(make_settings, engine, mailer, claude, claude_mode="fixture",
                                     admin_token="a" * 20)
    with c:
        sign_in(c, "meera@example.org")
        set_user(engine, "meera@example.org", status="approved")
        biz = meera(c)
        p = real_plan(c, biz)
        r = c.post(f"/api/plans/{p['id']}/approve", json={"approved_by": "Meera"})
        assert r.status_code == 409 and "Our team looks at every new shop" in r.json()["detail"]
        with Session(engine) as s:
            b = s.get(Business, biz["id"])
            assert b.review == "held" and b.status != "live"
            assert s.exec(select(AuditEvent).where(AuditEvent.action == "policy_check",
                                                   AuditEvent.result == "held")).first()
        assert server.godaddy.zones.get("localhost", []) == [] or all(
            r_["name"] != "meera" for r_ in server.godaddy.zones.get("localhost", []))  # nothing was written
        # The team looks and clears it: now the launch goes through.
        assert c.post(f"/api/admin/businesses/{biz['id']}/clear-review",
                      headers={"X-Admin-Token": "a" * 20}).status_code == 200
        assert c.post(f"/api/plans/{p['id']}/approve", json={"approved_by": "Meera"}).status_code == 200


def test_fixture_mode_on_a_practice_server_does_not_hold(client, engine):
    from tests.test_m3_launch import approve, meera, plan

    biz = meera(client)
    approve(client, plan(client, biz))  # practice server + fixture: the normal path
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).review == ""
