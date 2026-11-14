import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.main import create_app
from app.models import Business


@pytest.fixture
def prod_client(make_settings, engine):
    """App configured with a real-looking app domain and two sellers in the DB."""
    s = make_settings(app_domain="launchwitness.in")
    with Session(engine) as db:
        db.add(Business(name="Meera's Home Cakes", subdomain="meera", domain="meerascakes.in"))
        db.add(Business(name="Annapurna Tiffin", subdomain="annapurna"))
        db.commit()
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_settings] = lambda: s
    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def ask(c, domain):
    return c.get("/internal/tls-ask", params={"domain": domain}).status_code


@pytest.mark.parametrize("domain", [
    "launchwitness.in",
    "LaunchWitness.in.",
    "meera.launchwitness.in",
    "annapurna.launchwitness.in",
    "meerascakes.in",
])
def test_allows_known_domains(prod_client, domain):
    assert ask(prod_client, domain) == 200


@pytest.mark.parametrize("domain", [
    "evil.com",
    "unknown.launchwitness.in",            # subdomain not in DB
    "a.meera.launchwitness.in",            # nested subdomain
    "www.meerascakes.in",                  # only exact seller domains for now
    "meerascakes.in.evil.com",
    "notlaunchwitness.in",
    "",
    "bad domain",
    "../etc/passwd",
    "x" * 300,
])
def test_rejects_unknown_domains(prod_client, domain):
    assert ask(prod_client, domain) != 200


def test_rejects_missing_param(prod_client):
    assert prod_client.get("/internal/tls-ask").status_code == 404


def test_local_mode_allows_localhost_only(client):
    assert ask(client, "localhost") == 200
    assert ask(client, "example.com") == 404
