"""S13 B: monitoring at the 40-shop scale, on the slow pretend world (`tests/scale_world.py`, times scaled 50x).

Measured BEFORE this change (one shop after another): quick round 534 s, daily round 670 s (simulated), the
hanging shop holding every shop behind it. The numbers after are printed by `test_40_shops_finish_well_inside…`.
"""

import json
import threading
import time

import pytest
from sqlmodel import Session, select

from app import chain
from app.godaddy.ratelimit import RateLimiter
from app.models import Alert, AuditEvent, Business, CheckResult, CheckRun, Evidence
from app.monitor.scheduler import (
    CHECK_WATCHDOG,
    DAILY_SLOTS,
    QUICK_MINUTES,
    ROUND_DEADLINE,
    SHOP_BUDGET,
    Monitor,
)
from tests.scale_world import FAIL, HANG, N_SHOPS, SCALE, SLOW, SlowWorld, build_shops, projected

pytestmark = pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")


@pytest.fixture
def settings(make_settings, tmp_path):
    # a file database: shops really run side by side (the in-memory test DB is one shared connection)
    return make_settings(database_url=f"sqlite:///{tmp_path / 'scale.db'}", max_shops_per_user=100,
                         user_describes_per_day=100, monitor_workers=4)


def scaled_monitor(engine, settings, integ, claude) -> Monitor:
    m = Monitor(engine, settings, lambda _b: integ, claude)
    m.budgets = {k: v * SCALE for k, v in SHOP_BUDGET.items()}
    m.check_seconds = CHECK_WATCHDOG * SCALE
    m.round_deadline = {k: v * SCALE for k, v in ROUND_DEADLINE.items()}
    m.inbox_pass_seconds = 60 * SCALE
    m.tick_wait = 48 * SCALE
    return m


@pytest.fixture
def world(client, engine, settings, integ, claude):
    shops = build_shops(client, engine)
    slow = SlowWorld(integ)
    yield shops, slow, scaled_monitor(engine, settings, integ, claude)
    slow.release.set()  # let the hanging call return so its thread ends


def ids_by_name(engine) -> dict[str, int]:
    with Session(engine) as s:
        return {b.subdomain: b.id for b in s.exec(select(Business)).all()}


def results(engine, bid: int, check: str) -> list[dict]:
    with Session(engine) as s:
        rows = s.exec(select(CheckResult).join(CheckRun, CheckRun.id == CheckResult.run_id).where(
            CheckResult.business_id == bid, CheckResult.check == check, CheckRun.trigger.like("monitor_%"))).all()
        return [json.loads(r.detail) | {"passed": r.passed} for r in rows]


def test_40_shops_finish_well_inside_15_minutes_and_the_hanging_one_delays_nobody(world, engine):
    _shops, slow, mon = world
    names = ids_by_name(engine)
    times = {}
    for kind in ("quick", "daily"):
        started = time.monotonic()
        got = mon._round(kind)
        times[kind] = projected(time.monotonic() - started)
        assert got["checked"] == N_SHOPS and got["unfinished"] == [] and got["busy"] == [], got
    print(f"\nAFTER (simulated s, 4 workers): quick {times['quick']:.0f}, daily {times['daily']:.0f}; "
          f"most calls in flight at once {slow.max_busy}")
    # was 534 s and 670 s (one after another); "well inside" = under half of the 15 minutes, even on a busy laptop
    assert times["quick"] < 7.5 * 60 and times["daily"] < 7.5 * 60
    assert slow.max_busy > 1  # really side by side
    # the hanging shop: its page check is "couldn't finish" (never passed), and it's said why
    hang = results(engine, names[HANG], "https")
    assert hang and all(not r["passed"] and r.get("unfinished") for r in hang)
    assert all("stopped waiting" in r["detail"] for r in hang)
    # ...and it delayed nobody: every ordinary shop finished long before the watchdog gave up on it
    with Session(engine) as s:
        quick = s.exec(select(CheckRun).where(CheckRun.trigger == "monitor_quick")).all()
    start = min(proof_time(r.started_at) for r in quick)
    ordinary = [r for r in quick if r.business_id not in {names[HANG], names[FAIL]}]
    latest = max(proof_time(r.finished_at) for r in ordinary)
    assert projected((latest - start).total_seconds()) < CHECK_WATCHDOG * 0.7
    slow_ones = {names[n] for n in SLOW}
    assert all(r.passed for r in ordinary if r.business_id not in slow_ones) and all(
        r.passed for r in ordinary if r.business_id in slow_ones)  # slow is never called broken


