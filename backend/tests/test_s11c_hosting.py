"""S11c: hosting failures nobody had tested.

1. DNS before TLS: a shop's first https request (which makes Caddy ask Let's Encrypt) can only happen after its
   address record is written AND every nameserver answers with our server; /internal/tls-ask says yes from exactly
   that point, and says no again if DNS stops pointing at us.
2. DNS_MODE=wildcard: the app neither writes nor reads GoDaddy for shops, and everything else still holds."""

import pytest
from sqlmodel import Session, select

from app.checks.dns_resolver import AuthoritativeResolver, FakeDnsResolver, points_here
from app.models import Business, Plan
from app.routers.internal import is_allowed_tls_domain
from app.zone_hygiene import approve, compare, scan
from tests.conftest import AppClient
from tests.test_s9_phase2_access import approved_shop, real_approve, real_world

HOST = "meera.localhost"
IP = "127.0.0.1"


class Watched:
    """Wraps the stand-in real world's DNS and web probe and writes down the order things happen in."""

    def __init__(self, server, engine, settings_of):
        self.log: list[tuple] = []
        self.server, self.engine, self.settings_of = server, engine, settings_of
        dns, http = server.dns, server.http
        outer = self

        class Dns:
            hide = dns.hide

            def resolve(self, name, rtype):
                got = dns.resolve(name, rtype)
                if rtype == "A" and name == HOST:
                    outer.log.append(("dns", IP in got, outer.live()))
                return got

        real_fetch = http.fetch

        def fetch(url):
            if url.startswith(f"https://{HOST}"):
                outer.log.append(("https", IP in dns.resolve(HOST, "A"), outer.live()))
            return real_fetch(url)

        server.dns, http.fetch = Dns(), fetch

    def live(self) -> bool:
        """What tls-ask would say from the database alone, right now."""
        with Session(self.engine) as s:
            return is_allowed_tls_domain(HOST, self.settings_of(), s)


def launch(make_settings, engine, mailer, claude, before=None, **kw):
    app, server = real_world(make_settings, engine, mailer, claude, **kw)
    watch = Watched(server, engine, lambda: make_settings(**kw))
    if before:
        before(server)
    with AppClient(app) as c:
        biz = approved_shop(c, engine)
        r = real_approve(c, biz)
        assert r.status_code == 200, r.text
    with Session(engine) as s:
        plan = s.exec(select(Plan).where(Plan.business_id == biz["id"]).order_by(Plan.id.desc())).first()
        return app, server, watch, biz, plan.status


# ---------- 1. DNS before TLS ----------

def test_first_https_request_comes_only_after_the_record_is_written_and_answered(make_settings, engine, mailer, claude):
    _app, server, watch, _biz, status = launch(make_settings, engine, mailer, claude)
    assert status == "done"
    kinds = [e[0] for e in watch.log]
    assert "https" in kinds and "dns" in kinds
    first_https = kinds.index("https")
    # Before the first https request: the nameserver was asked, it answered with our server, and at the moment of
    # that answer the shop was NOT yet approved for a certificate.
    before = watch.log[:first_https]
    assert ("dns", True, False) in before
    # At the first https request: the address points at us and tls-ask says yes (or the padlock check could never pass).
    assert watch.log[first_https] == ("https", True, True)
    # tls-ask never said yes while the nameserver didn't answer with our server.
    assert not any(kind == "dns" and not pointed and allowed for kind, pointed, allowed in watch.log)
    assert server.godaddy.writes() == [("set_records", "localhost", "A", "meera")]


def test_no_https_request_and_no_certificate_while_dns_has_not_spread(make_settings, engine, mailer, claude):
    _app, server, watch, _biz, status = launch(make_settings, engine, mailer, claude,
                                               before=lambda sv: sv.dns.hide.add((HOST, "A")))
    assert status == "failed"  # "the internet hasn't picked up the new address yet": press Resume
    assert [e for e in watch.log if e[0] == "https"] == []
    assert watch.log and all(e == ("dns", False, False) for e in watch.log)
    assert server.http.calls == []
    assert watch.live() is False


def fake_ns(answers: dict):
    """An AuthoritativeResolver over two pretend nameservers; `answers` maps the server's IP to its A answer
    (an Exception = that server doesn't answer)."""
    finder = FakeDnsResolver({("shops.test", "NS"): ["ns1.example.", "ns2.example."],
                              ("ns1.example", "A"): ["10.0.0.1"], ("ns2.example", "A"): ["10.0.0.2"]})

    def query(name, rtype, ip):
        got = answers[ip]
        if isinstance(got, Exception):
            raise got
        return got

    return AuthoritativeResolver(finder=finder, query=query)


@pytest.mark.parametrize("answers, want", [
    ({"10.0.0.1": [IP], "10.0.0.2": [IP]}, True),
    ({"10.0.0.1": [IP], "10.0.0.2": []}, False),  # one nameserver is behind: Let's Encrypt might ask that one
    ({"10.0.0.1": [IP], "10.0.0.2": ["203.0.113.9"]}, False),
    ({"10.0.0.1": [IP], "10.0.0.2": TimeoutError()}, False),  # we couldn't ask: not proven
    ({"10.0.0.1": TimeoutError(), "10.0.0.2": TimeoutError()}, False),
])
def test_the_address_is_set_only_when_every_nameserver_says_so(answers, want):
    assert points_here(fake_ns(answers), "meera.shops.test", IP) is want


