"""Session 9F Phase 3: the order proof chain, shared reports, and "Check any address"."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlmodel import Session, select

from app import proof
from app.checks.dns_resolver import AuthoritativeResolver
from app.checks.safe_fetch import Page, Refused, SafeWeb
from app.models import AddressCheck, AuditEvent, Business, Evidence, Order, ReportShare, TestTicket
from app.routers.health import mailbox_warning
from app.routers.proof import get_public_dns, get_public_web
from tests.conftest import publish, set_user, sign_in
from tests.test_m3_launch import approve, meera, plan
from tests.test_m4_report import real_plan, two_worlds_client
from tests.test_s9_phase2_access import make_app


def report(c, biz):
    r = c.get(f"/api/businesses/{biz['id']}/report")
    assert r.status_code == 200, r.text
    return r.json()


def hops(engine, check="test_order"):
    with Session(engine) as s:
        return [e.step for e in s.exec(select(Evidence).where(Evidence.check == check).order_by(Evidence.id)).all()]


# ---------- hops recorded separately, practice labelled ----------

def test_practice_launch_records_each_hop_with_times(client, engine):
    biz = meera(client)
    approve(client, plan(client, biz))
    assert hops(engine) == ["form_post", "smtp_accepted", "imap_seen"]
    assert hops(engine, "site_points") == ["dns_answer"] and hops(engine, "https") == ["http_response"]
    with Session(engine) as s:
        rows = s.exec(select(Evidence)).all()
        assert all(e.practice for e in rows)  # pretend world: always labelled
        smtp = next(e for e in rows if e.step == "smtp_accepted")
        assert smtp.message_id and smtp.nonce and smtp.server == "pretend mail server"
        assert next(e for e in rows if e.step == "dns_answer").server == "pretend nameserver"
    rep = report(client, biz)
    assert rep["practice"] is True and rep["proof"]["proven"] == rep["proof"]["total"] == 7
    test = next(c for c in rep["run"]["checks"] if c["check"] == "test_order")
    assert [h["title"] for h in test["hops"]] == ["Form accepted", "Mail server accepted", "In the inbox"]
    assert all(h["at"] for h in test["hops"]) and rep["proof"]["stale"] is False


def test_test_order_goes_through_the_public_form_and_stays_hidden(client, engine):
    biz = meera(client)
    approve(client, plan(client, biz))
    with Session(engine) as s:
        order = s.exec(select(Order)).one()
        ticket = s.exec(select(TestTicket)).one()
        assert order.is_test and order.nonce == ticket.nonce and ticket.order_id == order.id and ticket.used_at
        assert order.client_token  # the form's own hidden token was posted back, like a browser does
    assert client.get(f"/api/businesses/{biz['id']}/orders").json() == []  # hidden from the seller's list


def test_new_code_every_run_and_old_emails_never_pass(client, engine, integ):
    biz = meera(client)
    approve(client, plan(client, biz))
    first = integ.inbox.messages[-1]
    integ.mailer.drop = True  # the next test email never arrives...
    integ.inbox.deliver(sender="x", to="y", subject=first.subject, body="old copy",
                        at=datetime.now(UTC) - timedelta(days=2))  # ...but an old one with an old code is there
    client.post(f"/api/businesses/{biz['id']}/checks")
    rep = report(client, biz)
    test = next(c for c in rep["run"]["checks"] if c["check"] == "test_order")
    assert test["passed"] is False and "hasn't arrived" in test["plain"]
    with Session(engine) as s:
        nonces = [t.nonce for t in s.exec(select(TestTicket)).all()]
    assert len(nonces) == 2 and len(set(nonces)) == 2


def test_imap_lookup_uses_since(client, integ):
    seen = []
    real_find = integ.inbox.find

    def find(*, subject_contains, since=None):
        seen.append(since)
        return real_find(subject_contains=subject_contains, since=since)

    integ.inbox.find = find
    approve(client, plan(client, meera(client)))
    assert seen and all(s is not None and datetime.now(UTC) - s < timedelta(minutes=5) for s in seen)


# ---------- accepted is never delivered ----------

def test_accepted_is_not_delivered_until_the_owner_taps(make_settings, engine, mailer, claude):
    c, server, _practice = two_worlds_client(make_settings, engine, mailer, claude)
    with c:
        sign_in(c, "meera@example.org")
        set_user(engine, "meera@example.org", status="approved")
        biz = meera(c)
        approve(c, real_plan(c, biz))
        assert hops(engine) == ["form_post", "smtp_accepted"]  # no inbox we can read: no "delivered"
        rep = report(c, biz)
        test = next(x for x in rep["run"]["checks"] if x["check"] == "test_order")
        assert test["state"] == "needs_you" and "accepted" in test["plain"]
        assert "arrived" not in test["plain"] and rep["ready"] is False
        mail = next(m for m in server.mailer.sent if "[TEST]" in m["subject"])
        token = mail["body"].split("#/got-it?token=", 1)[1].split()[0]
        assert c.get("/").status_code == 200  # opening the link's page uses nothing up
        assert c.post("/api/proof/confirm", json={"token": token}).status_code == 200
        assert c.post("/api/proof/confirm", json={"token": token}).status_code == 400  # single use
        assert c.post("/api/proof/confirm", json={"token": "made-up"}).status_code == 400
        assert hops(engine) == ["form_post", "smtp_accepted", "owner_confirmed"]
        assert report(c, biz)["ready"] is True


def test_lw_test_field_only_works_with_an_open_ticket_for_that_shop(client, new_client, engine):
    biz = meera(client)
    publish(engine, biz["id"])
    other = meera(new_client(), "other")
    with Session(engine) as s:
        b_other = s.get(Business, other["id"])
        ticket = proof.new_ticket(s, b_other, None)
        nonce = ticket.nonce
    shopper = new_client()
    form = {"customer_name": "Priya", "customer_phone": "9876543210", "qty_0": "1", "order_token": "a" * 20}
    r = shopper.post("/order", data={**form, "lw_test": nonce}, headers={"host": "meera.localhost"})
    assert r.status_code == 200
    with Session(engine) as s:
        order = s.exec(select(Order)).one()
        assert order.is_test is False  # another shop's ticket: just a normal customer order
        assert s.exec(select(TestTicket)).one().used_at is None


# ---------- the shop marker and the certificate wait ----------

def test_https_needs_the_shop_marker(client, integ, engine):
    class Parked(proof.PracticeShopWeb):
        def get(self, url):
            return Page(200, "<html>Domain parked</html>", url)

    integ.shop_web = lambda ctx: Parked(ctx.session, ctx.settings, ctx.integ.mailer, ctx.business, ctx.plan.site_host)
    biz = meera(client)
    approve(client, plan(client, biz))
    https = next(c for c in report(client, biz)["run"]["checks"] if c["check"] == "https")
    assert https["passed"] is False and "isn't your shop" in https["plain"]


def test_https_waits_for_a_new_certificate(client, integ):
    from app.checks.http_probe import ProbeResult

    naps, real, calls = [], integ.http.fetch, {"n": 0}
    integ.sleep = naps.append

    def fetch(url):
        calls["n"] += 1
        return ProbeResult(False, None, False, error="certificate verify failed") if calls["n"] <= 2 else real(url)

    integ.http.fetch = fetch
    biz = meera(client)
    approve(client, plan(client, biz))
    https = next(c for c in report(client, biz)["run"]["checks"] if c["check"] == "https")
    assert https["passed"] is True and naps[:2] == [5, 10]
    from app.agents.checker import HTTPS_BACKOFF

    assert sum(HTTPS_BACKOFF) <= 120


def test_shop_page_carries_its_marker(client, engine):
    biz = meera(client)
    publish(engine, biz["id"])
    assert '<meta name="lw-shop" content="meera">' in client.get("/", headers={"host": "meera.localhost"}).text


# ---------- SSRF guard ----------

def guarded(routes: dict, ips: dict, allow=lambda h: True):
    seen = []

    def handler(request: httpx.Request):
        seen.append((str(request.url), request.headers.get("host"), request.extensions.get("sni_hostname")))
        return routes.get(request.headers["host"] + request.url.path, httpx.Response(200, text="ok"))

    web = SafeWeb(allow, resolve=lambda h: ips.get(h, []), transport=httpx.MockTransport(handler))
    return web, seen


def test_ssrf_guard_pins_the_checked_public_address():
    web, seen = guarded({}, {"shop.example.com": ["93.184.216.34"]})
    page = web.get("https://shop.example.com/menu?x=1")
    assert page.status == 200 and page.server == "93.184.216.34"
    assert seen == [("https://93.184.216.34/menu?x=1", "shop.example.com", "shop.example.com")]


@pytest.mark.parametrize("url,ips,why", [
    ("https://10.0.0.5/", {}, "isn't a web address"),
    ("https://[::1]/", {}, "isn't a web address"),
    ("http://shop.example.com/", {"shop.example.com": ["93.184.216.34"]}, "secure"),
    ("https://shop.example.com:8443/", {"shop.example.com": ["93.184.216.34"]}, "secure"),
    ("https://inside.example.com/", {"inside.example.com": ["10.1.2.3"]}, "private"),
    ("https://loop.example.com/", {"loop.example.com": ["127.0.0.1"]}, "private"),
    ("https://meta.example.com/", {"meta.example.com": ["169.254.169.254"]}, "private"),
    ("https://mixed.example.com/", {"mixed.example.com": ["93.184.216.34", "192.168.1.1"]}, "private"),
    ("https://nowhere.example.com/", {}, "doesn't lead"),
])
def test_ssrf_guard_refuses(url, ips, why):
    web, seen = guarded({}, ips)
    with pytest.raises(Refused, match=why):
        web.get(url)
    assert seen == []


@pytest.mark.parametrize("location", ["https://10.0.0.1/", "http://shop.example.com/x", "https://evil.example.org/",
                                      "https://internal.example.com/"])
def test_ssrf_guard_checks_every_redirect(location):
    ips = {"shop.example.com": ["93.184.216.34"], "evil.example.org": ["93.184.216.35"],
           "internal.example.com": ["10.0.0.9"]}
    routes = {"shop.example.com/": httpx.Response(302, headers={"location": location})}
    web, _seen = guarded(routes, ips, allow=lambda h: h in ("shop.example.com", "internal.example.com"))
    with pytest.raises(Refused):
        web.get("https://shop.example.com/")


def test_ssrf_guard_gives_up_on_redirect_loops():
    routes = {"shop.example.com/": httpx.Response(302, headers={"location": "/"})}
    web, seen = guarded(routes, {"shop.example.com": ["93.184.216.34"]})
    with pytest.raises(Refused, match="circles"):
        web.get("https://shop.example.com/")
    assert len(seen) == 4


def test_checker_web_only_allows_the_shop_itself():
    web = proof.real_shop_web("meera.launchwitness.com")
    assert web.allow("meera.launchwitness.com") and not web.allow("launchwitness.com")
    assert not web.allow("other.launchwitness.com")


# ---------- shared report ----------

def test_shared_report_is_read_only_revocable_and_has_no_customer_data(client, new_client, engine):
    biz = meera(client)
    approve(client, plan(client, biz))
    publish(engine, biz["id"])
    new_client().post("/order", data={"customer_name": "Priya Sharma", "customer_phone": "9876543210", "qty_0": "1",
                                      "order_token": "b" * 20}, headers={"host": "meera.localhost"})
    url = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]
    path = "/r/" + url.rsplit("/r/", 1)[1]
    visitor = new_client()
    page = visitor.get(path)
    assert page.status_code == 200 and "of 7 proven" in page.text and "Eggless" in page.text
    assert "Priya" not in page.text and "9876543210" not in page.text and "meera@" not in page.text
    assert "Mail server accepted" in page.text and "IST" in page.text
    with Session(engine) as s:
        assert url.rsplit("/", 1)[1] not in s.exec(select(ReportShare)).one().model_dump_json()  # hash only
    assert client.get(f"/api/businesses/{biz['id']}/share").json()["active"] is True
    url2 = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]  # a new link stops the old one
    assert visitor.get(path).status_code == 404
    assert client.delete(f"/api/businesses/{biz['id']}/share").json() == {"ok": True}
    assert visitor.get("/r/" + url2.rsplit("/r/", 1)[1]).status_code == 404
    assert visitor.get("/r/" + url2.rsplit("/r/", 1)[1], headers={"host": "meera.localhost"}).status_code == 404


def test_shared_report_labels_practice(client, new_client):
    biz = meera(client)
    approve(client, plan(client, biz))
    url = client.post(f"/api/businesses/{biz['id']}/share").json()["url"]
    assert "Practice" in new_client().get("/r/" + url.rsplit("/r/", 1)[1]).text


def test_proof_rows_go_with_a_deleted_shop(client, engine):
    biz = meera(client)
    approve(client, plan(client, biz))
    client.post(f"/api/businesses/{biz['id']}/share")
    assert client.delete(f"/api/businesses/{biz['id']}").status_code == 200
    with Session(engine) as s:
        for table in (Evidence, TestTicket, ReportShare):
            assert s.exec(select(table)).all() == []


# ---------- check any address ----------

class FakeDns:
    def __init__(self, records):
        self.records = records

    def resolve(self, name, rtype):
        return list(self.records.get((name, rtype), []))


class FakeWeb:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return Page(200, "<html></html>", url)

    def cert_not_after(self, host):
        return datetime.now(UTC) + timedelta(days=30, hours=1)


@pytest.fixture
def checker_app(make_settings, engine, mailer, claude, integ):
    app, _ = make_app(make_settings, engine, mailer, claude, integ, address_checks_per_hour=3)
    web = FakeWeb()
    app.dependency_overrides[get_public_web] = lambda: web
    app.dependency_overrides[get_public_dns] = lambda: FakeDns({
        ("shop.example.com", "A"): ["93.184.216.34"], ("shop.example.com", "MX"): ["10 mx.example.com."],
        ("shop.example.com", "TXT"): ['"v=spf1 ip4:93.184.216.34 -all"'], ("mx.example.com", "A"): ["93.184.216.40"]})
    return app, web


def test_check_any_address_plain_and_read_only(checker_app, engine, mailer):
    from tests.conftest import AppClient

    app, web = checker_app
    with AppClient(app) as c:
        r = c.post("/api/check-address", json={"address": "https://Shop.Example.com/menu"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["address"] == "shop.example.com" and body["read_only"] is True
    res = {x["check"]: x for x in body["results"]}
    assert res["address"]["ok"] and res["https"]["ok"] and res["email_mx"]["ok"] and res["email_spf"]["ok"]
    assert res["email_dmarc"]["ok"] is False and "fake emails" in res["email_dmarc"]["plain"]
    assert "30 more days" in res["certificate"]["plain"]
    assert web.urls == ["https://shop.example.com/"]
    assert mailer.sent == []  # never emails anyone
    with Session(engine) as s:
        assert len(s.exec(select(AddressCheck)).all()) == 1
        assert "shop.example.com" not in " ".join(e.model_dump_json() for e in s.exec(select(AuditEvent)).all())


@pytest.mark.parametrize("bad", ["10.0.0.1", "http://127.0.0.1/", "localhost", "printer.local", "", "not an address"])
def test_check_any_address_refuses_non_addresses(checker_app, bad):
    from tests.conftest import AppClient

    with AppClient(checker_app[0]) as c:
        assert c.post("/api/check-address", json={"address": bad}).status_code == 422


def test_check_any_address_is_rate_limited(checker_app):
    from tests.conftest import AppClient

    with AppClient(checker_app[0]) as c:
        codes = [c.post("/api/check-address", json={"address": "shop.example.com"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# ---------- small items ----------

def test_thank_you_page_sends_the_order_to_the_shop_on_whatsapp(client, new_client, engine):
    biz = meera(client)
    profile = {**biz["profile"], "whatsapp": "9876543210"}
    client.put(f"/api/businesses/{biz['id']}", json={"profile": profile, "subdomain": "meera"})
    publish(engine, biz["id"])
    page = new_client().post("/order", data={"customer_name": "Priya", "customer_phone": "9876543210", "qty_0": "2",
                                             "order_token": "c" * 20}, headers={"host": "meera.localhost"}).text
    assert "Send this order to the shop" in page and "https://wa.me/919876543210?text=" in page
    with Session(engine) as s:
        ref = s.exec(select(Order)).one().ref
    assert ref in page.split("wa.me/", 1)[1].split('"', 1)[0]


def test_mailbox_expiry_warning(make_settings, client):
    s = make_settings(mailbox_expires_on=date(2026, 12, 15))
    assert mailbox_warning(s, today=date(2026, 11, 16)) is None
    assert "lapses in 14 day" in mailbox_warning(s, today=date(2026, 12, 1))
    assert "has lapsed" in mailbox_warning(s, today=date(2026, 12, 20))
    assert "warnings" not in client.get("/api/health").json()


def test_daily_monitoring_includes_a_test_order():
    from app.monitor.scheduler import daily_checks

    assert "test_order" in daily_checks("sandbox")


def test_authoritative_resolver_asks_the_zone_nameservers():
    class Finder:
        def resolve(self, name, rtype):
            return {("meera.launchwitness.com", "NS"): [], ("launchwitness.com", "NS"): ["ns2.domaincontrol.com.",
                                                                                         "ns1.domaincontrol.com."],
                    ("ns1.domaincontrol.com", "A"): ["97.74.100.1"],
                    ("ns2.domaincontrol.com", "A"): ["173.201.68.1"]}.get((name, rtype), [])

    asked = []

    def query(name, rtype, ip):
        asked.append(ip)
        if ip == "97.74.100.1":
            raise TimeoutError
        return ["203.0.113.7"]

    r = AuthoritativeResolver(finder=Finder(), query=query)
    assert r.resolve("meera.launchwitness.com", "A") == ["203.0.113.7"]
    assert asked == ["97.74.100.1", "173.201.68.1"] and r.last_server == "ns2.domaincontrol.com (173.201.68.1)"


# ---------- S11 review: a page can't make us read without end ----------

def test_safe_web_stops_reading_a_huge_page():
    from app.checks import safe_fetch
    sent = []

    def endless():
        for _ in range(400):  # 400 x 64 KB = 25 MB if nobody stops us
            sent.append(1)
            yield b"a" * 65536

    web = SafeWeb(lambda h: True, resolve=lambda h: ["93.184.216.34"],
                  transport=httpx.MockTransport(lambda req: httpx.Response(200, content=endless())))
    page = web.get("https://big.example.com/")
    assert page.status == 200 and len(page.html) == safe_fetch.MAX_BODY
    assert len(sent) <= safe_fetch.MAX_BODY // 65536 + 2


def test_safe_web_gives_up_on_a_page_that_drips_forever(monkeypatch):
    from app.checks import safe_fetch
    clock = iter(range(0, 100000, 7))  # every look at the clock is 7 "seconds" later
    monkeypatch.setattr(safe_fetch, "now", lambda: next(clock))

    def drip():
        for _ in range(1000):
            yield b"a"

    web = SafeWeb(lambda h: True, resolve=lambda h: ["93.184.216.34"],
                  transport=httpx.MockTransport(lambda req: httpx.Response(200, content=drip())))
    page = web.get("https://slow.example.com/")
    assert page.status is None and page.error == "TooSlow"
