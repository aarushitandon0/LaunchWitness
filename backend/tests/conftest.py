"""Shared test fixtures.

- Settings are built from defaults only (no `.env`, no real env vars).
- The DB is an in-memory SQLite.
- Any network connection to a non-local address fails the test (`no_network`, autouse).
"""

import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.agents.claude_client import FixtureClaudeClient
from app.config import Settings, get_settings
from app.db import get_session, init_db, make_engine
from app.integrations import Integrations, fake_integrations, get_integrations, get_practice_integrations
from app.mail.smtp import FakeMailer, get_mailer
from app.main import create_app
from app.routers.businesses import get_claude
from app.safety.access import csrf_for

ADMIN_TOKEN = "test-admin-token-0123456789"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


class NetworkBlocked(RuntimeError):
    pass


def _host_of(address) -> str | None:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None  # unix sockets etc.


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request) -> list[str]:
    """Block (and record) every non-local connection. Returns the list of blocked hosts."""
    blocked: list[str] = []
    if request.node.get_closest_marker("network"):  # the opt-in real-network run (pytest -m network): read-only
        return blocked

    # A local proxy would turn a "localhost" connection into a real outbound one.
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guard(host):
        if host is not None and host not in _LOCAL_HOSTS:
            blocked.append(host)
            raise NetworkBlocked(f"Real network call attempted in a test: {host}")

    def connect(self, address):
        guard(_host_of(address))
        return real_connect(self, address)

    def connect_ex(self, address):
        guard(_host_of(address))
        return real_connect_ex(self, address)

    def getaddrinfo(host, *args, **kwargs):
        guard(host if isinstance(host, str) else None)
        return real_getaddrinfo(host, *args, **kwargs)

    real_sendto = socket.socket.sendto

    def sendto(self, data, *args):
        guard(_host_of(args[-1]) if args else None)  # UDP (e.g. DNS queries)
        return real_sendto(self, data, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return blocked


@pytest.fixture
def clean_env(monkeypatch):
    """Remove any real env vars that map to Settings fields."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def make_settings(clean_env):
    def _make(**overrides) -> Settings:
        overrides.setdefault("database_url", "sqlite://")
        overrides.setdefault("monitor_enabled", False)
        overrides.setdefault("monitor_workers", 1)  # the in-memory test DB is ONE shared connection (S13 B scale tests use a file)
        overrides.setdefault("admin_token", ADMIN_TOKEN)
        overrides.setdefault("visitor_describes_per_day", 1000)  # limit tests set these low explicitly
        overrides.setdefault("visitor_launches_per_day", 1000)
        overrides.setdefault("signin_links_per_ip_per_hour", 1000)
        overrides.setdefault("dev_mode", True)  # plain-http cookies + sign-in link returned instead of emailed
        return Settings(_env_file=None, **overrides)

    return _make


@pytest.fixture
def settings(make_settings) -> Settings:
    return make_settings()


@pytest.fixture
def engine(settings) -> Engine:
    eng = make_engine(settings.database_url)
    init_db(eng)
    return eng


@pytest.fixture
def session(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def mailer(integ) -> FakeMailer:
    """The pretend world's mailer (shop orders, alerts) is also the app's own mailer in tests."""
    return integ.mailer


def publish_client(client, business_id: int) -> None:
    """`publish` for tests that only hold the TestClient."""
    gen = client.app.dependency_overrides[get_session]()
    publish(next(gen).get_bind(), business_id)
    gen.close()


def publish(engine: Engine, business_id: int) -> None:
    """Make a shop public the way a real (non-practice) launch does: live, not practice, and its
    launches count as real (practice results never count for a real shop)."""
    from sqlmodel import select

    from app.models import Business, Plan

    with Session(engine) as s:
        b = s.get(Business, business_id)
        b.status, b.practice = "live", False
        s.add(b)
        for p in s.exec(select(Plan).where(Plan.business_id == business_id)).all():
            p.practice = False
            s.add(p)
        s.commit()


@pytest.fixture
def claude() -> FixtureClaudeClient:
    return FixtureClaudeClient()


@pytest.fixture
def integ(settings) -> Integrations:
    """A fresh fake world (GoDaddy, availability, mailbox, DNS, HTTP) with no real sleeping."""
    return fake_integrations(settings)


@pytest.fixture
def app(settings, engine, mailer, claude, integ):
    application = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_session] = _session
    application.dependency_overrides[get_mailer] = lambda: mailer
    application.dependency_overrides[get_claude] = lambda: claude
    application.dependency_overrides[get_integrations] = lambda: integ
    application.dependency_overrides[get_practice_integrations] = lambda: integ
    return application


ORIGIN = "http://localhost"  # = Settings.origin with the default APP_BASE_URL


class AppClient(TestClient):
    """A browser on the app's own pages: state-changing /api calls carry the app's Origin and, when a
    session or guest cookie exists, the matching CSRF token. Pass a header explicitly (even "") to override."""

    def request(self, method, url, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and str(url).startswith("/api/"):
            low = {k.lower() for k in headers} | {k.lower() for k in self.headers}
            if "origin" not in low:
                headers["Origin"] = ORIGIN
            cookie = self.cookies.get("lw_session") or self.cookies.get("lw_guest")
            if cookie and "x-csrf-token" not in low:
                headers["X-CSRF-Token"] = csrf_for(cookie)
        return super().request(method, url, headers=headers, **kw)


@pytest.fixture
def new_client(app):
    """Factory: each call is a separate browser (its own cookies) on the same app."""
    made = []

    def _make() -> AppClient:
        c = AppClient(app)
        c.__enter__()
        made.append(c)
        return c

    yield _make
    for c in made:
        c.__exit__(None, None, None)


@pytest.fixture
def client(new_client) -> AppClient:
    return new_client()


def sign_in(client, email: str) -> dict:
    """Ask for a link, then press "Sign in" on the confirm page (DEV_MODE returns the link instead of emailing it)."""
    r = client.post("/api/auth/request-link", json={"email": email})
    assert r.status_code == 200, r.text
    token = r.json()["dev_link"].split("token=", 1)[1].split("&", 1)[0]
    r = client.post("/api/auth/confirm", json={"token": token})
    assert r.status_code == 200, r.text
    return r.json()


def set_user(engine: Engine, email: str, **fields) -> int:
    """Change a user row directly (e.g. status="approved"), as the admin pages would."""
    from sqlmodel import select

    from app.models import User

    with Session(engine) as s:
        u = s.exec(select(User).where(User.email == email)).one()
        for k, v in fields.items():
            setattr(u, k, v)
        s.add(u)
        s.commit()
        return u.id


GO_LIVE = {"whatsapp": "98765 43210", "upi_id": "meera.cakes@okaxis", "upi_display_name": "Meera Joshi",
           "pickup_available": True, "area": "Baner, Pune", "delivery_areas": "Baner, Aundh",
           "hours": "Tue-Sun, 10am-7pm"}


def ready_for_real(client, business_id: int, **profile) -> dict:
    """Do the S10.5 go-live checklist as the owner would: fill the details, open the preview, test the WhatsApp
    number, do the UPI name test, tick the two boxes. (Sign-in, shop name and a priced item are already there.)"""
    biz = client.get(f"/api/businesses/{business_id}").json()
    r = client.put(f"/api/businesses/{business_id}",
                   json={"profile": {**biz["profile"], **GO_LIVE, **profile}, "subdomain": biz["subdomain"]})
    assert r.status_code == 200, r.text
    assert client.get(f"/api/businesses/{business_id}/preview").status_code == 200
    for body in ({"what": "whatsapp"}, {"what": "upi"}, {"what": "agreements", "own_goods": True, "terms": True}):
        r = client.post(f"/api/businesses/{business_id}/confirm", json=body)
        assert r.status_code == 200, r.text
    out = client.get(f"/api/businesses/{business_id}/golive").json()
    assert out["ready"], out
    return out
