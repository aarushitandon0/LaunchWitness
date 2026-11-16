"""S13 A: the durable email outbox. Retry + backoff, dead letters, idempotency, a crash mid-send, the daily
budget and priorities, an expired link, an order kept when the mail server is down, and no double send."""

import json
import smtplib
import threading
import time
from datetime import timedelta

import pytest
from sqlmodel import Session, select

from app import outbox
from app.db import init_db, make_engine
from app.models import AuditEvent, Order, Outbox, utcnow
from app.startup import reconcile
from tests.conftest import ADMIN_TOKEN
from tests.test_s9_phase1 import HOST, ORDER, launched_shop

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def put(session, settings, mailer, key="k1", kind="alert", channel="smtp", body="Body", **kw):
    return outbox.send(session, settings, mailer, kind=kind, key=key, to="owner@example.org", subject="Hello",
                       body=body, channel=channel, **kw)


def rows(engine) -> list[Outbox]:
    with Session(engine) as s:
        return list(s.exec(select(Outbox).order_by(Outbox.id)).all())


def later(seconds: float):
    return utcnow() + timedelta(seconds=seconds)


# ---------- retry, backoff, dead letters ----------

def test_temporary_failure_is_retried_with_growing_waits_then_sent(engine, settings, mailer):
    mailer.fail = True
    with Session(engine) as s:
        row = put(s, settings, mailer)
        assert row.status == "failed" and row.attempts == 1 and row.last_error == "ConnectionError"
        first_wait = (outbox.aware(row.next_try_at) - utcnow()).total_seconds()
    assert 0.8 * outbox.BASE_DELAY_S - 2 <= first_wait <= 1.2 * outbox.BASE_DELAY_S
    assert outbox.run_once(engine, settings, lambda _c: mailer) == {}  # not due yet: nothing tried
    assert outbox.run_once(engine, settings, lambda _c: mailer, now=later(40)) == {"failed": 1}
    second = rows(engine)[0]
    assert second.attempts == 2
    assert (outbox.aware(second.next_try_at) - utcnow()).total_seconds() > first_wait  # waits longer each time
    mailer.fail = False
    assert outbox.run_once(engine, settings, lambda _c: mailer, now=later(200)) == {"sent": 1}
    done = rows(engine)[0]
    assert done.status == "sent" and done.message_id and done.last_error == "" and len(mailer.sent) == 1


def test_backoff_doubles_with_jitter_and_is_capped():
    for n in range(1, 15):
        base = min(outbox.MAX_DELAY_S, outbox.BASE_DELAY_S * 2 ** (n - 1))
        got = [outbox.backoff(n) for _ in range(30)]
        assert all(0.8 * base <= g <= 1.2 * base for g in got)
        assert len({round(g, 3) for g in got}) > 1  # jitter: not all at the same moment


def test_permanent_refusal_is_dead_at_once_and_the_team_is_warned(client, engine, settings, mailer):
    def refuse(**_kw):
        raise smtplib.SMTPRecipientsRefused({"owner@example.org": (550, b"no such user owner@example.org")})

    mailer.send = refuse
    with Session(engine) as s:
        row = put(s, settings, mailer)
    assert row.status == "dead" and row.attempts == 1
    assert row.last_error == "SMTPRecipientsRefused 550" and "@" not in row.last_error  # no address kept
    assert "outbox_dead" in client.get("/api/health", headers=ADMIN).json().get("warning_codes", [])
    assert "outbox_dead" not in client.get("/api/health").json().get("warning_codes", [])  # the team only
    assert outbox.run_once(engine, settings, lambda _c: mailer, now=later(3600)) == {}  # never tried again


def test_a_refused_mail_sign_in_is_not_permanent(engine, settings, mailer):
    def bad_password(**_kw):
        raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    mailer.send = bad_password
    with Session(engine) as s:
        assert put(s, settings, mailer).status == "failed"  # the team can fix the password: keep trying


def test_too_many_temporary_failures_end_dead(engine, settings, mailer):
    mailer.fail = True
    with Session(engine) as s:
        put(s, settings, mailer)
    for i in range(outbox.MAX_ATTEMPTS + 2):
        outbox.run_once(engine, settings, lambda _c: mailer, now=later(4000 * (i + 1)))
    row = rows(engine)[0]
    assert row.status == "dead" and row.attempts == outbox.MAX_ATTEMPTS


# ---------- idempotency, crash, two senders ----------

def test_the_same_key_is_saved_and_sent_once(engine, settings, mailer):
    with Session(engine) as s:
        a = put(s, settings, mailer, key="order:1")
        b = put(s, settings, mailer, key="order:1", retry_now=True)
    assert a.id == b.id and len(rows(engine)) == 1 and len(mailer.sent) == 1


