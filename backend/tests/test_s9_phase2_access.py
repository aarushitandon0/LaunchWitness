"""Session 9F Phase 2: accounts, tenancy and access control.

- Every route is classified in `app/safety/route_table.py`, and each class really uses its gate.
- An authorization matrix over every OWNER route for: user A, user B, anonymous, guest, pending,
  suspended, a signed-in admin and the admin token.
- Sign-in links, sessions, CSRF/Origin, shop hosts, and the multi-seller rules.
"""

import json
import re
from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from app import accounts
from app.agents.claude_client import ClaudeUnavailable, FallbackClaudeClient
from app.config import Settings, get_settings
from app.db import get_session
from app.integrations import fake_integrations, get_integrations, get_practice_integrations
from app.mail.smtp import get_mailer
from app.main import create_app
from app.models import AuditEvent, Business, LoginToken, Membership, ShopReport, User, UserSession, utcnow
from app.routers.businesses import get_claude
from app.safety import route_table
from app.safety.access import csrf_for, sha
from app.tenancy import purge_old_guest_shops
from tests.conftest import ADMIN_TOKEN, AppClient, publish, ready_for_real, set_user, sign_in
from tests.test_m3_launch import SELLERS, approve, meera, plan

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
TEAM = "team@example.org"
GATES = {
    route_table.OWNER: {"require_business_access", "require_plan_access"},
    route_table.ADMIN: {"require_admin"},
    route_table.AUTH: {"require_user"},
}
OPTIONAL = {("MOUNT", "/assets")}  # only there when the frontend has been built


def events(engine, action):
    with Session(engine) as s:
        return s.exec(select(AuditEvent).where(AuditEvent.action == action)).all()


def make_app(make_settings, engine, mailer, claude, integ, practice=None, **settings_kw):
    if settings_kw.get("use_fakes") is False:
        settings_kw.setdefault("claude_mode", "live")  # a stand-in for the VPS, which runs live Claude
    settings = make_settings(**settings_kw)
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides.update({get_settings: lambda: settings, get_session: _session,
                                     get_mailer: lambda: mailer, get_claude: lambda: claude,
                                     get_integrations: lambda: integ,
                                     get_practice_integrations: lambda: practice or integ})
    return app, settings


@pytest.fixture
def team_app(make_settings, engine, mailer, claude, integ):
    app, _ = make_app(make_settings, engine, mailer, claude, integ, admin_email=TEAM)
    return app


@pytest.fixture
def browser(team_app):
    made = []

    def _make() -> AppClient:
        c = AppClient(team_app)
        c.__enter__()
        made.append(c)
        return c

    yield _make
    for c in made:
        c.__exit__(None, None, None)


# ---------- route classification ----------

def test_every_route_is_classified_and_uses_its_gate():
    app = create_app(run_lifespan=False)
    found = {(m, p): r for m, p, r in route_table.app_routes(app)}
    missing = sorted(k for k in found if k not in route_table.ROUTES)
    stale = sorted(k for k in route_table.ROUTES if k not in found and k not in OPTIONAL)
    assert missing == [], f"routes missing from route_table.ROUTES: {missing}"
    assert stale == [], f"stale entries in route_table.ROUTES: {stale}"
    for key, route in found.items():
        cls = route_table.ROUTES[key]
        if cls in GATES:
            assert route_table.gate_calls(route) & GATES[cls], f"{key} is {cls} but doesn't use {GATES[cls]}"
    owner = [k for k, c in route_table.ROUTES.items() if c == route_table.OWNER]
    assert len(owner) >= 15


