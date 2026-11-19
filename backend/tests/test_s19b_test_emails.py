"""Session 19B: a seller only gets a test email when she asked for one, and a test never looks like an order.

- launch, "Run checks now" and "Describe the problem" send the test to the shop's order address (she asked);
- the daily run (and its re-check) sends it to LaunchWitness's own check mailbox, never to the seller, with no
  "Yes, I got it" link, and the report says "check mailbox", never "your inbox";
- every test email: subject starts with "TEST, not a real order:" (the one-time code kept), body opens with the
  grey "This is a check" banner, no call / WhatsApp buttons; real order emails are unchanged;
- test orders stay out of the Orders page, the "new" count and the daily capacity;
- one alert per problem.
"""

from sqlmodel import Session, select

from app import chain
from app.mail import layout
from app.models import Alert, CheckResult, CheckRun, Evidence, Order, Outbox, TestTicket
from app.monitor.scheduler import Monitor
from app.sites.orders import TEST_BANNER, TEST_SUBJECT
from app.sites.orders import test_audience as audience_for
from tests.test_s9_phase1 import HOST, ORDER, launched_shop

OWNER = "meera@example.org"


def mails_of_tests(integ) -> list[dict]:
    return [m for m in integ.mailer.sent if m["subject"].startswith(TEST_SUBJECT)]


def sent_rows(engine, kind: str) -> list[Outbox]:
    with Session(engine) as s:
        return list(s.exec(select(Outbox).where(Outbox.kind == kind).order_by(Outbox.id)).all())


def monitor(engine, settings, integ, claude) -> Monitor:
    return Monitor(engine, settings, lambda _b: integ, claude)


def last_result(engine, bid: int, trigger_prefix: str) -> dict:
    import json

    with Session(engine) as s:
        row = s.exec(select(CheckResult).join(CheckRun, CheckRun.id == CheckResult.run_id).where(
            CheckResult.business_id == bid, CheckResult.check == "test_order",
            CheckRun.trigger.like(f"{trigger_prefix}%")).order_by(CheckResult.id.desc())).first()
        return json.loads(row.detail) | {"passed": row.passed, "run_id": row.run_id}


# ---------- who gets it ----------

def test_audience_by_trigger():
    assert audience_for("launch") == audience_for("manual") == ""
    assert audience_for("monitor_daily") == audience_for("monitor_recheck") == "check"


def test_launch_sends_the_test_to_the_seller_once(client, engine, integ):
    launched_shop(client, engine, owner_email=OWNER)
    (mail,) = mails_of_tests(integ)
    assert mail["to"] == OWNER
    assert "/#/got-it?token=" in mail["body"]  # she can prove her own inbox got it


def test_run_checks_now_and_describe_the_problem_go_to_the_seller(client, engine, integ):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    assert client.post(f"/api/businesses/{biz['id']}/checks").status_code == 202
    assert client.post(f"/api/businesses/{biz['id']}/describe-problem",
                       json={"symptom": "my customer says the page won't open"}).status_code == 202
    sent = mails_of_tests(integ)
    assert len(sent) == 3 and all(m["to"] == OWNER for m in sent)
    assert all("/#/got-it?token=" in m["body"] for m in sent)


