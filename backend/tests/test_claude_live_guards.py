"""LiveClaudeClient guards: max_tokens ceiling, daily spend cap, usage recording.

Uses a fake SDK object, so nothing here can reach the network.
"""

import json
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.agents.claude_client import (
    ClaudeBadJson,
    ClaudeBudgetExceeded,
    LiveClaudeClient,
    call_cost_usd,
    spent_today_usd,
    today_utc,
)
from app.models import AuditEvent, ClaudeUsage


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text, stop, in_tok, out_tok = self.replies.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok,
                                  cache_creation_input_tokens=0, cache_read_input_tokens=0),
        )


def make_client(make_settings, engine, replies, **overrides):
    overrides.setdefault("claude_mode", "live")
    overrides.setdefault("anthropic_api_key", "sk-test-not-real")
    # S21B: the strong tier has its own ceiling (CLAUDE_READER_MAX_TOKENS, 3000); these guard tests pin both to one value
    overrides.setdefault("claude_reader_max_tokens", overrides.get("claude_max_tokens", 1500))
    sdk = SimpleNamespace(messages=FakeMessages(replies))
    return LiveClaudeClient(make_settings(**overrides), engine, sdk=sdk), sdk.messages


def ok(obj=None, in_tok=1000, out_tok=500):
    return (json.dumps(obj or {"a": 1}), "end_turn", in_tok, out_tok)


def test_max_tokens_never_above_setting(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok(), ok()], claude_max_tokens=800)
    c.ask_json(fixture="t", tier="strong", system="s", user="u", max_tokens=5000)
    c.ask_json(fixture="t", tier="strong", system="s", user="u", max_tokens=300)
    assert [call["max_tokens"] for call in fake.calls] == [800, 300]


def test_default_max_tokens_is_setting(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()], claude_max_tokens=1234)
    c.ask_json(fixture="t", tier="cheap", system="s", user="u")
    assert fake.calls[0]["max_tokens"] == 1234


def test_records_usage_and_cost(make_settings, engine):
    c, _ = make_client(make_settings, engine, [ok(in_tok=2000, out_tok=1000)])
    assert c.ask_json(fixture="reader_x", tier="strong", system="s", user="u") == {"a": 1}
    with Session(engine) as s:
        row = s.exec(select(ClaudeUsage)).one()
        assert (row.model, row.input_tokens, row.output_tokens, row.purpose) == ("claude-sonnet-5-5", 2000, 1000, "reader_x")
        assert row.cost_usd == pytest.approx(2000 * 2 / 1e6 + 1000 * 10 / 1e6)
        assert spent_today_usd(s) == pytest.approx(row.cost_usd)
        assert s.exec(select(AuditEvent).where(AuditEvent.action == "claude_call")).one().result == "ok"


def test_daily_cap_blocks_before_calling(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()], claude_daily_spend_cap_usd=0.05)
    with Session(engine) as s:
        s.add(ClaudeUsage(day=today_utc(), purpose="earlier", model="claude-sonnet-5-5",
                          input_tokens=0, output_tokens=0, cost_usd=0.04))
        s.commit()
    # worst case for 1500 output tokens on Sonnet = $0.015 → 0.04 + 0.015 > 0.05
    with pytest.raises(ClaudeBudgetExceeded):
        c.ask_json(fixture="t", tier="strong", system="s", user="u")
    assert fake.calls == []
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(AuditEvent.action == "claude_call")).one()
        assert ev.result == "blocked"


def test_cap_only_counts_today(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()], claude_daily_spend_cap_usd=0.05)
    with Session(engine) as s:
        s.add(ClaudeUsage(day="2000-01-01", purpose="old", model="claude-sonnet-5-5",
                          input_tokens=0, output_tokens=0, cost_usd=99.0))
        s.commit()
    c.ask_json(fixture="t", tier="strong", system="s", user="u")
    assert len(fake.calls) == 1


def test_cap_accumulates_across_calls(make_settings, engine):
    # Each call really costs $0.012; cap $0.03 allows the first, then worst-case blocks.
    replies = [ok(in_tok=1000, out_tok=1000)] * 5
    c, fake = make_client(make_settings, engine, replies, claude_daily_spend_cap_usd=0.03)
    c.ask_json(fixture="t", tier="strong", system="s", user="u")
    with pytest.raises(ClaudeBudgetExceeded):
        for _ in range(4):
            c.ask_json(fixture="t", tier="strong", system="s", user="u")
    with Session(engine) as s:
        assert spent_today_usd(s) <= 0.03


def test_image_counts_toward_estimate(make_settings, engine):
    # Text-only fits under the cap; the same call with a photo does not.
    cap = call_cost_usd("claude-sonnet-5-5", 200, 1500) + 0.001
    c, fake = make_client(make_settings, engine, [ok()], claude_daily_spend_cap_usd=cap)
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    with pytest.raises(ClaudeBudgetExceeded):
        c.ask_json(fixture="t", tier="strong", system="s", user=[image, {"type": "text", "text": "u"}])
    c.ask_json(fixture="t", tier="strong", system="s", user="u")
    assert len(fake.calls) == 1


def test_unknown_model_is_refused(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()], claude_model_strong="claude-unknown-9")
    with pytest.raises(ClaudeBudgetExceeded):
        c.ask_json(fixture="t", tier="strong", system="s", user="u")
    assert fake.calls == []


def test_schema_and_thinking_off_are_sent(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()])
    c.ask_json(fixture="t", tier="strong", system="s", user="u", schema={"type": "object"})
    call = fake.calls[0]
    assert call["output_config"] == {"format": {"type": "json_schema", "schema": {"type": "object"}}}
    assert call["thinking"] == {"type": "between_tools"}
    assert call["model"] == "claude-sonnet-5-5"


def test_cheap_model_thinking_is_off_too(make_settings, engine):
    c, fake = make_client(make_settings, engine, [ok()])
    c.ask_json(fixture="t", tier="cheap", system="s", user="u", max_tokens=200)
    assert fake.calls[0]["model"] == "claude-haiku-5-5" and fake.calls[0]["thinking"] == {"type": "disabled"}


def test_invalid_json_raises_but_cost_is_still_recorded(make_settings, engine):
    c, _ = make_client(make_settings, engine, [("not json {", "end_turn", 100, 50)])
    with pytest.raises(ClaudeBadJson):
        c.ask_json(fixture="t", tier="strong", system="s", user="u")
    with Session(engine) as s:
        assert len(s.exec(select(ClaudeUsage)).all()) == 1


@pytest.mark.parametrize("stop", ["max_tokens", "refusal"])
def test_early_stop_is_bad_json(make_settings, engine, stop):
    c, _ = make_client(make_settings, engine, [('{"a": 1}', stop, 10, 10)])
    with pytest.raises(ClaudeBadJson):
        c.ask_json(fixture="t", tier="strong", system="s", user="u")


def test_code_fenced_json_is_accepted(make_settings, engine):
    c, _ = make_client(make_settings, engine, [('```json\n{"a": 2}\n```', "end_turn", 10, 10)])
    assert c.ask_json(fixture="t", tier="strong", system="s", user="u") == {"a": 2}