def test_api_docs_are_switched_off(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert "openapi" not in client.get(path).text.lower()


# ---------- authorization matrix ----------

def owner_urls(biz_id: int, plan_id: int) -> list[tuple[str, str]]:
    out = []
    for (method, path), cls in route_table.ROUTES.items():
        if cls == route_table.OWNER:
            out.append((method, path.replace("{business_id}", str(biz_id)).replace("{plan_id}", str(plan_id))
                        .replace("{order_id}", "1")))
    return sorted(out)


def call(c, method, url, **kw):
    if method in ("POST", "PUT"):
        kw.setdefault("json", {})
    return c.request(method, url, **kw)


@pytest.fixture
def world(browser, engine):
    """User A (approved) with a launched practice shop, user B (approved) with their own, and the team."""
    a, b = browser(), browser()
    sign_in(a, "a@example.org")
    sign_in(b, "b@example.org")
    set_user(engine, "a@example.org", status="approved")
    set_user(engine, "b@example.org", status="approved")
    shop_a = meera(a, "shop-a")
    plan_a = approve(a, plan(a, shop_a))
    shop_b = meera(b, "shop-b")
    return {"a": a, "b": b, "shop_a": shop_a, "plan_a": plan_a, "shop_b": shop_b}


def test_matrix_owner_routes(world, browser, engine):
    a, b, shop_a, plan_a = world["a"], world["b"], world["shop_a"], world["plan_a"]
    urls = owner_urls(shop_a["id"], plan_a["id"])
    anon, guest = browser(), browser()
    meera(guest, "guest-shop")  # a guest with a workspace of its own
    counts = {"b_404": 0, "anon_401": 0, "guest_404": 0}
    for method, url in urls:
        r = call(b, method, url)
        assert r.status_code == 404 and r.json()["detail"] == "We couldn't find that shop.", (method, url, r.text)
        counts["b_404"] += 1
        assert call(anon, method, url).status_code == 401, (method, url)
        counts["anon_401"] += 1
        assert call(guest, method, url).status_code == 404, (method, url)
        counts["guest_404"] += 1
    # A can read every GET of their own (writes are covered by the flow tests)
    for method, url in urls:
        # S20: 404 until a customer attaches one (see test_s20); S21: the poster is 404 until the shop is live (test_s21)
        if method == "GET" and "payment-screenshot" not in url and not url.endswith("/poster"):
            assert a.get(url).status_code == 200, (url, a.get(url).text)
    assert all(v == len(urls) for v in counts.values())


def test_matrix_admin_reads_are_audited_and_token_works(world, browser, engine, new_client):
    shop_a, plan_a = world["shop_a"], world["plan_a"]
    team = browser()
    sign_in(team, TEAM)
    gets = [u for m, u in owner_urls(shop_a["id"], plan_a["id"])
            if m == "GET" and "payment-screenshot" not in u and not u.endswith("/poster")]
    before = len(events(engine, "admin_access"))
    for url in gets:
        assert team.get(url).status_code == 200, url
    rows = events(engine, "admin_access")
    assert len(rows) - before >= len(gets) and all(r.business_id == shop_a["id"] for r in rows[before:])
    cli = new_client()  # command line: no cookies, only the token
    for url in gets:
        assert cli.get(url, headers=ADMIN).status_code == 200, url
        assert cli.get(url).status_code == 401


def test_matrix_lists_only_own_shops(world, browser):
    a, b = world["a"], world["b"]
    assert [s["id"] for s in a.get("/api/businesses").json()] == [world["shop_a"]["id"]]
    assert [s["id"] for s in b.get("/api/businesses").json()] == [world["shop_b"]["id"]]
    assert browser().get("/api/businesses").json() == []
    assert a.get("/api/admin/businesses").status_code == 403


def test_matrix_pending_practises_but_cannot_launch_for_real(browser):
    c = browser()
    me = sign_in(c, "new@example.org")
    assert me["user"]["status"] == "pending"
    biz = meera(c, "pending-shop")
    r = c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True})
    assert r.status_code == 403
    assert approve(c, plan(c, biz))["status"] == "done"  # practice works


def test_matrix_suspended_user_is_locked_out_at_once(world, browser, engine):
    a, shop_a = world["a"], world["shop_a"]
    team = browser()
    sign_in(team, TEAM)
    uid = set_user(engine, "a@example.org")
    assert team.post(f"/api/admin/users/{uid}/suspend", json={"reason": "spam"}).status_code == 200
    assert a.get("/api/auth/me").json()["user"] is None  # the open session ended
    assert a.get(f"/api/businesses/{shop_a['id']}").status_code == 401
    assert a.get("/api/businesses").json() == []
    r = a.post("/api/auth/request-link", json={"email": "a@example.org"})
    assert r.status_code == 200 and "dev_link" not in r.json()  # no link is made for a suspended account
    with Session(engine) as s:
        assert all(row.revoked for row in s.exec(select(UserSession).where(UserSession.user_id == uid)).all())
    assert events(engine, "user_suspended")