def test_a_crash_mid_send_is_requeued_with_the_same_message_id(engine, settings, mailer):
    with Session(engine) as s:
        row, _ = outbox.enqueue(s, settings, kind="alert", key="k", to="o@example.org", subject="s", body="b")
        planned = json.loads(row.ref_json)["planned_id"]
        assert outbox.claim(s, row.id, utcnow())  # the process dies here, between "sending" and the answer
    assert rows(engine)[0].status == "sending"
    assert outbox.run_once(engine, settings, lambda _c: mailer) == {}  # a fresh claim isn't stolen
    assert reconcile(engine)["outbox"] == 1  # the restart puts it back in the queue
    assert rows(engine)[0].status == "failed" and "restarted" in rows(engine)[0].last_error
    seen = []
    mailer_send = mailer.send

    def spy(**kw):
        seen.append(kw.get("message_id"))
        return mailer_send(**kw)

    mailer.send = spy
    assert outbox.run_once(engine, settings, lambda _c: mailer) == {"sent": 1}
    assert seen == [planned]  # same Message-ID, so a copy sent just before the crash shows as one email


def test_a_stale_claim_is_freed_by_the_sender_job(engine, settings, mailer):
    with Session(engine) as s:
        row, _ = outbox.enqueue(s, settings, kind="alert", key="k", to="o@example.org", subject="s", body="b")
        outbox.claim(s, row.id, utcnow() - timedelta(minutes=11), ignore_backoff=True)
    got = outbox.run_once(engine, settings, lambda _c: mailer)
    assert got == {"reclaimed": 1, "sent": 1} and len(mailer.sent) == 1


def test_two_senders_never_send_the_same_email_twice(tmp_path, settings):
    engine = make_engine(f"sqlite:///{tmp_path / 'two.db'}")
    init_db(engine)
    sent, gate = [], threading.Barrier(2)

    class Slow:
        def send(self, **kw):
            sent.append(kw["to"])
            time.sleep(0.2)
            return "<id@x>"

    with Session(engine) as s:
        for i in range(5):
            outbox.enqueue(s, settings, kind="alert", key=f"k{i}", to=f"o{i}@example.org", subject="s", body="b")

    def worker():
        gate.wait()
        outbox.run_once(engine, settings, lambda _c: Slow())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(sent) == sorted(f"o{i}@example.org" for i in range(5))  # each exactly once
    with Session(engine) as s:
        assert all(r.status == "sent" for r in s.exec(select(Outbox)).all())
        row = s.exec(select(Outbox)).first()
        assert not outbox.claim(s, row.id, utcnow(), ignore_backoff=True)  # a sent row can't be claimed again


# ---------- budget and priorities ----------

def fill_today(engine, n: int) -> None:
    with Session(engine) as s:
        for i in range(n):
            s.add(Outbox(key=f"old{i}", kind="alert", to_addr="x@example.org", subject="s", status="sent",
                         sent_at=utcnow(), channel="smtp"))
        s.commit()


@pytest.mark.parametrize("used, held", [(3, set()), (4, {"test_order", "digest"}),
                                        (5, {"test_order", "digest", "alert", "team"})])
def test_near_the_daily_budget_low_priority_mail_waits_and_sign_ins_and_orders_never_do(
        make_settings, engine, mailer, used, held):
    settings = make_settings(smtp_daily_limit=5)
    fill_today(engine, used)
    with Session(engine) as s:
        for kind in ("login", "order", "alert", "team", "test_order", "digest"):
            row = put(s, settings, mailer, key=f"new-{kind}", kind=kind)
            assert (row.status == "queued") == (kind in held), kind
            if kind in held:
                assert row.last_error == "waiting: daily send budget" and row.attempts == 0
            else:  # sent: take it out again, so every kind sees the same count for today
                assert row.status == "sent"
                s.delete(row)
                s.commit()


def test_practice_mail_doesnt_use_the_real_budget(make_settings, engine, mailer):
    settings = make_settings(smtp_daily_limit=1)
    fill_today(engine, 1)
    with Session(engine) as s:
        assert put(s, settings, mailer, kind="digest", channel="practice").status == "sent"
        assert put(s, settings, mailer, key="k2", kind="digest").status == "queued"


def test_held_mail_goes_out_the_next_day(make_settings, engine, mailer):
    settings = make_settings(smtp_daily_limit=1)
    fill_today(engine, 1)
    with Session(engine) as s:
        put(s, settings, mailer, kind="digest")
    tomorrow = outbox.start_of_day(utcnow()) + timedelta(days=1, minutes=1)
    assert outbox.run_once(engine, settings, lambda _c: mailer, now=tomorrow) == {"sent": 1}


# ---------- sign-in links ----------

def test_a_link_that_would_arrive_expired_is_dropped_and_forgotten(engine, settings, mailer):
    mailer.fail = True
    with Session(engine) as s:
        row = put(s, settings, mailer, key="login:x", kind="login", html="<a href=x>link</a>",
                  expires_at=utcnow() + timedelta(minutes=13))
    assert row.status == "failed"
    mailer.fail = False
    assert outbox.run_once(engine, settings, lambda _c: mailer, now=later(14 * 60)) == {"dead": 1}
    row = rows(engine)[0]
    assert mailer.sent == [] and row.body == "" and row.html == "" and row.last_error.startswith("expired")


