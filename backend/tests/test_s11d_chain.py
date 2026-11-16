"""Session 11d: the tamper-evident proof log (per-shop hash chain over Evidence rows)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlmodel import Session, delete, select

from app import chain, proof
from app.db import init_db, make_engine
from app.models import AuditEvent, Business, Evidence
from app.monitor.scheduler import Monitor
from app.routers import proof as proof_routes
from tests.test_m3_launch import approve, meera, plan


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    proof_routes._verify_hits.clear()
    yield
    proof_routes._verify_hits.clear()


def launched(client, subdomain="meera") -> dict:
    biz = meera(client, subdomain)
    approve(client, plan(client, biz))
    return biz


def share_path(client, biz) -> str:
    return "/r/" + client.post(f"/api/businesses/{biz['id']}/share").json()["url"].rsplit("/r/", 1)[1]


def state(engine, business_id: int) -> dict:
    with Session(engine) as s:
        return chain.verify(s, business_id)


def ids(engine, business_id: int) -> list[int]:
    with Session(engine) as s:
        return list(s.exec(select(Evidence.id).where(Evidence.business_id == business_id).order_by(Evidence.id)).all())


def raw(engine, sql: str, **params) -> None:
    """Someone with the database file, going behind the app's back."""
    with engine.begin() as conn:
        conn.execute(text(sql), params)


# ---------- normal life is always intact ----------

def test_launch_checks_and_monitoring_keep_the_chain_intact(client, engine, settings, integ, claude):
    biz = launched(client)
    first = state(engine, biz["id"])
    assert first["intact"] is True and first["rows"] >= 5 and len(first["head"]) == 64
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 202  # "check again now"
    mon = Monitor(engine, settings, lambda _b: integ, claude)
    for kind in ("quick", "daily"):
        mon.check_business(biz["id"], kind)
    after = state(engine, biz["id"])
    assert after["intact"] is True and after["rows"] > first["rows"] and after["head"] != first["head"]
    with Session(engine) as s:
        rows = s.exec(select(Evidence).where(Evidence.business_id == biz["id"]).order_by(Evidence.id)).all()
        assert rows[0].prev_hash == chain.genesis(biz["id"])
        assert all(b.prev_hash == a.hash for a, b in zip(rows, rows[1:], strict=False))


def test_each_shop_has_its_own_chain(client, new_client, engine):
    a, b = launched(client), launched(new_client(), "meera2")
    assert chain.genesis(a["id"]) != chain.genesis(b["id"])
    sa, sb = state(engine, a["id"]), state(engine, b["id"])
    assert sa["intact"] and sb["intact"] and sa["head"] != sb["head"]
    raw(engine, "UPDATE evidence SET answer = 'x' WHERE id = :i", i=ids(engine, b["id"])[0])
    assert state(engine, a["id"]) == sa and state(engine, b["id"]) == {"intact": False, "altered_at": 1}


def test_the_hash_covers_every_stored_field():
    stored = set(Evidence.model_fields) - {"id", "prev_hash", "hash"}
    assert set(chain.FIELDS) == stored  # a new Evidence column must join the hash


def test_canonical_json_is_stable_and_times_are_utc():
    at = datetime(2026, 11, 16, 9, 30, 0, 123456, tzinfo=UTC)
    row = Evidence(business_id=7, run_id=None, check="https", step="http_response", at=at, answer="é ok")
    text_ = chain.canonical(row)
    assert text_ == ('{"answer":"\\u00e9 ok","at":"2026-11-16T09:30:00.123456Z","business_id":7,"cert_not_after":null,'
                     '"check":"https","message_id":"","nonce":"","practice":false,"run_id":null,"server":"",'
                     '"source":"","status_code":null,"step":"http_response"}')
    row.at = at.replace(tzinfo=None)  # as SQLite hands it back
    assert chain.canonical(row) == text_
    row.at = at.astimezone(timezone(timedelta(hours=5, minutes=30)))  # the same moment in IST
    assert chain.canonical(row) == text_