# ---------- sign-in ----------

def test_signin_same_answer_for_known_unknown_and_suspended(make_settings, engine, mailer, claude, integ):
    app, _ = make_app(make_settings, engine, mailer, claude, integ, dev_mode=False)
    with Session(engine) as s:
        s.add(User(email="known@example.org", status="approved"))
        s.add(User(email="gone@example.org", status="suspended"))
        s.commit()
    with AppClient(app) as c:
        answers = [c.post("/api/auth/request-link", json={"email": e}).json()
                   for e in ("known@example.org", "nobody@example.org", "gone@example.org")]
    assert answers[0] == answers[1] == answers[2] and "dev_link" not in answers[0]
    assert sorted(m["to"] for m in mailer.sent) == ["known@example.org", "nobody@example.org"]
    with Session(engine) as s:
        assert s.exec(select(User).where(User.email == "nobody@example.org")).first() is None  # made at confirm only


def test_signin_token_hashed_single_use_expires_and_only_confirm_uses_it(client, engine):
    link = client.post("/api/auth/request-link", json={"email": "meera@example.org"}).json()["dev_link"]
    token = link.split("token=", 1)[1]
    assert "/#/signin/confirm?token=" in link
    with Session(engine) as s:
        row = s.exec(select(LoginToken)).one()
        assert row.token_hash == sha(token) and token not in row.model_dump_json()
        minutes = (accounts.aware(row.expires_at) - accounts.aware(row.created_at)).total_seconds() / 60
        assert 14.9 < minutes <= 15.01
    assert client.get("/").status_code == 200  # opening the link: the token sits after "#", so the server never sees it
    assert client.get("/api/auth/confirm").status_code in (404, 405)  # no GET that could use it up
    assert client.post("/api/auth/confirm", json={"token": token}).status_code == 200
    assert client.post("/api/auth/confirm", json={"token": token}).status_code == 400  # single use

    link = client.post("/api/auth/request-link", json={"email": "late@example.org"}).json()["dev_link"]
    late = link.split("token=", 1)[1]
    with Session(engine) as s:
        row = s.exec(select(LoginToken).where(LoginToken.token_hash == sha(late))).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        s.add(row)
        s.commit()
    r = client.post("/api/auth/confirm", json={"token": late})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["https://evil.example/", "//evil.example", "http:evil", "#//evil.example",
                                 "javascript:alert(1)", "#/x?y=https://evil", "/#/shops", "#/../../etc"])
def test_signin_next_refuses_anything_but_an_app_page(client, bad):
    link = client.post("/api/auth/request-link", json={"email": "m@example.org", "next": bad}).json()["dev_link"]
    assert "evil" not in link and "javascript" not in link and "&next=" not in link
    assert accounts.safe_next(bad) == "#/shops"


def test_signin_next_keeps_an_app_page(client):
    link = client.post("/api/auth/request-link", json={"email": "m@example.org", "next": "#/b/12"}).json()["dev_link"]
    assert link.endswith("&next=b/12")


def test_signin_limits_per_email_and_per_ip(make_settings, engine, mailer, claude, integ):
    app, _ = make_app(make_settings, engine, mailer, claude, integ, signin_links_per_email_per_day=2,
                      signin_links_per_ip_per_hour=4)
    with AppClient(app) as c:
        got = [c.post("/api/auth/request-link", json={"email": "m@example.org"}).json() for _ in range(3)]
        assert ["dev_link" in g for g in got] == [True, True, False]  # third: same answer, no link
        assert got[2]["message"] == got[0]["message"]
        for e in ("x@example.org", "y@example.org"):  # links 3 and 4 from this address
            assert "dev_link" in c.post("/api/auth/request-link", json={"email": e}).json()
        r = c.post("/api/auth/request-link", json={"email": "z@example.org"})
        assert r.status_code == 429 and "wait an hour" in r.json()["detail"]