def test_daily_run_sends_the_test_to_our_check_mailbox_never_the_seller(client, engine, integ, settings, claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    before = len(integ.mailer.sent)
    assert monitor(engine, settings, integ, claude).check_business(biz["id"], "daily") == []
    new = integ.mailer.sent[before:]
    (mail,) = [m for m in new if m["subject"].startswith(TEST_SUBJECT)]
    assert mail["to"] == settings.smtp_user != OWNER
    assert not any(OWNER in m["to"] for m in new)  # nothing at all reached the seller
    assert "got-it" not in mail["body"]  # no "Yes, I got it" link: a tap in our mailbox would prove nothing about hers
    with Session(engine) as s:
        t = s.exec(select(TestTicket).order_by(TestTicket.id.desc())).first()
        assert t.audience == "check" and t.confirm_hash == ""


def test_daily_proof_is_labelled_our_check_mailbox_and_the_chain_still_verifies(client, engine, integ, settings,
                                                                                 claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    monitor(engine, settings, integ, claude).check_business(biz["id"], "daily")
    got = last_result(engine, biz["id"], "monitor_")
    assert got["passed"] and got["mailbox"] == "check"
    assert "LaunchWitness's check mailbox" in got["plain"] and "your inbox" not in got["plain"]
    with Session(engine) as s:
        hops = [e.step for e in s.exec(select(Evidence).where(Evidence.run_id == got["run_id"],
                                                              Evidence.check == "test_order")).all()]
        assert hops == ["form_post", "smtp_accepted", "imap_seen"]  # the same hops as ever
        seen = s.exec(select(Evidence).where(Evidence.run_id == got["run_id"], Evidence.step == "imap_seen")).one()
        assert seen.answer.startswith("LaunchWitness's check mailbox")
        assert chain.verify(s, biz["id"])["intact"]
    from app import proof
    from app.routers.report import run_out

    with Session(engine) as s:  # the run as the API serialises it (the owner's report shows launch / her own runs)
        run = run_out(s, s.get(CheckRun, got["run_id"]))
        proof.summary(s, run)
    check = next(c for c in run["checks"] if c["check"] == "test_order")
    assert check["title"] == "A test order reached LaunchWitness's check mailbox"
    assert any(h["title"] == "In LaunchWitness's check mailbox" for h in check["hops"])
    assert not any(h["title"] == "In the inbox" for h in check["hops"])


def test_launch_proof_still_says_your_inbox(client, engine, integ):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    check = next(c for c in rep["run"]["checks"] if c["check"] == "test_order")
    assert check["title"] == "A test order reached your inbox" and check["mailbox"] == ""


def test_daily_test_missing_from_our_mailbox_is_our_side_and_never_alerts_her(client, engine, integ, settings, claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    mon = monitor(engine, settings, integ, claude)
    integ.mailer.drop = True  # accepted, never arrives
    mon.inbox_pass_seconds = 0
    mon.check_business(biz["id"], "daily")
    (job,) = [j for j in mon.scheduler.get_jobs() if j.id.startswith("inbox-")]
    _b, run_id, item, _n = job.args
    assert mon.inbox_pass(biz["id"], run_id, item, 3) == "missing"
    got = last_result(engine, biz["id"], "monitor_daily")
    assert not got["passed"] and got["unfinished"] and "our side, not yours" in got["plain"]
    assert mon.recheck(biz["id"], ["test_order"]) == []  # couldn't check: no alert
    with Session(engine) as s:
        assert s.exec(select(Alert).where(Alert.business_id == biz["id"])).all() == []


# ---------- what it looks like ----------

def test_every_test_email_is_labelled_and_has_no_customer_buttons(client, engine, integ, settings, claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    client.post(f"/api/businesses/{biz['id']}/checks")
    monitor(engine, settings, integ, claude).check_business(biz["id"], "daily")
    sent = mails_of_tests(integ)
    assert len(sent) == 3
    with Session(engine) as s:
        nonces = [t.nonce for t in s.exec(select(TestTicket).order_by(TestTicket.id)).all()]
    for mail, nonce in zip(sent, nonces, strict=True):
        assert mail["subject"].startswith(f"{TEST_SUBJECT} ") and f"[{nonce}]" in mail["subject"]
        assert mail["body"].startswith(TEST_BANNER)
        assert "tel:" not in mail["body"] and "wa.me" not in mail["body"] and "WhatsApp the customer" not in mail["body"]
        assert "New order" not in mail["subject"] and "New order" not in mail["body"]
        assert 'data-lw="test-banner"' in mail["html"] and layout.TEST_BG in mail["html"]
        assert "tel:" not in mail["html"] and "wa.me" not in mail["html"]


def test_real_order_email_is_unchanged(client, engine, integ):
    launched_shop(client, engine, owner_email=OWNER)
    assert client.post("/order", data=ORDER, headers=HOST).status_code == 200
    mail = integ.mailer.sent[-1]
    assert mail["subject"].startswith("New order for Meera's Eggless Bakes from Asha Rao (LW-")
    assert not mail["subject"].startswith(TEST_SUBJECT) and "[" not in mail["subject"]
    assert mail["body"].startswith("New order LW-") and TEST_BANNER not in mail["body"]
    assert "Call: tel:+919876543210" in mail["body"] and "WhatsApp the customer: https://wa.me/" in mail["body"]
    assert "test-banner" not in mail["html"]


def test_banner_contrast_passes_aa():
    assert layout.contrast(layout.TEXT, layout.TEST_BG) >= 4.5


# ---------- test orders are evidence only ----------

def test_test_orders_hidden_from_orders_new_count_and_capacity(client, engine, integ, settings, claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    client.post(f"/api/businesses/{biz['id']}/checks")
    monitor(engine, settings, integ, claude).check_business(biz["id"], "daily")
    with Session(engine) as s:
        assert len(s.exec(select(Order).where(Order.business_id == biz["id"], Order.is_test)).all()) == 3
    assert client.get(f"/api/businesses/{biz['id']}/orders").json() == []
    shop = next(b for b in client.get("/api/businesses").json() if b["id"] == biz["id"])
    assert shop["new_orders"] == 0
    from app.agents.reader import Profile
    from app.models import Business
    from app.sites.orders import full_days, orders_on

    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        p = Profile.model_validate_json(b.profile_json).model_copy(update={"max_orders_per_day": 1})
        test_days = {o.wanted_date for o in s.exec(select(Order).where(Order.is_test)).all()}
        for day in test_days | {""}:
            assert orders_on(s, b.id, day) == 0
        assert full_days(s, b, p) == []


def test_one_alert_per_problem_until_it_changes(client, engine, integ, settings, claude):
    biz, _p = launched_shop(client, engine, owner_email=OWNER)
    mon = monitor(engine, settings, integ, claude)
    from app.agents.checker import Outcome

    bad = Outcome("https", False, "Your website didn't open.", "status=None")
    for _ in range(3):  # three rounds find the same unchanged problem
        mon.check_alert(biz["id"], "meera.localhost", bad)
    alerts = [r for r in sent_rows(engine, "alert") if r.status == "sent"]
    assert len(alerts) == 1 and alerts[0].to_addr == OWNER
