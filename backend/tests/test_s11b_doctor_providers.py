"""S11b 1c: on our own shops the Doctor never gives another email service's customer our values, and never
overwrites or removes another service's working records (the B4 rule), proven once per service."""

import copy

import pytest

from app.agents.checker import run_check
from app.agents.doctor import repair
from app.agents.executor import StepFailed
from app.agents.playbook import apply_fix
from app.checks.mail_setup import BY_KEY, UNKNOWN_STEPS
from tests.test_m4_repair import DOMAIN, ScriptedDoctor, ctx_for, launched
from tests.test_s11b_matrix import SETUPS

OTHERS = sorted(k for k in SETUPS if k != "secureserver") + ["unknown"]


def move_mail_to(integ, provider: str) -> None:
    """The seller moved her email to another service after launch: its mail servers and its SPF line are live."""
    mx, inc, all_, _sel = SETUPS.get(provider, (["10 in1.mailhost.example."], "spf.mailhost.example", "~all", ""))
    zone = [r for r in integ.godaddy.zones[DOMAIN] if not (r["type"] == "MX" or str(r["data"]).startswith("v=spf1"))]
    zone += [{"type": "MX", "name": "@", "data": m.split()[1].rstrip("."), "priority": int(m.split()[0])} for m in mx]
    zone += [{"type": "TXT", "name": "@", "data": f"v=spf1 include:{inc} {all_}"}]
    integ.godaddy.zones[DOMAIN] = zone


@pytest.mark.parametrize("provider", OTHERS)
@pytest.mark.parametrize("check,fix", [("email_mx", "readd_mx"), ("email_spf", "readd_email_auth")])
def test_another_services_mail_is_explained_never_fixed_or_overwritten(client, integ, engine, settings, provider, check, fix):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    move_mail_to(integ, provider)
    before, writes = copy.deepcopy(integ.godaddy.zones[DOMAIN]), len(integ.godaddy.writes())
    out = run_check(ctx, check)
    assert not out.passed
    claude = ScriptedDoctor({"plain_explanation": "Emails can't reach you.", "fix_id": fix})
    r = repair(claude, ctx, out)
    assert not r.fixed and r.doctor["fix_id"] == "needs_owner" and r.doctor["source"] == "standard"
    assert claude.calls == []  # the evidence is certain, so code writes the instruction, not the model
    text = r.doctor["owner_instruction"]
    if provider == "unknown":
        assert UNKNOWN_STEPS in text and "include:" not in text
    else:
        assert BY_KEY[provider].label in text
    assert "secureserver" not in text or provider == "microsoft"  # never our values for someone else's service
    assert "GoDaddy Professional Email" not in text
    assert integ.godaddy.zones[DOMAIN] == before and len(integ.godaddy.writes()) == writes
    with pytest.raises(StepFailed):  # and even asked directly, the fix refuses
        apply_fix(ctx, fix)
    assert integ.godaddy.zones[DOMAIN] == before


def test_our_own_missing_settings_are_still_fixed(client, integ, engine, settings):
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if r["type"] != "MX"]
    out = run_check(ctx, "email_mx")
    r = repair(ScriptedDoctor({"plain_explanation": "Emails can't reach you.", "fix_id": "readd_mx"}), ctx, out)
    assert r.fixed


def test_a_shared_spf_line_and_later_records_are_kept(client, integ, engine, settings):
    """Her SPF names us AND another sender, and she added a verification record after launch: a fix keeps both."""
    ctx = ctx_for(engine, settings, integ, launched(client, integ))
    zone = [r for r in integ.godaddy.zones[DOMAIN] if not str(r["data"]).startswith("v=spf1")]
    shared = "v=spf1 include:secureserver.net include:_spf.google.com -all"
    zone += [{"type": "TXT", "name": "@", "data": shared}, {"type": "TXT", "name": "@", "data": "site-verification=abc"}]
    integ.godaddy.zones[DOMAIN] = zone
    apply_fix(ctx, "readd_email_auth")
    at_root = [r["data"] for r in integ.godaddy.zones[DOMAIN] if r["type"] == "TXT" and r["name"] == "@"]
    assert shared in at_root and "site-verification=abc" in at_root and "keep-me" in at_root
    # with the SPF line gone, the fix writes ours back and still keeps what she added
    integ.godaddy.zones[DOMAIN] = [r for r in integ.godaddy.zones[DOMAIN] if r["data"] != shared]
    apply_fix(ctx, "readd_email_auth")
    at_root = [r["data"] for r in integ.godaddy.zones[DOMAIN] if r["type"] == "TXT" and r["name"] == "@"]
    assert "site-verification=abc" in at_root and any(d.startswith("v=spf1 include:secureserver.net") for d in at_root)