def test_signin_smtp_down_says_so(make_settings, engine, claude, integ):
    class DownMailer:
        def send(self, **_kw):
            raise ConnectionRefusedError

    app, _ = make_app(make_settings, engine, DownMailer(), claude, integ, dev_mode=False)
    with AppClient(app) as c:
        r = c.post("/api/auth/request-link", json={"email": "m@example.org"})
    # S13: the link is kept in the outbox and retried; the answer says so and never says "sent"
    assert r.status_code == 200 and r.json()["mail_delayed"] is True
    assert r.json()["message"].startswith("We're having trouble sending email right now. We'll keep trying")
    assert "sent" not in r.json()["message"]
    assert [e.result for e in events(engine, "login_email")] == ["failed"]


# ---------- sessions ----------

def test_session_cookie_flags_in_production(make_settings, engine, mailer, claude, integ):
    app, settings = make_app(make_settings, engine, mailer, claude, integ, dev_mode=False,
                             app_base_url="https://launchwitness.com", app_domain="launchwitness.com")
    with Session(engine) as s:
        raw = accounts.issue_token(s, "m@example.org", "login")
    with AppClient(app, base_url="https://launchwitness.com") as c:
        r = c.post("/api/auth/confirm", json={"token": raw}, headers={"Origin": "https://launchwitness.com"})
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("__Host-lw_session=")
    low = cookie.lower()
    for flag in ("secure", "httponly", "samesite=lax", "path=/"):
        assert flag in low
    assert "domain=" not in low  # host-only: shop subdomains never receive it
    assert settings.guest_cookie == "__Host-lw_guest"


def test_session_new_id_each_sign_in_sliding_expiry_logout(client, new_client, engine):
    sign_in(client, "m@example.org")
    first = client.cookies.get("lw_session")
    sign_in(client, "m@example.org")
    second = client.cookies.get("lw_session")
    assert first and second and first != second
    with Session(engine) as s:
        row = s.exec(select(UserSession).where(UserSession.token_hash == sha(second))).one()
        assert (accounts.aware(row.expires_at) - utcnow()).days in (13, 14)  # 14 days, minus a moment (or none: coarse clocks)
        row.last_seen_at, row.expires_at = utcnow() - timedelta(minutes=11), utcnow() + timedelta(days=1)
        s.add(row)
        s.commit()
    assert client.get("/api/auth/me").json()["user"]["email"] == "m@example.org"
    with Session(engine) as s:
        row = s.exec(select(UserSession).where(UserSession.token_hash == sha(second))).one()
        assert (accounts.aware(row.expires_at) - utcnow()).days in (13, 14)  # slid forward
        row.expires_at = utcnow() - timedelta(seconds=1)
        s.add(row)
        s.commit()
    assert client.get("/api/auth/me").json()["user"] is None  # expired

    other = new_client()
    sign_in(client, "m@example.org")
    sign_in(other, "m@example.org")
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").json()["user"] is None
    assert other.get("/api/auth/me").json()["user"] is not None  # logout ends only this session
    third = new_client()
    sign_in(third, "m@example.org")
    assert other.post("/api/auth/logout-all").json()["ended"] >= 2
    assert third.get("/api/auth/me").json()["user"] is None and other.get("/api/auth/me").json()["user"] is None


# ---------- CSRF, Origin and hosts ----------

def test_csrf_and_origin(client, new_client, engine):
    sign_in(client, "m@example.org")
    biz = meera(client)
    url = f"/api/businesses/{biz['id']}/plans"
    body = {"mode": "sandbox"}
    token = csrf_for(client.cookies.get("lw_session"))
    assert client.post(url, json=body, headers={"Origin": "", "X-CSRF-Token": token}).status_code == 403  # no Origin
    assert client.post(url, json=body, headers={"Origin": "https://evil.example", "X-CSRF-Token": token}).status_code == 403
    assert client.post(url, json=body, headers={"X-CSRF-Token": ""}).status_code == 403  # cookie, no token
    assert client.post(url, json=body, headers={"X-CSRF-Token": "0" * 64}).status_code == 403  # wrong token
    assert client.post(url, json=body).status_code == 201  # right Origin + token

    cli = new_client()  # command line: no cookie, no Origin, the admin token
    r = cli.post(f"/api/admin/businesses/{biz['id']}/pause", json={"reason": "test"},
                 headers={**ADMIN, "Origin": ""})
    assert r.status_code == 200
    assert cli.post("/api/contact", json={}, headers={"Origin": "https://evil.example"}).status_code == 403