def test_a_time_in_another_zone_still_verifies(client, engine):
    biz = launched(client)
    ist = timezone(timedelta(hours=5, minutes=30))
    with Session(engine) as s:
        proof.add(s, business=s.get(Business, biz["id"]), run_id=None, check="https", step="http_response",
                  practice=True, cert_not_after=datetime(2027, 1, 1, 12, 0, tzinfo=ist))
    assert state(engine, biz["id"])["intact"] is True


# ---------- tampering is found, at the right place ----------

EDITS = {"business_id": None, "run_id": 987654, "check": "'forged_check'", "step": "'forged_step'",
         "at": "'2020-01-01 00:00:00.000000'", "source": "'elsewhere'", "server": "'10.0.0.1'",
         "message_id": "'<forged@x>'", "nonce": "'feedfacefeedface'", "status_code": 201,
         "cert_not_after": "'2031-01-01 00:00:00.000000'", "answer": "'forged'", "practice": 0,
         "prev_hash": "'" + "0" * 64 + "'", "hash": "'" + "f" * 64 + "'"}


@pytest.mark.parametrize("field", [f for f in EDITS if f != "business_id"])
def test_editing_any_field_of_any_row_is_detected(client, engine, field):
    biz = launched(client)
    rows = ids(engine, biz["id"])
    for position in (1, len(rows) // 2 + 1, len(rows)):
        target = rows[position - 1]
        with Session(engine) as s:
            before = dict(s.connection().execute(text("SELECT * FROM evidence WHERE id = :i"), {"i": target}).mappings().one())
        raw(engine, f'UPDATE evidence SET "{field}" = {EDITS[field]} WHERE id = :i', i=target)
        assert state(engine, biz["id"]) == {"intact": False, "altered_at": position}, (field, position)
        raw(engine, f'UPDATE evidence SET "{field}" = :v WHERE id = :i', v=before[field], i=target)  # put it back
        assert state(engine, biz["id"])["intact"] is True


def test_moving_a_row_to_another_shop_is_detected(client, new_client, engine):
    a, b = launched(client), launched(new_client(), "meera2")
    rows_a, n_b = ids(engine, a["id"]), len(ids(engine, b["id"]))
    raw(engine, "UPDATE evidence SET business_id = :b WHERE id = :i", b=b["id"], i=rows_a[2])
    assert state(engine, a["id"]) == {"intact": False, "altered_at": 3}  # a's chain has a hole
    broken_b = state(engine, b["id"])
    assert broken_b["intact"] is False and 1 <= broken_b["altered_at"] <= n_b + 1  # and b's a stranger


def test_reordering_rows_is_detected(client, engine):
    biz = launched(client)
    rows = ids(engine, biz["id"])
    x, y = rows[2], rows[3]
    raw(engine, "UPDATE evidence SET id = -1 WHERE id = :x", x=x)
    raw(engine, "UPDATE evidence SET id = :x WHERE id = :y", x=x, y=y)
    raw(engine, "UPDATE evidence SET id = :y WHERE id = -1", y=y)
    assert state(engine, biz["id"]) == {"intact": False, "altered_at": 3}


def test_deleting_a_middle_row_is_detected(client, engine):
    biz = launched(client)
    raw(engine, "DELETE FROM evidence WHERE id = :i", i=ids(engine, biz["id"])[3])
    assert state(engine, biz["id"]) == {"intact": False, "altered_at": 4}  # the row that followed it


def test_inserting_a_row_is_detected(client, engine):
    biz = launched(client)
    rows = ids(engine, biz["id"])
    with Session(engine) as s:
        third = s.get(Evidence, rows[2])
        forged = Evidence(business_id=biz["id"], run_id=third.run_id, check="test_order", step="owner_confirmed",
                          practice=True, at=third.at)
        prev, when = third.hash, third.at
        forged.prev_hash, forged.hash = prev, chain.row_hash(prev, forged)  # a careful forger: links it properly
    # make room after row 3, then slip the forged row in as the 4th
    for i in reversed(rows[3:]):
        raw(engine, "UPDATE evidence SET id = id + 1000 WHERE id = :i", i=i)
    raw(engine, "INSERT INTO evidence (id, business_id, run_id, \"check\", step, at, source, server, message_id, nonce,"
                " answer, practice, prev_hash, hash) VALUES (:id, :b, :r, 'test_order', 'owner_confirmed', :at, '', '',"
                " '', '', '', 1, :p, :h)", id=rows[2] + 1, b=biz["id"], r=forged.run_id, at=str(when), p=prev, h=forged.hash)
    assert state(engine, biz["id"]) == {"intact": False, "altered_at": 5}  # the old 4th row no longer follows
    raw(engine, "UPDATE evidence SET hash = 'junk' WHERE id = :i", i=rows[2] + 1)  # a careless forger
    assert state(engine, biz["id"]) == {"intact": False, "altered_at": 4}


# ---------- append-only in code ----------

def test_code_refuses_to_update_or_delete_evidence(client, engine):
    from sqlalchemy import update

    biz = launched(client)
    before = state(engine, biz["id"])
    with Session(engine) as s:
        row = s.exec(select(Evidence)).first()
        row.answer = "changed"
        s.add(row)
        with pytest.raises(chain.AppendOnly):
            s.commit()
    with Session(engine) as s:
        with pytest.raises(chain.AppendOnly):
            s.delete(s.exec(select(Evidence)).first())
            s.commit()
    with Session(engine) as s:
        with pytest.raises(chain.AppendOnly):
            s.exec(delete(Evidence).where(Evidence.business_id == biz["id"]))
        with pytest.raises(chain.AppendOnly):
            s.exec(update(Evidence).values(answer="changed"))
    assert state(engine, biz["id"]) == before


# ---------- backfill ----------

def test_backfill_chains_old_rows_once_and_the_same_way_every_time(client, engine, tmp_path):
    biz = launched(client)
    want = state(engine, biz["id"])
    with Session(engine) as s:
        chained = [(e.id, e.prev_hash, e.hash) for e in s.exec(select(Evidence).order_by(Evidence.id)).all()]
    raw(engine, "UPDATE evidence SET prev_hash = '', hash = ''")  # as if written before S11d
    assert state(engine, biz["id"])["intact"] is False
    assert chain.backfill(engine) == want["rows"]
    with Session(engine) as s:
        assert [(e.id, e.prev_hash, e.hash) for e in s.exec(select(Evidence).order_by(Evidence.id)).all()] == chained
        logged = s.exec(select(AuditEvent).where(AuditEvent.action == "evidence_chain_backfilled")).all()
        assert len(logged) == 1 and logged[0].business_id is None and "chain starts here" in logged[0].detail
    assert state(engine, biz["id"]) == want
    assert chain.backfill(engine) == 0  # once
    init_db(engine)  # every later start: nothing to do, nothing changes
    assert state(engine, biz["id"]) == want
    with Session(engine) as s:
        assert len(s.exec(select(AuditEvent).where(AuditEvent.action == "evidence_chain_backfilled")).all()) == 1


def test_startup_migration_adds_the_columns_and_chains_an_old_database(tmp_path):
    old = make_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with old.begin() as conn:  # the evidence table as it was before S11d, with two rows
        conn.execute(text('CREATE TABLE evidence (id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL, run_id INTEGER,'
                          ' "check" VARCHAR NOT NULL, step VARCHAR NOT NULL, at DATETIME NOT NULL, source VARCHAR NOT NULL,'
                          ' server VARCHAR NOT NULL, message_id VARCHAR NOT NULL, nonce VARCHAR NOT NULL, status_code INTEGER,'
                          ' cert_not_after DATETIME, answer VARCHAR NOT NULL, practice BOOLEAN NOT NULL)'))
        for i, step in ((1, "dns_answer"), (2, "http_response")):
            conn.execute(text("INSERT INTO evidence VALUES (:i, 5, 1, 'https', :s, '2026-11-10 08:00:00.000000', 'ns', '', '',"
                              " '', 200, NULL, 'ok', 0)"), {"i": i, "s": step})
    init_db(old)  # what every start does: add the two columns, then chain the old rows
    with Session(old) as s:
        assert [e.action for e in s.exec(select(AuditEvent)).all()] == ["evidence_chain_backfilled"]
    with Session(old) as s:
        assert chain.verify(s, 5)["intact"] is True and chain.verify(s, 5)["rows"] == 2
    old.dispose()


# ---------- purge ----------

def test_purge_removes_the_chain_and_logs_one_anonymous_event(client, engine):
    biz = launched(client)
    rows = state(engine, biz["id"])["rows"]
    with Session(engine) as s:
        name = s.get(Business, biz["id"]).name
    assert client.delete(f"/api/businesses/{biz['id']}").status_code == 200
    with Session(engine) as s:
        assert s.exec(select(Evidence)).all() == []
        logged = s.exec(select(AuditEvent).where(AuditEvent.action == "evidence_chain_purged")).all()
        assert len(logged) == 1
        e = logged[0]
        assert e.business_id is None and e.user_id is None and e.target == "" and e.actor == "system"
        assert e.detail == f"chain purged: {rows} proof row(s) removed with a deleted shop"
        assert name not in e.detail and str(biz["id"]) not in e.detail.replace(str(rows), "")
    assert state(engine, biz["id"]) == {"intact": True, "rows": 0, "head": ""}


# ---------- the receipt and the public verify ----------

def test_share_page_shows_the_receipt_and_verify_says_intact(client, new_client, engine):
    biz = launched(client)
    path = share_path(client, biz)
    visitor = new_client()
    want = state(engine, biz["id"])
    page = visitor.get(path).text
    assert f"Receipt {want['head'][:12]} · <a href='{path}/verify'>verify</a>" in page
    r = visitor.get(path + "/verify")
    assert r.status_code == 200 and r.json() == want and set(r.json()) == {"intact", "rows", "head"}
    assert r.headers["cache-control"] == "no-store"


def test_verify_leaks_nothing(client, new_client, engine):
    biz = launched(client)
    path = share_path(client, biz)
    visitor = new_client()
    ok = visitor.get(path + "/verify")
    assert sorted(ok.json()) == ["head", "intact", "rows"]
    assert isinstance(ok.json()["rows"], int) and len(ok.json()["head"]) == 64
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        secrets_ = [b.name, "Eggless", "meera"] + [v for e in s.exec(select(Evidence)).all()
                                                   for v in (e.nonce, e.message_id, e.source, e.server, e.answer) if v]
    assert not [v for v in secrets_ if v in ok.text]
    raw(engine, "UPDATE evidence SET answer = 'forged' WHERE id = :i", i=ids(engine, biz["id"])[1])
    bad = visitor.get(path + "/verify")
    assert bad.status_code == 200 and bad.json() == {"intact": False, "altered_at": 2}
    assert sorted(bad.json()) == ["altered_at", "intact"] and "forged" not in bad.text


def test_verify_with_no_evidence_yet(client, new_client):
    biz = meera(client)  # described, never launched
    path = share_path(client, biz)
    assert "Receipt" not in new_client().get(path).text
    assert new_client().get(path + "/verify").json() == {"intact": True, "rows": 0, "head": ""}


def test_revoked_paused_or_unknown_share_is_404(client, new_client, engine):
    biz = launched(client)
    path = share_path(client, biz)
    visitor = new_client()
    assert visitor.get(path + "/verify").status_code == 200
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.paused = True
        s.add(b)
        s.commit()
    assert visitor.get(path + "/verify").status_code == 404 and visitor.get(path).status_code == 404
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        b.paused = False
        s.add(b)
        s.commit()
    assert visitor.get(path + "/verify").status_code == 200
    client.delete(f"/api/businesses/{biz['id']}/share")
    gone = visitor.get(path + "/verify")
    assert gone.status_code == 404 and set(gone.json()) == {"detail"} and "head" not in gone.text
    assert visitor.get("/r/not-a-real-token/verify").status_code == 404


def test_verify_is_rate_limited_per_visitor(client, new_client):
    biz = launched(client)
    path = share_path(client, biz)
    one = new_client()
    for _ in range(proof_routes.VERIFY_PER_MINUTE):
        assert one.get(path + "/verify").status_code == 200
    assert one.get(path + "/verify").status_code == 429
    assert one.get("/r/guess/verify").status_code == 429  # guessing links is slowed too
    other = new_client()
    assert other.get(path + "/verify", headers={"x-forwarded-for": "203.0.113.9"}).status_code == 200
