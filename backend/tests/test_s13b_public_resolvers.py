"""S13b: on the daily run the monitor also asks 8.8.8.8, 1.1.1.1 and 9.9.9.9 for each live shop's address and saves
what they say as evidence ("Reachable from 3 of 3 public resolvers"). Information only: one that disagrees is said
plainly and never alerted on; the shop's own nameservers stay the proof."""

import pytest
from sqlmodel import Session, select

from app import chain
from app.agents.checker import public_resolvers_text
from app.checks.dns_resolver import PUBLIC_RESOLVERS, Answer, FakeDnsResolver
from app.models import Alert, AuditEvent, CheckResult, CheckRun, Evidence
from app.monitor.scheduler import Monitor
from tests.test_m4_report import report
from tests.test_s9_phase1 import launched_shop

HOST = "meera.localhost"


class Broken:
    def resolve(self, name, rtype):
        raise TimeoutError("no answer")


def resolvers(ip: str, odd: dict[str, object] | None = None):
    """Three public resolvers that answer `ip`, except the ones named in `odd` (label -> resolver)."""
    odd = odd or {}
    out = []
    for name, addr in PUBLIC_RESOLVERS:
        label = f"{name} {addr}"
        out.append((label, odd.get(name) or FakeDnsResolver({(HOST, "A"): [ip]})))
    return lambda: out


@pytest.fixture
def shop(client, engine, settings, integ, claude):
    biz, _p = launched_shop(client, engine, owner_email="meera@example.org")
    integ.mailer.drop = True  # the daily test order: accepted now, looked for later (not this test's subject)
    return biz, Monitor(engine, settings, lambda _b: integ, claude)


def evidence(engine, bid: int) -> list[Evidence]:
    with Session(engine) as s:
        return s.exec(select(Evidence).where(Evidence.business_id == bid, Evidence.step == "public_resolvers")
                      .order_by(Evidence.id)).all()


# ---------- the plain words ----------

def test_three_of_three():
    seen = [(f"{n} {ip}", Answer("ok", ("1.2.3.4",))) for n, ip in PUBLIC_RESOLVERS]
    head, answers = public_resolvers_text("1.2.3.4", seen).split(" | ")
    assert head == "Reachable from 3 of 3 public resolvers"
    assert answers == "Google 8.8.8.8: 1.2.3.4; Cloudflare 1.1.1.1: 1.2.3.4; Quad9 9.9.9.9: 1.2.3.4"


def test_one_disagrees_is_said_plainly():
    seen = [("Google 8.8.8.8", Answer("ok", ("1.2.3.4",))), ("Cloudflare 1.1.1.1", Answer("nodata")),
            ("Quad9 9.9.9.9", Answer("ok", ("5.6.7.8",)))]
    head = public_resolvers_text("1.2.3.4", seen).split(" | ")[0]
    assert head.startswith("Reachable from 1 of 3 public resolvers (")
    assert "Cloudflare has no address for it yet" in head and "Quad9 still shows an old address" in head
    assert "no alert for this" in head


def test_a_resolver_that_does_not_answer_is_ours_to_say():
    seen = [("Google 8.8.8.8", Answer("ok", ("1.2.3.4",))), ("Cloudflare 1.1.1.1", Answer("ok", ("1.2.3.4",))),
            ("pretend Quad9 9.9.9.9", Answer("error"))]
    text = public_resolvers_text("1.2.3.4", seen)
    assert text.startswith("Reachable from 2 of 3 public resolvers (Quad9 didn't answer us")
    assert text.endswith("pretend Quad9 9.9.9.9: no answer")


# ---------- the daily run ----------

def test_daily_run_saves_it_through_the_proof_chain(shop, engine, settings, integ, client):
    biz, mon = shop
    integ.public_dns = resolvers(settings.server_ip)
    mon.check_business(biz["id"], "daily")
    (row,) = evidence(engine, biz["id"])
    assert row.check == "site_points" and row.answer.startswith("Reachable from 3 of 3 public resolvers | ")
    assert row.hash and row.practice is True  # the pretend world: labelled
    with Session(engine) as s:
        assert chain.verify(s, biz["id"])["intact"]
        assert s.get(CheckRun, row.run_id).trigger == "monitor_daily"
    got = report(client, biz)["monitoring"]["public_resolvers"]
    assert got["title"] == "Reachable from 3 of 3 public resolvers" and got["agree"] is True


def test_quick_rounds_do_not_ask(shop, engine, settings, integ):
    biz, mon = shop
    integ.public_dns = resolvers(settings.server_ip)
    mon.check_business(biz["id"], "quick")
    assert evidence(engine, biz["id"]) == []


def test_one_resolver_disagreeing_never_alerts_or_fails_the_shop(shop, engine, settings, integ, client):
    biz, mon = shop
    integ.public_dns = resolvers(settings.server_ip, {"Quad9": FakeDnsResolver({(HOST, "A"): ["203.0.113.9"]}),
                                                      "Cloudflare": Broken()})
    assert "site_points" not in mon.check_business(biz["id"], "daily")
    (row,) = evidence(engine, biz["id"])
    assert row.answer.startswith("Reachable from 1 of 3 public resolvers (Cloudflare didn't answer us; Quad9 still "
                                 "shows an old address")
    with Session(engine) as s:
        assert s.exec(select(Alert)).all() == []
        site = s.exec(select(CheckResult).where(CheckResult.run_id == row.run_id,
                                                CheckResult.check == "site_points")).one()
        assert site.passed  # the shop's own nameservers decide
        (ev,) = s.exec(select(AuditEvent).where(AuditEvent.action == "public_resolvers")).all()
        assert ev.result == "differs" and ev.detail == "1 of 3 agree"
    assert f"recheck-{biz['id']}" not in {j.id for j in mon.scheduler.get_jobs()}
    rep = report(client, biz)
    assert rep["monitoring"]["public_resolvers"]["agree"] is False
    from app.proof import evidence_out

    hop = evidence_out(row)  # how the run's site_points hops show it: the plain summary is the hop's title
    assert hop["title"].startswith("Reachable from 1 of 3 public resolvers (") and " | " not in hop["title"]


def test_a_broken_look_never_breaks_the_round(shop, engine, integ):
    biz, mon = shop

    def boom():
        raise RuntimeError("resolver setup failed")

    integ.public_dns = boom
    mon.check_business(biz["id"], "daily")  # no exception
    assert evidence(engine, biz["id"]) == []
    with Session(engine) as s:
        (ev,) = s.exec(select(AuditEvent).where(AuditEvent.action == "public_resolvers")).all()
        assert ev.result == "failed" and ev.detail == "RuntimeError"


def test_real_integrations_ask_the_three_public_resolvers(settings):
    from app.integrations import real_integrations

    got = real_integrations(settings).public_dns()
    assert [label for label, _r in got] == ["Google 8.8.8.8", "Cloudflare 1.1.1.1", "Quad9 9.9.9.9"]
    assert [r._r.nameservers for _label, r in got] == [["8.8.8.8"], ["1.1.1.1"], ["9.9.9.9"]]