@pytest.mark.parametrize("path", ["/api/health", "/api/auth/me", "/internal/tls-ask?domain=x", "/assets/x.js",
                                  "/build", "/r/abc", "/api"])
def test_shop_host_never_serves_the_app(client, engine, path):
    publish(engine, meera(client)["id"])
    assert client.get(path, headers={"host": "meera.localhost"}).status_code == 404


def test_dev_mode_refuses_https(clean_env):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, dev_mode=True, app_base_url="https://launchwitness.com")


# ---------- multi-seller ----------

def test_guest_shops_kept_at_sign_in_up_to_the_limit(make_settings, engine, mailer, claude, integ):
    app, _ = make_app(make_settings, engine, mailer, claude, integ, max_shops_per_user=1)
    with AppClient(app) as c:
        first, second = meera(c, "guest-one"), meera(c, "guest-two")
        assert first["guest"] and second["guest"]
        assert sign_in(c, "m@example.org")["kept_shops"] == 1
        mine = [s["id"] for s in c.get("/api/businesses").json()]
        assert mine == [second["id"]]  # the newest one
        assert c.cookies.get("lw_guest") is None


def test_guest_shops_purged_after_a_day(client, new_client, engine, settings, integ):
    old, fresh = meera(client, "old-guest"), meera(client, "fresh-guest")
    owner = new_client()
    sign_in(owner, "m@example.org")
    kept = meera(owner, "owned")
    with Session(engine) as s:
        for bid in (old["id"], kept["id"]):
            b = s.get(Business, bid)
            b.created_at = utcnow() - timedelta(hours=25)
            s.add(b)
        s.commit()
    assert purge_old_guest_shops(engine, settings, integ) == 1
    with Session(engine) as s:
        assert s.get(Business, old["id"]) is None
        assert s.get(Business, fresh["id"]) and s.get(Business, kept["id"])


def test_max_three_shops_and_daily_describe_cap(client, make_settings):
    client.app.dependency_overrides[get_settings] = lambda: make_settings(user_describes_per_day=4)
    sign_in(client, "m@example.org")
    s = json.loads((SELLERS / "meera_cakes.json").read_text(encoding="utf-8"))
    data = {"description": s["description"], "price_list": s["price_list"]}
    ids = [client.post("/api/businesses", data=data).json()["id"] for _ in range(3)]
    r = client.post("/api/businesses", data=data)
    assert r.status_code == 409 and "3 shops" in r.json()["detail"]
    client.delete(f"/api/businesses/{ids[0]}")
    client.delete(f"/api/businesses/{ids[1]}")
    assert client.post("/api/businesses", data=data).status_code == 201  # 4th describe
    r = client.post("/api/businesses", data=data)
    assert r.status_code == 429  # deleting didn't give the describes back


@pytest.mark.parametrize("slug,ok", [("meera", True), ("www", False), ("api", False), ("admin", False),
                                     ("paytm-cakes", False), ("google", False), ("ab", False), ("-bad-", False)])
def test_slug_rules(client, slug, ok):
    biz = meera(client)
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": biz["profile"], "subdomain": slug})
    assert (r.status_code == 200) is ok, r.text