def test_a_sign_in_link_is_kept_retried_and_then_forgotten_once_sent(make_settings, engine, claude, integ):
    from tests.test_s9_phase2_access import AppClient, make_app

    integ.mailer.fail = True
    app, settings = make_app(make_settings, engine, integ.mailer, claude, integ, dev_mode=False)
    with AppClient(app) as c:
        r = c.post("/api/auth/request-link", json={"email": "m@example.org"})
    assert r.status_code == 200 and r.json()["mail_delayed"] is True
    row = rows(engine)[0]
    assert row.kind == "login" and row.priority == 0 and row.status == "failed"
    assert outbox.aware(row.expires_at) <= utcnow() + timedelta(minutes=13, seconds=5)  # 15 min link, 2 min margin
    integ.mailer.fail = False
    assert outbox.run_once(engine, settings, lambda _c: integ.mailer, now=later(60)) == {"sent": 1}
    row = rows(engine)[0]
    assert "signin/confirm" in integ.mailer.sent[-1]["body"] and row.body == "" and row.html == ""


# ---------- orders ----------

def test_an_order_is_kept_when_the_mail_server_is_down_and_sent_later(client, engine, settings, integ):
    biz, _p = launched_shop(client, engine, owner_email="meera@example.org")
    integ.mailer.fail = True
    r = client.post("/order", data=ORDER, headers=HOST)
    assert r.status_code == 200 and "Thank you" in r.text  # the customer's order went through
    listed = client.get(f"/api/businesses/{biz['id']}/orders").json()
    assert listed[0]["email_status"] == "retrying"
    with Session(engine) as s:
        order = s.exec(select(Order).where(Order.is_test == False)).one()  # noqa: E712
        assert order.email_status == "retrying" and order.email_message_id == ""
    integ.mailer.fail = False
    assert outbox.run_once(engine, settings, lambda _c: integ.mailer, now=later(60)) == {"sent": 1}
    listed = client.get(f"/api/businesses/{biz['id']}/orders").json()
    assert listed[0]["email_status"] == "sent"
    with Session(engine) as s:
        order = s.get(Order, order.id)
        row = s.exec(select(Outbox).where(Outbox.key == f"order:{order.id}")).one()
        assert order.email_message_id == row.message_id != ""
        assert [e.result for e in s.exec(select(AuditEvent).where(AuditEvent.action == "order_email",
                                                                   AuditEvent.target == f"order:{order.id}"))] \
            == ["failed", "sent"]


def test_the_test_order_proof_carries_the_outboxs_real_message_id(client, engine):
    from app.models import Evidence

    launched_shop(client, engine)
    with Session(engine) as s:
        ev = s.exec(select(Evidence).where(Evidence.step == "smtp_accepted")).all()[-1]
        test = s.exec(select(Order).where(Order.is_test == True)).all()[-1]  # noqa: E712
        row = s.exec(select(Outbox).where(Outbox.key == f"order:{test.id}")).one()
    assert row.kind == "test_order" and row.priority == 2 and row.status == "sent"
    assert ev.message_id == row.message_id and ev.answer == f"outbox {row.id}, try 1"


def test_a_test_order_held_by_the_budget_is_unfinished_not_failed(client, engine, make_settings, integ, claude):
    from app.agents.checker import check_test_order
    from tests.test_m4_repair import ctx_for

    _biz, p = launched_shop(client, engine)
    settings = make_settings(smtp_daily_limit=0)
    ctx = ctx_for(engine, settings, integ, p["id"])
    integ.fake = False  # stand in for the real mail server, so the budget applies
    try:
        out = check_test_order(ctx)
    finally:
        integ.fake = True
    assert not out.passed and out.unfinished and "waiting its turn" in out.plain


# ---------- the team's view ----------

def test_admin_sees_counts_and_errors_but_no_bodies_or_addresses(client, engine, settings, mailer):
    mailer.fail = True
    with Session(engine) as s:
        put(s, settings, mailer, key="secret-order", body="Asha Rao 98765 43210")
    assert client.get("/api/admin/outbox").status_code in (401, 403, 404)
    got = client.get("/api/admin/outbox", headers=ADMIN).json()
    assert got["counts"]["failed"] == 1 and got["daily_limit"] == settings.smtp_daily_limit
    text = json.dumps(got)
    assert "Asha" not in text and "@" not in text and "Hello" not in text
    assert got["recent_errors"][0]["error"] == "ConnectionError"


def test_practice_mail_switch_is_team_only_and_pretend_only(client, integ):
    assert client.put("/api/admin/practice-mail", json={"down": True}).status_code in (401, 403, 404)
    r = client.put("/api/admin/practice-mail", json={"down": True}, headers=ADMIN)
    assert r.status_code == 200 and r.json() == {"down": True, "practice": True} and integ.mailer.fail is True
    client.put("/api/admin/practice-mail", json={"down": False}, headers=ADMIN)
    assert integ.mailer.fail is False
