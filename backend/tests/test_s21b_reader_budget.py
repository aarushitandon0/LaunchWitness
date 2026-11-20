"""S21B: the Reader's output budget. A long menu gets 3000 output tokens (strong tier only); a reply cut off at
max_tokens is never tidied, saved or shown: one retry, then a plain "Your menu is long" message and no shop.

Uses a fake SDK (no network) and a 20-item menu fixture (tests/fixtures/long_menu_20.json)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.agents.claude_client import ClaudeBadJson, ClaudeCutOff, LiveClaudeClient
from app.agents.reader import LONG_MENU, ReaderError, read_business
from app.models import Business
from app.routers.businesses import get_claude
from tests.test_claude_live_guards import FakeMessages

MENU = json.loads((Path(__file__).parent / "fixtures" / "long_menu_20.json").read_text(encoding="utf-8"))


def full_reply() -> str:
    return json.dumps(MENU["reply"], ensure_ascii=False)


def cut_reply() -> str:
    text = full_reply()
    return text[: len(text) * 2 // 3]  # what a reply stopped at max_tokens looks like: unfinished JSON


def live(make_settings, engine, replies, **over):
    sdk = SimpleNamespace(messages=FakeMessages(replies))
    s = make_settings(claude_mode="live", anthropic_api_key="sk-test-not-real", **over)
    return LiveClaudeClient(s, engine, sdk=sdk), sdk.messages


def test_the_fixture_is_a_real_20_item_menu():
    assert len(MENU["reply"]["products"]) == 20 and MENU["price_list"].count("\n") >= 19


def test_the_reader_gets_3000_output_tokens_and_the_cheap_tier_keeps_its_ceiling(make_settings, engine):
    c, fake = live(make_settings, engine, [(full_reply(), "end_turn", 2000, 2600), ('{"a": 1}', "end_turn", 10, 10)])
    p = read_business(c, description=MENU["description"], price_list=MENU["price_list"])
    assert len(p.products) == 20
    assert fake.calls[0]["max_tokens"] == 3000
    c.ask_json(fixture="t", tier="cheap", system="s", user="u", max_tokens=5000)
    assert fake.calls[1]["max_tokens"] == 1500  # CLAUDE_MAX_TOKENS still caps Namer / Doctor / policy


def test_a_cut_off_reply_is_its_own_error(make_settings, engine):
    c, _ = live(make_settings, engine, [(cut_reply(), "max_tokens", 2000, 3000), (cut_reply(), "refusal", 1, 1)])
    with pytest.raises(ClaudeCutOff):
        c.ask_json(fixture="t", tier="strong", system="s", user="u")
    with pytest.raises(ClaudeBadJson) as e:
        c.ask_json(fixture="t", tier="strong", system="s", user="u")
    assert not isinstance(e.value, ClaudeCutOff)


def test_cut_off_once_then_whole_is_used(make_settings, engine):
    c, fake = live(make_settings, engine, [(cut_reply(), "max_tokens", 2000, 3000), (full_reply(), "end_turn", 2000, 2600)])
    p = read_business(c, description=MENU["description"], price_list=MENU["price_list"])
    assert len(fake.calls) == 2 and len(p.products) == 20


def test_cut_off_twice_says_the_menu_is_long(make_settings, engine):
    c, fake = live(make_settings, engine, [(cut_reply(), "max_tokens", 2000, 3000)] * 3)
    with pytest.raises(ReaderError) as e:
        read_business(c, description=MENU["description"], price_list=MENU["price_list"])
    assert len(fake.calls) == 2  # one retry, no more
    assert str(e.value) == LONG_MENU and "details" not in str(e.value)


def test_the_describe_route_saves_nothing_from_a_cut_off_reply(client, engine, make_settings):
    c, _ = live(make_settings, engine, [(cut_reply(), "max_tokens", 2000, 3000)] * 2)
    client.app.dependency_overrides[get_claude] = lambda: c
    with Session(engine) as s:
        before = len(s.exec(select(Business)).all())
    r = client.post("/api/businesses", data={"description": MENU["description"], "price_list": MENU["price_list"]})
    assert r.status_code == 422 and r.json()["detail"].startswith("Your menu is long, please check the items")
    with Session(engine) as s:
        assert len(s.exec(select(Business)).all()) == before