def proof_time(when):
    from app.monitor.scheduler import proof_aware

    return proof_aware(when)


def test_alert_rules_still_hold_at_scale(world, engine):
    _shops, _slow, mon = world
    names = ids_by_name(engine)
    mon._round("quick")
    jobs = {j.id for j in mon.scheduler.get_jobs()}
    assert f"recheck-{names[FAIL]}" in jobs  # a real failure is re-checked a minute later
    assert f"recheck-{names[HANG]}" not in jobs  # "couldn't finish" is not a failure: no re-check, no alert
    assert len([j for j in jobs if j.startswith("recheck-")]) == 1
    with Session(engine) as s:
        assert s.exec(select(Alert)).all() == []  # nothing is emailed from the first look


def test_no_round_stacks_on_another_and_a_busy_shop_is_skipped(world, engine):
    _shops, slow, mon = world
    names = ids_by_name(engine)
    mon.check_seconds = 10_000  # no watchdog: the hanging shop stays busy past the round's deadline
    # longer than every other shop needs (the failing one retries for 120 s), shorter than the 300 s hang
    mon.round_deadline = {"quick": 220 * SCALE, "daily": 220 * SCALE}
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("first", mon._round("quick")))
    t.start()
    time.sleep(5 * SCALE)
    assert mon._round("quick") == {"skipped_round": True}  # a second round never stacks
    t.join()
    assert got["first"]["unfinished"] == [names[HANG]]  # reported, and the round didn't wait for it
    again = mon._round("quick")  # the next round: the hanging shop's previous check is still running
    assert again["busy"] == [names[HANG]]  # skipped, not run twice
    with Session(engine) as s:
        rows = s.exec(select(AuditEvent).where(AuditEvent.action.in_(("monitor_round", "monitor_shop")))).all()
    assert {r.result for r in rows} >= {"skipped", "unfinished"}
    slow.release.set()


def test_godaddy_calls_stay_under_the_rate_limit(world, integ):
    _shops, slow, mon = world
    integ.godaddy.limiter = RateLimiter(calls=10, period=60 * SCALE)  # stricter than ours, to see it bite
    mon._round("daily")
    assert slow.most_godaddy_calls_in_a_minute() <= 10
    assert integ.godaddy.limiter.waited > 0  # the limit really held calls back (40 shops read the zone)


def test_the_evidence_chain_stays_intact_under_concurrency(world, engine):
    _shops, _slow, mon = world
    mon._round("daily")
    mon._round("quick")
    with Session(engine) as s:
        ids = [b.id for b in s.exec(select(Business)).all()]
        total = 0
        for bid in ids:
            v = chain.verify(s, bid)
            assert v["intact"], (bid, v)
            total += v["rows"]
        assert total == len(s.exec(select(Evidence)).all()) and total > N_SHOPS * 3


def test_slots_spread_the_shops_over_15_minutes_and_the_day():
    ids = list(range(1, N_SHOPS + 1))
    per_minute = [sum(1 for b in ids if Monitor.slot(b, QUICK_MINUTES) == m) for m in range(QUICK_MINUTES)]
    assert sum(per_minute) == N_SHOPS and max(per_minute) <= 6  # 40 shops: 2-3 a minute, never all at once
    assert Monitor.slot(7, QUICK_MINUTES) == Monitor.slot(7, QUICK_MINUTES)  # stable
    daily = {Monitor.slot(b, DAILY_SLOTS) for b in ids}
    assert len(daily) >= N_SHOPS - 2  # nearly every shop its own minute of the day


