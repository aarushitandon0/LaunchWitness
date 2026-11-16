"""S11b real-network run: read-only looks at well-known public sites. NOT part of the normal run.

    cd backend && ../.venv/Scripts/python -m pytest -m network tests/test_s11b_network.py -q
    LW_SAVE_FIXTURES=1 ...same...   # also re-save tests/fixtures/network/*.json for the offline replay

Only public DNS questions and one home-page visit per site. No form is posted and no email is sent to anyone.
Categories are asserted, not exact values (those change over time).
"""

import json
import os
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from app.checks import mail_setup as ms
from app.checks import web_setup as ws
from app.checks.dns_resolver import Answer, RealDnsResolver
from app.checks.safe_fetch import SafeWeb

pytestmark = pytest.mark.network
FIXTURES = Path(__file__).parent / "fixtures" / "network"
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+)")


class RecordingDns(RealDnsResolver):
    def __init__(self):
        super().__init__()
        self.asked: dict[str, list] = {}

    def lookup(self, name: str, rtype: str) -> Answer:
        got = super().lookup(name, rtype)
        self.asked[f"{name.lower().rstrip('.')} {rtype}"] = [got.status, [EMAIL.sub(r"someone@\1", v) for v in got.values]]
        return got


def brief(findings: list[dict]) -> list[list]:
    return [[f["check"], f["code"], f["ok"], f["sure"]] for f in findings]


def save(kind: str, host: str, dns: RecordingDns, findings: list[dict], **more) -> None:
    if os.environ.get("LW_SAVE_FIXTURES") != "1":
        return
    FIXTURES.mkdir(parents=True, exist_ok=True)
    data = {"kind": kind, "host": host, "date": date.today().isoformat(), "dns": dns.asked, **more,
            "findings": brief(findings), "plain": {f["check"]: f["plain"] for f in findings}}
    (FIXTURES / f"{kind}-{host}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


MAIL = [("google.com", "google"), ("microsoft.com", "microsoft"), ("zoho.com", "zoho"), ("zoho.in", "zoho_in"),
        ("launchwitness.com", "secureserver"), ("titan.email", "titan"), ("example.com", "null_mx"),
        ("neverssl.com", "no_mx"), ("jvns.ca", "unknown")]


@pytest.mark.parametrize("host,provider", MAIL)
def test_real_mail_setups(host, provider):
    dns = RecordingDns()
    findings = ms.mail_findings(host, dns)
    save("mail", host, dns, findings)
    f = {x["check"]: x for x in findings}
    assert f["email_mx"]["provider"] == provider, f["email_mx"]
    assert all(x["sure"] in ("seen", "not_seen", "couldnt_check") for x in findings)
    assert f["email_dkim"]["code"] != "dkim_missing" and "aren't signed" not in f["email_dkim"]["plain"]
    if provider in ("google", "microsoft", "zoho", "zoho_in", "secureserver", "titan"):
        assert f["email_mx"]["ok"] is True and f["email_spf"]["ok"] is True, (f["email_mx"], f["email_spf"])
        assert f["email_dmarc"]["ok"] is True
    if provider == "null_mx":
        assert f["email_mx"]["code"] == "mx_null" and f["email_dkim"]["code"] == "dkim_not_applicable"
    if provider == "no_mx":
        assert f["email_mx"]["code"] == "mx_none"
    if provider == "unknown":
        assert all(ms.UNKNOWN_STEPS == x["steps"] for x in findings if x["check"] in ("email_spf", "email_dkim")
                   and x["ok"] is not True)


WEB = [("expired.badssl.com", "https", {"cert_expired"}), ("wrong.host.badssl.com", "https", {"cert_wrong_host"}),
       ("self-signed.badssl.com", "https", {"cert_self_signed"}), ("untrusted-root.badssl.com", "https", {"cert_untrusted"}),
       ("http.badssl.com", "https", {"web_https_to_http", "web_http_only"}),
       ("neverssl.com", "https", {"web_http_only", "web_refused", "web_timeout", "web_error"}),
       ("github.com", "plain_http", {"http_redirects"}), ("example.com", "https", {"web_ok"})]


@pytest.mark.parametrize("host,check,codes", WEB)
def test_real_websites(host, check, codes):
    dns, web = RecordingDns(), SafeWeb(lambda _h: True, timeout=8.0)
    seen = ws.observe(host, dns, web)
    other = ws.twin_of(host, dns) if seen.dns == "ok" else None
    twin = ws.observe(other, dns, web, light=True) if other else None
    findings = ws.judge(seen, twin)
    save("web", host, dns, findings, web=asdict(seen), twin=asdict(twin) if twin else None)
    f = {x["check"]: x for x in findings}
    assert f["address"]["ok"] is True
    assert f[check]["code"] in codes, f[check]
    if host == "github.com":
        assert f["https"]["code"] == "web_ok" and f["certificate"]["ok"] is True


def test_watch_job_on_real_addresses_is_read_only_and_does_not_repeat(engine, mailer):
    from sqlmodel import Session

    from app import watch
    from app.models import User, WatchedAddress

    hosts = ["example.com", "expired.badssl.com", "github.com"]
    with Session(engine) as s:
        u = User(email="watcher@example.org", status="approved")
        s.add(u)
        s.commit()
        s.refresh(u)
        for h in hosts:
            s.add(WatchedAddress(user_id=u.id, host=h))
        s.commit()
    dns, web = RecordingDns(), SafeWeb(lambda _h: True, timeout=8.0)
    first = watch.run_daily(engine, mailer, dns, web)
    assert first >= 1  # expired.badssl.com has a real problem
    assert {m["to"] for m in mailer.sent} == {"watcher@example.org"}  # never anyone at the watched domains
    assert watch.run_daily(engine, mailer, dns, web) == 0  # the same problems tomorrow: no repeat
    assert len(mailer.sent) == first
