"""Claude API wrapper.

CLAUDE_MODE=fixture (default) reads saved responses from
`backend/tests/fixtures/claude/<fixture>.json` and never touches the network.
CLAUDE_MODE=live calls the API with a tight `max_tokens`. Only Reader uses the
strong model; Namer and Doctor use the cheap one.
"""

import json
from pathlib import Path
from typing import Literal, Protocol

from app.config import Settings

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "claude"

Tier = Literal["strong", "cheap"]


class Claude(Protocol):
    def ask_json(self, *, fixture: str, tier: Tier, system: str, user: str) -> dict: ...


class FixtureClaudeClient:
    def __init__(self, fixture_dir: Path = FIXTURE_DIR):
        self.fixture_dir = fixture_dir
        self.calls: list[str] = []

    def ask_json(self, *, fixture: str, tier: Tier, system: str, user: str) -> dict:
        self.calls.append(fixture)
        path = self.fixture_dir / f"{fixture}.json"
        if not path.is_file():
            raise FileNotFoundError(f"No Claude fixture: {path.name}")
        return json.loads(path.read_text(encoding="utf-8"))


class LiveClaudeClient:
    def __init__(self, settings: Settings):
        key = settings.anthropic_api_key.get_secret_value()
        if not key:
            raise RuntimeError("CLAUDE_MODE=live but ANTHROPIC_API_KEY is empty")
        import anthropic  # imported lazily so fixture mode never needs it

        self._client = anthropic.Anthropic(api_key=key)
        self._models = {"strong": settings.claude_model_strong, "cheap": settings.claude_model_cheap}
        self._max_tokens = settings.claude_max_tokens

    def ask_json(self, *, fixture: str, tier: Tier, system: str, user: str) -> dict:
        # TODO(M2): daily spend cap (CLAUDE_DAILY_SPEND_CAP_USD) + structured output.
        msg = self._client.messages.create(
            model=self._models[tier],
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return json.loads(text)


def make_claude_client(settings: Settings) -> Claude:
    if settings.claude_mode == "live":
        return LiveClaudeClient(settings)
    return FixtureClaudeClient()
