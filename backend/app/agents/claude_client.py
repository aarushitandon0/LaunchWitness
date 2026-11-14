"""Claude API wrapper.

CLAUDE_MODE=fixture (default) reads saved responses from
`backend/tests/fixtures/claude/<fixture>.json` and never touches the network.
CLAUDE_MODE=live calls the API. Only Reader uses the strong model; Namer and
Doctor use the cheap one.

Live-mode guards (every call):
- `max_tokens` is never above CLAUDE_MAX_TOKENS.
- Before the call, today's recorded spend + a worst-case estimate for this call
  (estimated input + full max_tokens output) must fit under
  CLAUDE_DAILY_SPEND_CAP_USD, otherwise the call is refused (ClaudeBudgetExceeded).
- After the call, the real token usage and cost are stored as a ClaudeUsage row.
- Models without a known price are refused, because their cost can't be capped.
Every allow/block writes an AuditEvent.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app import audit
from app.config import Settings
from app.models import ClaudeUsage

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "claude"

Tier = Literal["strong", "cheap"]
Content = str | list[dict[str, Any]]

# USD per million tokens (input, output). Anthropic first-party list prices.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.00, 20.00),
}
# Models where thinking can be switched off with {"type": "between_tools"}; the
# Reader is plain extraction, so we don't pay for thinking tokens.
THINKING_OFF = {"claude-sonnet-5-5": {"type": "between_tools"}}

IMAGE_TOKEN_ESTIMATE = 1600  # generous upper bound for one resized photo
CHARS_PER_TOKEN = 3  # conservative (overestimates tokens)


class ClaudeError(RuntimeError):
    pass


class ClaudeBadJson(ClaudeError):
    """The model's reply was not valid JSON (or was cut off / refused)."""


class ClaudeBudgetExceeded(ClaudeError):
    pass


class Claude(Protocol):
    def ask_json(
        self,
        *,
        fixture: str,
        tier: Tier,
        system: str,
        user: Content,
        schema: dict | None = None,
        max_tokens: int | None = None,
    ) -> dict: ...


class FixtureClaudeClient:
    def __init__(self, fixture_dir: Path = FIXTURE_DIR):
        self.fixture_dir = fixture_dir
        self.calls: list[str] = []

    def ask_json(self, *, fixture: str, tier: Tier, system: str, user: Content, schema=None, max_tokens=None) -> dict:
        self.calls.append(fixture)
        path = self.fixture_dir / f"{fixture}.json"
        if not path.is_file():
            raise FileNotFoundError(f"No Claude fixture: {path.name}")
        return json.loads(path.read_text(encoding="utf-8"))


def today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def call_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES_PER_MTOK[model]
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000


def estimate_input_tokens(system: str, user: Content) -> int:
    if isinstance(user, str):
        return (len(system) + len(user)) // CHARS_PER_TOKEN + 50
    chars, images = len(system), 0
    for block in user:
        if block.get("type") == "image":
            images += 1
        else:
            chars += len(json.dumps(block, ensure_ascii=False))
    return chars // CHARS_PER_TOKEN + images * IMAGE_TOKEN_ESTIMATE + 50


def spent_today_usd(session: Session, day: str | None = None) -> float:
    total = session.exec(select(func.sum(ClaudeUsage.cost_usd)).where(ClaudeUsage.day == (day or today_utc()))).one()
    return float(total or 0.0)


class LiveClaudeClient:
    def __init__(self, settings: Settings, engine: Engine | None = None, sdk: Any = None):
        key = settings.anthropic_api_key.get_secret_value()
        if not key:
            raise RuntimeError("CLAUDE_MODE=live but ANTHROPIC_API_KEY is empty")
        if sdk is None:
            import anthropic  # imported lazily so fixture mode never needs it

            sdk = anthropic.Anthropic(api_key=key)
        if engine is None:
            from app.db import get_engine

            engine = get_engine()
        self._client = sdk
        self._engine = engine
        self._models = {"strong": settings.claude_model_strong, "cheap": settings.claude_model_cheap}
        self._max_tokens = settings.claude_max_tokens
        self._cap = settings.claude_daily_spend_cap_usd

    def ask_json(
        self,
        *,
        fixture: str,
        tier: Tier,
        system: str,
        user: Content,
        schema: dict | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        model = self._models[tier]
        limit = min(max_tokens or self._max_tokens, self._max_tokens)

        with Session(self._engine) as session:
            if model not in PRICES_PER_MTOK:
                audit.record(session, actor="claude", action="claude_call", target=fixture, result="blocked",
                             detail=f"no known price for model {model}")
                raise ClaudeBudgetExceeded(f"No price known for {model}; refusing so the spend cap holds")
            spent = spent_today_usd(session)
            worst = call_cost_usd(model, estimate_input_tokens(system, user), limit)
            if spent + worst > self._cap:
                audit.record(session, actor="claude", action="claude_call", target=fixture, result="blocked",
                             detail=f"daily cap ${self._cap:.2f}: spent ${spent:.4f} + worst case ${worst:.4f}")
                raise ClaudeBudgetExceeded("Daily Claude spend cap reached")

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": limit,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if model in THINKING_OFF:
            kwargs["thinking"] = THINKING_OFF[model]
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        msg = self._client.messages.create(**kwargs)

        usage = msg.usage
        in_tok = (usage.input_tokens or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (
            getattr(usage, "cache_read_input_tokens", 0) or 0
        )
        out_tok = usage.output_tokens or 0
        cost = call_cost_usd(model, in_tok, out_tok)
        with Session(self._engine) as session:
            session.add(ClaudeUsage(day=today_utc(), purpose=fixture, model=model, input_tokens=in_tok,
                                    output_tokens=out_tok, cost_usd=cost))
            session.commit()
            audit.record(session, actor="claude", action="claude_call", target=fixture, result="ok",
                         detail=f"{model} in={in_tok} out={out_tok} ${cost:.4f} stop={msg.stop_reason}")

        if msg.stop_reason in ("refusal", "max_tokens"):
            raise ClaudeBadJson(f"Reply stopped early ({msg.stop_reason})")
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClaudeBadJson("Reply was not valid JSON") from e
        if not isinstance(data, dict):
            raise ClaudeBadJson("Reply was JSON but not an object")
        return data


def make_claude_client(settings: Settings, engine: Engine | None = None) -> Claude:
    if settings.claude_mode == "live":
        return LiveClaudeClient(settings, engine)
    return FixtureClaudeClient()