def test_no_nameservers_found_is_not_a_yes():
    assert points_here(AuthoritativeResolver(finder=FakeDnsResolver(), query=lambda *a: [IP]), HOST, IP) is False


def test_tls_ask_says_no_again_when_dns_stops_pointing_at_us(make_settings, engine, mailer, claude):
    app, server, _watch, _biz, status = launch(make_settings, engine, mailer, claude)
    assert status == "done"
    with AppClient(app) as c:
        ask = lambda d: c.get("/internal/tls-ask", params={"domain": d}).status_code  # noqa: E731
        assert ask(HOST) == 200
        assert ask("nobody.localhost") == 404
        server.godaddy.zones["localhost"] = [r for r in server.godaddy.zones["localhost"] if r["name"] != "meera"]
        assert ask(HOST) == 404  # still live in the database, but a certificate attempt would fail: don't try
        assert ask("localhost") == 200  # the app's own name never depends on a shop's record


# ---------- 2. DNS_MODE=wildcard ----------

def star(server):
    """The owner made the wildcard by hand, and GoDaddy's API refuses us (reads as well as writes)."""
    server.godaddy.zones.setdefault("localhost", []).append({"type": "A", "name": "*", "data": IP, "ttl": 600})
    server.godaddy.fail_next["get_records"] = server.godaddy.fail_next["set_records"] = 999


def test_wildcard_mode_launches_and_proves_a_shop_without_touching_godaddy(make_settings, engine, mailer, claude):
    app, server, watch, biz, status = launch(make_settings, engine, mailer, claude, before=star, dns_mode="wildcard")
    assert status == "done"
    assert server.godaddy.writes() == []
    assert ("get_records", "localhost") not in server.godaddy.calls  # the shop zone isn't even read
    kinds = [e[0] for e in watch.log]
    assert ("dns", True, False) in watch.log[:kinds.index("https")]  # still proven at the nameserver first
    with AppClient(app) as c:
        ask = lambda d: c.get("/internal/tls-ask", params={"domain": d}).status_code  # noqa: E731
        assert ask(HOST) == 200
        # The wildcard makes EVERY name reach our server; tls-ask is what stops certificates for random names.
        assert IP in server.dns.resolve("random-name.localhost", "A")
        assert ask("random-name.localhost") == 404
    with Session(engine) as s:
        b = s.get(Business, biz["id"])
        assert b.status == "live" and not b.practice
        b.paused = True
        s.add(b)
        s.commit()
    with AppClient(app) as c:
        assert c.get("/internal/tls-ask", params={"domain": HOST}).status_code == 404  # paused: no certificate


def test_wildcard_mode_fails_the_launch_when_the_wildcard_is_not_there(make_settings, engine, mailer, claude):
    _app, server, watch, _biz, status = launch(make_settings, engine, mailer, claude, dns_mode="wildcard")
    assert status == "failed"
    assert server.godaddy.writes() == [] and server.http.calls == []
    assert watch.live() is False


def test_per_shop_mode_is_the_default_and_writes_one_record(make_settings, engine, mailer, claude):
    assert make_settings().dns_mode == "per_shop"
    _app, server, _watch, _biz, status = launch(make_settings, engine, mailer, claude)
    assert status == "done" and server.godaddy.writes() == [("set_records", "localhost", "A", "meera")]


def test_zone_hygiene_in_wildcard_mode_expects_the_wildcard_and_never_writes(make_settings, engine, integ):
    s = make_settings(dns_mode="wildcard")
    with Session(engine) as db:
        db.add(Business(name="Live", subdomain="liveshop", status="live", practice=False))
        db.commit()
        good = [{"type": "A", "name": "@", "data": IP}, {"type": "A", "name": "*", "data": IP}]
        assert compare(s, db, good) == []  # a live shop with no record of its own is exactly right here
        missing = compare(s, db, good[:1])
        assert [(f["kind"], f["name"], f["fix"]) for f in missing] == [("missing", "*", "manual")]
        wrong = compare(s, db, [{"type": "A", "name": "*", "data": "203.0.113.9"}])
        assert [(f["kind"], f["name"], f["fix"]) for f in wrong] == [("wrong_target", "*", "manual")]
        own = compare(s, db, good + [{"type": "A", "name": "liveshop", "data": "203.0.113.9"}])
        assert [(f["kind"], f["name"], f["fix"]) for f in own] == [("dangling", "liveshop", "manual")]
    integ.godaddy.zones["localhost"] = []
    found = scan(engine, s, integ.godaddy)
    assert [f.name for f in found] == ["*"]
    done = approve(engine, s, integ.godaddy, found[0].id, "team")
    assert done.status == "open" and done.result.startswith("failed")
    assert integ.godaddy.writes() == []