def test_report_shop_goes_to_the_queue_with_a_limit(client, new_client, engine, mailer):
    biz = meera(client)
    publish(engine, biz["id"])
    shopper = new_client()
    host = {"host": "meera.localhost"}
    assert "Report this shop" in shopper.get("/", headers=host).text
    for _ in range(3):
        assert shopper.post("/report-shop", data={"reason": "scam", "note": "asks for advance"}, headers=host).status_code == 200
    assert shopper.post("/report-shop", data={"reason": "scam"}, headers=host).status_code == 429
    assert shopper.post("/report-shop", data={"reason": "made-up"}, headers=host).status_code in (422, 429)
    queue = new_client().get("/api/admin/reports", headers=ADMIN).json()
    assert len(queue) == 3 and queue[0]["reason"] == "scam"
    with Session(engine) as s:
        assert all(r.visitor and "." not in r.visitor for r in s.exec(select(ShopReport)).all())  # hashed, not an IP
    assert any("Shop reported" in m["subject"] for m in mailer.sent)


def test_admin_pause_hides_the_shop_and_its_certificate(client, new_client, engine):
    biz = meera(client)
    publish(engine, biz["id"])
    host = {"host": "meera.localhost"}
    cli = new_client()
    assert cli.get("/internal/tls-ask", params={"domain": "meera.localhost"}).status_code == 200
    assert cli.post(f"/api/admin/businesses/{biz['id']}/pause", json={"reason": "reported"}, headers=ADMIN).status_code == 200
    page = cli.get("/", headers=host)
    assert "This shop is paused" in page.text and "Meera" not in page.text
    assert cli.get("/internal/tls-ask", params={"domain": "meera.localhost"}).status_code == 404
    assert cli.post(f"/api/admin/businesses/{biz['id']}/unpause", headers=ADMIN).status_code == 200
    assert "This shop is paused" not in cli.get("/", headers=host).text
    assert events(engine, "shop_paused") and events(engine, "shop_unpaused")


# ---------- real launches: live-shop cap and policy check ----------

def real_world(make_settings, engine, mailer, claude, **kw):
    server, practice = fake_integrations(make_settings()), fake_integrations(make_settings())
    server.fake = False
    app, settings = make_app(make_settings, engine, mailer, claude, server, practice=practice, use_fakes=False, **kw)
    return app, server


def approved_shop(c, engine, email="m@example.org", sub="meera"):
    sign_in(c, email)
    set_user(engine, email, status="approved")
    return meera(c, sub)


def real_approve(c, biz):
    ready_for_real(c, biz["id"])
    p = c.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "real": True})
    assert p.status_code == 201, p.text
    return c.post(f"/api/plans/{p.json()['id']}/approve", json={"approved_by": "M"})


def test_live_shop_cap(make_settings, engine, mailer, claude):
    app, server = real_world(make_settings, engine, mailer, claude, max_live_shops=1)
    with Session(engine) as s:
        s.add(Business(name="Other", subdomain="other", status="live", practice=False))
        s.commit()
    with AppClient(app) as c:
        r = real_approve(c, approved_shop(c, engine))
    assert r.status_code == 409 and "live shops" in r.json()["detail"]
    assert server.godaddy.writes() == []


class Says:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    def ask_json(self, **kw):
        if kw["fixture"] != "policy_ok":
            from app.agents.claude_client import FixtureClaudeClient
            return FixtureClaudeClient().ask_json(**kw)
        if self.error:
            raise self.error
        return self.reply


@pytest.mark.parametrize("claude_like", [
    Says({"ok": False, "reason": "This shop looks like it pretends to be a famous brand."}),
    Says(error=ClaudeUnavailable("down")),  # can't ask: held (fail closed)
    FallbackClaudeClient(Says(error=ClaudeUnavailable("down"))),  # live mode never answers from the saved sample
])
def test_policy_hold_blocks_a_real_launch(make_settings, engine, mailer, claude_like):
    app, server = real_world(make_settings, engine, mailer, claude_like)
    with AppClient(app) as c:
        biz = approved_shop(c, engine)
        r = real_approve(c, biz)
        assert r.status_code == 409 and "Nothing was launched" in r.json()["detail"]
    assert server.godaddy.writes() == []
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).review == "held"
    assert events(engine, "policy_check")[-1].result == "held"


