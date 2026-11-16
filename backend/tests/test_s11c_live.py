"""S11c: the live pre-flight replies (scripts/preflight_live.py), replayed offline through the same code.

Reader: three sellers the prompt had never seen. Policy: the five go-live cases. The saved files are real replies;
these tests keep the app's handling of them (schema, tidy-up, rendering, verdicts) from regressing."""

import json
from pathlib import Path

import pytest
from markupsafe import escape

from app.agents.claude_client import FixtureClaudeClient
from app.agents.policy import policy_check
from app.agents.reader import Profile, read_business
from app.sites.render import format_inr, render_site
from tests.test_s6_agents import load

FIX = Path(__file__).parent / "fixtures"
FRESH = ["tiffin_hinglish", "candle_note", "tailor_from"]
CASES = json.loads((FIX / "policy_cases.json").read_text(encoding="utf-8"))


def seller(sid: str) -> dict:
    return json.loads((FIX / "sellers_hard" / f"{sid}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sid", FRESH)
def test_fresh_seller_keeps_real_prices_and_renders(sid):
    load(f"reader_{sid}")  # skips (or fails when strict) if it was never captured
    case = seller(sid)
    p = read_business(FixtureClaudeClient(), description=case["description"], price_list=case["price_list"])
    left = sorted(x.price_inr for x in p.products)
    for price in case["expected_prices"]:
        assert price in left, (price, left)
        left.remove(price)
    assert all(x in case["optional_prices"] for x in left), left
    for x in p.products:
        if x.price_inr in case["expected_prices"]:
            assert x.price_from == (x.price_inr in case["from_prices"]), x.name
    page = render_site(p, shop="lw-test")
    assert str(escape(p.name)) in page
    for x in p.products:
        assert str(escape(x.name)) in page and format_inr(x.price_inr) in page
        if x.price_from:
            assert f"<small>from </small>{format_inr(x.price_inr)}" in page


def test_fresh_sellers_are_found_by_their_own_text():
    """Fixture mode picks the saved reply by the description, so the three are distinct shops, not Meera's."""
    names = {read_business(FixtureClaudeClient(), description=seller(s)["description"]).name for s in FRESH}
    assert len(names) == 3 and not any("meera" in n.lower() for n in names)


def test_hinglish_tiffin_comes_back_in_english():
    p = Profile.model_validate(load("reader_tiffin_hinglish"))
    text = f"{p.about} {p.tagline} {p.hours}".lower()
    assert not any(w in text.split() for w in ("hum", "chalate", "hain", "chhutti", "batana", "hoga"))
    assert "sunday" in p.hours.lower() and "noida" in p.area.lower()
    assert p.whatsapp.endswith("9811045672") and p.delivery_available


class Replays(FixtureClaudeClient):
    """The policy check always asks as `policy_ok`; this answers with one case's saved live reply."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def ask_json(self, **kw):
        return super().ask_json(**{**kw, "fixture": self.name})


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_policy_case_verdict_from_the_live_reply(case):
    name = "policy_ok" if case["id"] == "normal" else f"policy_{case['id']}"
    raw = load(name, live_only=True)
    v = policy_check(Replays(name), Profile.model_validate(case["profile"]))
    assert v.by == "claude"  # none of these is caught by the word list: Claude really decided
    if case["expect"] != "any":
        assert v.ok == (case["expect"] == "ok"), v.reason
    if not v.ok:
        assert v.reason and len(v.reason) <= 300
    if case.get("must_not_contain"):
        assert case["must_not_contain"] not in json.dumps(raw)


def test_policy_fixture_is_no_longer_a_placeholder():
    assert "_note" not in json.loads((FIX / "claude" / "policy_ok.json").read_text(encoding="utf-8"))


def test_namer_live_reply_gives_usable_names():
    from app.agents.namer import clean_names
    names = clean_names(load("namer_preflight_s11c", live_only=True)["names"])
    assert len(names) >= 3 and any(n.endswith(".in") for n in names) and any(n.endswith(".com") for n in names)