def test_each_tick_checks_only_the_shops_whose_slot_it_is_plus_the_overdue(world, engine):
    from datetime import timedelta

    from app.models import utcnow

    _shops, _slow, mon = world
    base = utcnow().replace(hour=3, minute=0, second=0, microsecond=0)
    seen: dict[int, int] = {}
    for m in range(QUICK_MINUTES):
        for bid in mon.due(base + timedelta(minutes=m))["quick"]:
            seen[bid] = seen.get(bid, 0) + 1
    assert set(seen) == set(ids_by_name(engine).values()) and set(seen.values()) == {1}  # each exactly once
    # a shop whose last quick check is old (the server was down) is caught up at the next tick
    bid = next(iter(seen))
    with Session(engine) as s:
        s.add(CheckRun(business_id=bid, plan_id=1, trigger="monitor_quick", status="done", passed=True,
                       started_at=base - timedelta(hours=2), finished_at=base - timedelta(hours=2)))
        s.commit()
    other = next(m for m in range(QUICK_MINUTES) if bid not in mon.due(base + timedelta(minutes=m))["quick"]) \
        if False else None  # noqa: SIM210
    assert other is None
    for m in range(QUICK_MINUTES):
        assert bid in mon.due(base + timedelta(minutes=m))["quick"]


# ---------- the test order's inbox look doesn't block a round ----------

@pytest.fixture
def one_shop(client, engine, settings, integ, claude):
    from tests.test_s9_phase1 import launched_shop

    biz, _p = launched_shop(client, engine, owner_email="meera@example.org")
    waits = []
    integ.sleep = waits.append
    integ.mailer.drop = True  # the test order email is accepted but doesn't arrive (yet)
    return biz["id"], Monitor(engine, settings, lambda _b: integ, claude), waits


def test_daily_round_records_accepted_now_and_looks_for_seen_later(one_shop, engine, integ):
    bid, mon, waits = one_shop
    assert mon.check_business(bid, "daily") == []
    assert 20 not in waits  # no 20-second inbox waits inside the round any more
    row = results(engine, bid, "test_order")[-1]
    assert row["passed"] and row["waiting"] and "look for it in the inbox again" in row["plain"]
    (job,) = [j for j in mon.scheduler.get_jobs() if j.id.startswith("inbox-")]
    _bid, run_id, item, n = job.args
    assert n == 1
    integ.inbox.deliver(sender="hello@example.com", to="meera@example.org", subject=f"[TEST] {item['nonce']}",
                        body="")
    assert mon.inbox_pass(*job.args) == "seen"
    row = results(engine, bid, "test_order")[-1]
    assert row["passed"] and not row["waiting"] and row["plain"] == "A test order reached your inbox."
    with Session(engine) as s:
        seen = s.exec(select(Evidence).where(Evidence.run_id == run_id, Evidence.step == "imap_seen")).all()
        assert len(seen) == 1 and seen[0].nonce == item["nonce"]
        assert chain.verify(s, bid)["intact"]


def test_a_test_order_still_missing_after_the_last_look_fails_and_is_rechecked(one_shop, engine):
    bid, mon, _waits = one_shop
    mon.check_business(bid, "daily")
    (job,) = [j for j in mon.scheduler.get_jobs() if j.id.startswith("inbox-")]
    _bid, run_id, item, _n = job.args
    assert mon.inbox_pass(bid, run_id, item, 1) == "later"  # looks again
    assert mon.inbox_pass(bid, run_id, item, 3) == "missing"  # the last look
    row = results(engine, bid, "test_order")[-1]
    assert not row["passed"] and "hasn't arrived" in row["plain"]
    with Session(engine) as s:
        assert s.get(CheckRun, run_id).passed is False
    assert f"recheck-{bid}" in {j.id for j in mon.scheduler.get_jobs()}  # the usual re-check + Doctor + alert path


def test_a_beat_never_waits_long_for_a_hanging_shop(world, engine):
    from datetime import timedelta

    from app.models import utcnow

    _shops, slow, mon = world
    hang = ids_by_name(engine)[HANG]
    mon.check_seconds = 10_000  # no watchdog: the worst case
    base = utcnow().replace(hour=5, minute=0, second=0, microsecond=0)
    at = base + timedelta(minutes=Monitor.slot(hang, QUICK_MINUTES))
    started = time.monotonic()
    got = mon.tick(at)
    took = projected(time.monotonic() - started)
    assert hang in got["quick"]["unfinished"] and took < 60  # the beat moved on within the minute
    assert mon.tick(at)["quick"]["busy"] == [hang]  # and the hanging shop isn't started a second time
    slow.release.set()
