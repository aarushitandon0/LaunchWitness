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
from app.integrations import Integrations, fake_integrations, get_integrations, get_practice_integrations
from app.mail.smtp import FakeMailer, get_mailer
from app.routers.businesses import get_claude
from app.db import get_session, init_db, make_engine
from app.main import create_app

ADMIN_TOKEN = "test-admin-token-0123456789"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


class NetworkBlocked(RuntimeError):
    pass


def _host_of(address) -> str | None:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return None  # unix sockets etc.


@pytest.fixture(autouse=True)
def no_network(monkeypatch) -> list[str]:
    """Block (and record) every non-local connection. Returns the list of blocked hosts."""
    blocked: list[str] = []

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
        overrides.setdefault("admin_token", ADMIN_TOKEN)
        overrides.setdefault("visitor_describes_per_day", 1000)  # limit tests set these low explicitly
        overrides.setdefault("visitor_launches_per_day", 1000)
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
    """Make a shop public the way a real (non-practice) launch does: live and not practice."""
    from app.models import Business

    with Session(engine) as s:
        b = s.get(Business, business_id)
        b.status, b.practice = "live", False
        s.add(b)
        s.commit()


@pytest.fixture
def claude() -> FixtureClaudeClient:
    return FixtureClaudeClient()


@pytest.fixture
def integ(settings) -> Integrations:
    """A fresh fake world (GoDaddy, availability, mailbox, DNS, HTTP) with no real sleeping."""
    return fake_integrations(settings)


@pytest.fixture
def client(settings, engine, mailer, claude, integ) -> Iterator[TestClient]:
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_mailer] = lambda: mailer
    app.dependency_overrides[get_claude] = lambda: claude
    app.dependency_overrides[get_integrations] = lambda: integ
    app.dependency_overrides[get_practice_integrations] = lambda: integ
    with TestClient(app) as c:
        yield c