def test_policy_ok_and_team_can_clear_a_hold(make_settings, engine, mailer):
    held = Says({"ok": False, "reason": "Unclear."})
    app, server = real_world(make_settings, engine, mailer, held)
    with AppClient(app) as c:
        biz = approved_shop(c, engine)
        assert real_approve(c, biz).status_code == 409
        assert c.post(f"/api/admin/businesses/{biz['id']}/clear-review", headers=ADMIN).status_code == 200
        assert real_approve(c, biz).status_code == 200  # the team looked: no second policy call
    assert server.godaddy.writes() == [("set_records", "localhost", "A", "meera")]
    assert events(engine, "shop_review_cleared")


# ---------- account deletion ----------

def test_account_delete_needs_the_link_and_being_signed_in(make_settings, engine, mailer, claude):
    app, server = real_world(make_settings, engine, mailer, claude)
    with AppClient(app) as c, AppClient(app) as other:
        biz = approved_shop(c, engine)
        assert real_approve(c, biz).status_code == 200
        assert c.get("/", headers={"host": "meera.localhost"}).status_code == 200  # live
        link = c.post("/api/account/delete-request").json()["dev_link"]
        token = link.split("token=", 1)[1]
        assert other.post("/api/account/delete", json={"token": token}).status_code == 401  # not signed in
        sign_in(other, "x@example.org")
        assert other.post("/api/account/delete", json={"token": token}).status_code == 400  # not their link...
        with Session(engine) as s:  # ...and trying it didn't use up the owner's link
            assert s.exec(select(LoginToken).where(LoginToken.token_hash == sha(token))).one().used_at is None
        assert c.post("/api/account/delete", json={"token": "nope"}).status_code == 400
        assert c.post("/api/account/delete", json={"token": token}).json() == {"ok": True}
        assert c.get("/api/auth/me").json()["user"] is None
        assert c.get("/", headers={"host": "meera.localhost"}).status_code == 404  # unpublished
    assert ("delete_records", "localhost", "A", "meera") in server.godaddy.calls
    with Session(engine) as s:
        assert s.get(Business, biz["id"]) is None
        assert s.exec(select(Membership).where(Membership.business_id == biz["id"])).all() == []
        user = s.exec(select(User).where(User.status == "deleted")).one()
        assert user.email.endswith("@deleted.invalid")
        rows = s.exec(select(AuditEvent)).all()
        dump = " ".join(r.model_dump_json() for r in rows)
        assert "m@example.org" not in dump and "Meera" not in dump
        assert len([r for r in rows if r.action == "account_deleted"]) == 1


def test_every_admin_action_is_audited(world, browser, engine):
    team = browser()
    sign_in(team, TEAM)
    pending = browser()
    sign_in(pending, "p@example.org")
    pid = set_user(engine, "p@example.org")
    sid = world["shop_b"]["id"]
    with Session(engine) as s:
        s.add(ShopReport(business_id=sid, reason="other"))
        s.commit()
        rid = s.exec(select(ShopReport)).one().id
    steps = [("post", f"/api/admin/users/{pid}/approve", None, "user_approved"),
             ("post", f"/api/admin/users/{pid}/reject", {"reason": "no"}, "user_rejected"),
             ("post", f"/api/admin/businesses/{sid}/pause", {"reason": "x"}, "shop_paused"),
             ("post", f"/api/admin/businesses/{sid}/unpause", None, "shop_unpaused"),
             ("post", f"/api/admin/businesses/{sid}/clear-review", None, "shop_review_cleared"),
             ("post", f"/api/admin/reports/{rid}/close", {"reason": "ok"}, "report_closed"),
             ("get", "/api/admin/users", None, "admin_list_users"),
             ("get", "/api/admin/businesses", None, "admin_list_shops")]
    for verb, url, body, action in steps:
        r = team.get(url) if verb == "get" else team.post(url, json=body or {})
        assert r.status_code == 200, (url, r.text)
        rows = events(engine, action)
        assert rows and rows[-1].user_id is not None, action


def test_two_users_never_see_each_other(world):
    b, shop_a = world["b"], world["shop_a"]
    r = b.get(f"/api/businesses/{shop_a['id']}/report")
    assert r.status_code == 404 and r.json()["detail"] == "We couldn't find that shop."
    assert not re.search(r"shop-a", json.dumps(b.get("/api/businesses").json()))
