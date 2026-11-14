"""Wrappers: env switches, fixture mode, fakes — and proof that the real ones can't reach the network in tests."""

import json

import httpx
import pytest

from app.agents.claude_client import FixtureClaudeClient, LiveClaudeClient, make_claude_client
from app.checks.dns_resolver import FakeDnsResolver, RealDnsResolver
from app.godaddy.client import BASE_URLS, FakeGoDaddyClient, GoDaddyClient
from app.mail.imap import FakeInboxReader, ImapInboxReader
from app.mail.smtp import FakeMailer, SmtpMailer
from tests.conftest import NetworkBlocked

# ---------- GoDaddy ----------


def _capture_transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    return httpx.MockTransport(handler)


def test_godaddy_defaults_to_ote_with_ote_keys(make_settings):
    s = make_settings(godaddy_ote_api_key="otekey", godaddy_ote_api_secret="otesecret",
                      godaddy_api_key="prodkey", godaddy_api_secret="prodsecret")
    seen: list[httpx.Request] = []
    client = GoDaddyClient(s, transport=_capture_transport(seen))
    client.get_records("example.in")
    assert client.env == "ote"
    assert str(seen[0].url).startswith(BASE_URLS["ote"])
    assert seen[0].headers["Authorization"] == "sso-key otekey:otesecret"


def test_godaddy_prod_only_when_set(make_settings):
    s = make_settings(godaddy_env="prod", godaddy_api_key="prodkey", godaddy_api_secret="prodsecret")
    seen: list[httpx.Request] = []
    GoDaddyClient(s, transport=_capture_transport(seen)).get_records("example.in")
    assert str(seen[0].url).startswith("https://api.godaddy.com/v1/domains/example.in/records")
    assert seen[0].headers["Authorization"] == "sso-key prodkey:prodsecret"


def test_godaddy_env_rejects_unknown_value(make_settings):
    with pytest.raises(ValueError):
        make_settings(godaddy_env="production")


def test_fake_godaddy_roundtrip():
    gd = FakeGoDaddyClient(available={"meerascakes.in": 9.99})
    assert gd.check_availability("meerascakes.in") == {"domain": "meerascakes.in", "available": True, "price_usd": 9.99}
    assert gd.check_availability("taken.in")["available"] is False
    gd.set_records("meerascakes.in", "A", "@", [{"data": "203.0.113.10", "ttl": 600}])
    gd.set_records("meerascakes.in", "TXT", "@", [{"data": "hello"}])
    gd.set_records("meerascakes.in", "A", "@", [{"data": "203.0.113.11", "ttl": 600}])  # replaces only A @
    recs = gd.get_records("meerascakes.in")
    assert {(r["type"], r["data"]) for r in recs} == {("A", "203.0.113.11"), ("TXT", "hello")}
    gd.delete_records("meerascakes.in", "TXT", "@")
    assert [r["type"] for r in gd.get_records("meerascakes.in")] == ["A"]


def test_real_godaddy_writes_are_scoped_to_type_and_name(settings):
    seen = []
    client = GoDaddyClient(settings, transport=_capture_transport(seen))
    client.set_records("meerascakes.in", "TXT", "_dmarc", [{"type": "TXT", "name": "_dmarc", "data": "v=DMARC1", "ttl": 600}])
    client.delete_records("meerascakes.in", "A", "www")
    assert [(r.method, r.url.path) for r in seen] == [
        ("PUT", "/v1/domains/meerascakes.in/records/TXT/_dmarc"),
        ("DELETE", "/v1/domains/meerascakes.in/records/A/www"),
    ]
    assert json.loads(seen[0].content) == [{"data": "v=DMARC1", "ttl": 600}]


def test_real_godaddy_never_purchases(settings):
    from app.godaddy.client import PurchaseNotSupported

    seen = []
    with pytest.raises(PurchaseNotSupported):
        GoDaddyClient(settings, transport=_capture_transport(seen)).purchase_domain("meerascakes.in", 9.99)
    assert seen == []


def test_real_godaddy_cannot_reach_network(settings):
    with pytest.raises(NetworkBlocked):
        GoDaddyClient(settings).check_availability("example.in")


# ---------- Claude ----------


def test_claude_fixture_mode_is_default(settings):
    assert isinstance(make_claude_client(settings), FixtureClaudeClient)


def test_claude_fixture_reads_json(tmp_path):
    (tmp_path / "reader_demo.json").write_text(json.dumps({"business_name": "Demo"}))
    c = FixtureClaudeClient(fixture_dir=tmp_path)
    assert c.ask_json(fixture="reader_demo", tier="strong", system="", user="") == {"business_name": "Demo"}
    assert c.calls == ["reader_demo"]


def test_claude_fixture_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FixtureClaudeClient(fixture_dir=tmp_path).ask_json(fixture="nope", tier="cheap", system="", user="")


def test_claude_live_requires_key(make_settings, engine):
    with pytest.raises(RuntimeError):
        make_claude_client(make_settings(claude_mode="live"), engine)


def test_claude_live_cannot_reach_network(make_settings, engine):
    c = LiveClaudeClient(make_settings(claude_mode="live", anthropic_api_key="sk-test-not-real"), engine)
    c._client = c._client.with_options(max_retries=0)
    with pytest.raises(Exception) as exc:
        c.ask_json(fixture="x", tier="cheap", system="s", user="u")
    # The anthropic SDK wraps the transport error; make sure our guard was the cause.
    chain, e = [], exc.value
    while e is not None:
        chain.append(e)
        e = e.__cause__ or e.__context__
    assert any(isinstance(x, NetworkBlocked) for x in chain)


# ---------- Mail ----------


def test_fake_mailer_and_inbox():
    mailer, inbox = FakeMailer(), FakeInboxReader()
    mid = mailer.send(to="meera@example.com", subject="Test order #1", body="1 x Chocolate truffle cake")
    assert mid.startswith("<fake-1")
    inbox.deliver(sender="hello@example.com", to="meera@example.com", subject="Test order #1", body="...")
    assert len(inbox.find(subject_contains="Test order")) == 1
    assert inbox.find(subject_contains="Other") == []


def test_real_smtp_cannot_reach_network(settings):
    with pytest.raises(NetworkBlocked):
        SmtpMailer(settings).send(to="a@example.com", subject="x", body="y")


def test_real_imap_cannot_reach_network(settings):
    with pytest.raises(NetworkBlocked):
        ImapInboxReader(settings).find(subject_contains="x")


# ---------- DNS ----------


def test_fake_dns_resolver():
    r = FakeDnsResolver()
    r.set("MeerasCakes.in.", "a", ["203.0.113.10"])
    assert r.resolve("meerascakes.in", "A") == ["203.0.113.10"]
    assert r.resolve("meerascakes.in", "MX") == []


def test_real_dns_cannot_reach_network(no_network):
    # dnspython swallows per-nameserver errors and times out, so check the guard's record.
    assert RealDnsResolver(nameservers=["192.0.2.53"], timeout=0.3).resolve("example.com", "A") == []
    assert "192.0.2.53" in no_network


def test_network_guard_blocks_plain_httpx():
    with pytest.raises(NetworkBlocked):
        httpx.get("https://example.com")
