"""Make ONE live Reader call per sample seller and save each reply as a fixture.

Exactly one API call per seller (no retry), at most 3 calls per run. The
replies go through the same LiveClaudeClient guards (max_tokens, daily cap,
usage recorded in the app DB). A reply that fails Profile validation is NOT
saved; the placeholder fixture stays.

Usage (needs CLAUDE_MODE=live and ANTHROPIC_API_KEY in the environment):
    cd backend && ../.venv/bin/python ../scripts/capture_reader_fixtures.py [seller_id ...]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlmodel import Session  # noqa: E402

from app.agents.claude_client import FIXTURE_DIR, LiveClaudeClient, spent_today_usd  # noqa: E402
from app.agents.reader import PROFILE_SCHEMA, SELLER_FIXTURES, SYSTEM, Profile, build_user_content  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402

MAX_CALLS = 3


def main(ids: list[str]) -> int:
    settings = get_settings()
    if settings.claude_mode != "live":
        print("Set CLAUDE_MODE=live to run this.")
        return 2
    ids = ids or ["meera_cakes", "tiffin_service", "tailor"]
    if len(ids) > MAX_CALLS:
        print(f"At most {MAX_CALLS} live calls per run.")
        return 2
    engine = get_engine()
    init_db(engine)
    client = LiveClaudeClient(settings, engine)
    with Session(engine) as s:
        before = spent_today_usd(s)
    failed = 0
    for seller_id in ids:
        sample = json.loads((SELLER_FIXTURES / f"{seller_id}.json").read_text(encoding="utf-8"))
        content = build_user_content(sample["description"], sample["price_list"], None)
        fixture = f"reader_{seller_id}"
        try:
            data = client.ask_json(fixture=fixture, tier="strong", system=SYSTEM, user=content, schema=PROFILE_SCHEMA)
            Profile.model_validate(data)
        except Exception as e:  # report and keep the placeholder
            print(f"{seller_id}: NOT saved ({type(e).__name__}: {str(e)[:200]})")
            failed += 1
            continue
        (FIXTURE_DIR / f"{fixture}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{seller_id}: saved {fixture}.json ({len(data['products'])} products)")
    with Session(engine) as s:
        after = spent_today_usd(s)
    print(f"Spend this run: ${after - before:.4f} · today total: ${after:.4f} (cap ${settings.claude_daily_spend_cap_usd:.2f})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
