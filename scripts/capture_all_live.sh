#!/usr/bin/env bash
# Capture every live Claude fixture for session 6 on a machine that has the key.
# 17 calls, worst case ~$0.14. Stops at the first failure (no retries, no spend on a broken prompt).
# Needs in .env (never on the command line): ANTHROPIC_API_KEY=..., CLAUDE_MODE=live, CLAUDE_DAILY_SPEND_CAP_USD=1.5
set -euo pipefail
cd "$(dirname "$0")/../backend"
# Linux/Mac venvs use .venv/bin; Windows venvs use .venv/Scripts.
if [ -d ../.venv/bin ]; then VBIN=../.venv/bin; PY=$VBIN/python; PYTEST=$VBIN/pytest
else VBIN=../.venv/Scripts; PY=$VBIN/python.exe; PYTEST="$PY -m pytest"; fi
CAP_LIMIT=1.5

$PY - "$CAP_LIMIT" <<'PY'
import sys
from app.config import get_settings
s = get_settings()
limit = float(sys.argv[1])
problems = []
if s.claude_mode != "live": problems.append("CLAUDE_MODE is not 'live' in .env")
if not s.anthropic_api_key.get_secret_value(): problems.append("ANTHROPIC_API_KEY is empty in .env")
if s.claude_daily_spend_cap_usd > limit: problems.append(f"CLAUDE_DAILY_SPEND_CAP_USD must be <= {limit}")
if problems:
    print("Not starting:", "; ".join(problems)); sys.exit(2)
print(f"OK: live mode, key present (not shown), cap ${s.claude_daily_spend_cap_usd:.2f}")
PY

READERS="reader:meera_cakes reader:tiffin_service reader:tailor reader:whatsapp_messy reader:hinglish reader:no_categories reader:handwritten_photo reader:prompt_injection"
echo "== Worst-case cost (no calls) =="
$PY ../scripts/capture_live_fixtures.py --dry-run $READERS
$PY ../scripts/capture_live_fixtures.py --dry-run namer:meera_cakes doctor:all
echo "== Reader: 8 calls =="
$PY ../scripts/capture_live_fixtures.py $READERS
echo "== Namer + Doctor: 9 calls (Namer uses Meera's new Reader fixture) =="
$PY ../scripts/capture_live_fixtures.py namer:meera_cakes doctor:all
echo "== Quality gates on the new fixtures (fixture mode, no calls) =="
CLAUDE_MODE=fixture REQUIRE_LIVE_FIXTURES=1 $PYTEST -q tests/test_s6_agents.py
echo "== Spend today (ClaudeUsage table) =="
$PY ../scripts/capture_live_fixtures.py --report
