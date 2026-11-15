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
