# Capturing the live Claude fixtures (run on your laptop)

Cloud sessions can't hold an Anthropic key, so the live calls run on your machine. Everything else is in the repo:
the capture script, the hard test inputs, and the quality gates that check each saved reply.

**Total: 17 calls, worst case $0.14** (8 Reader on Sonnet 5.5, 1 Namer + 8 Doctor on Haiku 5.5). The cap is $1.50.
The run stops at the first reply that fails a check, so a broken prompt can't burn credit through retries.

## 1. Get the branch and set up (one time)

**Windows (Git Bash):** a Windows venv keeps its programs in `.venv/Scripts/` (`python.exe`, `pip.exe`, `pytest.exe`), not `.venv/bin/`. In every command below, replace `.venv/bin/` with `.venv/Scripts/`. `capture_all_live.sh` picks the right one by itself.

```bash
git fetch origin && git checkout main && git pull
```

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
```

## 2. Put the key in `.env` (never on the command line)

Open `.env` in your editor (create it with `cp .env.example .env` if it doesn't exist) and set these three lines:

```
ANTHROPIC_API_KEY=<your key>
CLAUDE_MODE=live
CLAUDE_DAILY_SPEND_CAP_USD=1.5
```

`.env` is git-ignored. Don't `export` the key in your shell, because that puts it in your shell history.

## 3. Run the capture (one command)

```bash
bash scripts/capture_all_live.sh
```

What it does, in order:
1. Refuses to start unless `.env` has live mode, a key, and a cap of $1.50 or less. It never prints the key.
2. Prints the worst-case cost of each call (no calls made yet).
3. Reader: 8 calls (Meera, tiffin, tailor, messy WhatsApp, Hinglish, no categories, handwritten photo, prompt injection).
4. Namer (Meera) + Doctor (each of the 8 checks): 9 calls.
5. Runs the quality gates with `REQUIRE_LIVE_FIXTURES=1`. A missing fixture or a leftover placeholder counts as a failure.
6. Prints today's spend from the `ClaudeUsage` table (`data/launchwitness.db`).

Each raw reply is also saved to `replay/raw/claude/<fixture>.json` (git-ignored: model, stop reason, tokens, cost, text),
so a bad reply can be debugged without paying for another call.

## 4. If something fails

The script stops and prints e.g. `reader:hinglish: NOT saved (ValidationError: …). Stopping: no more calls this run.`
- **Don't re-run blindly.** Send Claude Code the line it printed plus `replay/raw/claude/<fixture>.json`. The fix goes into
  the prompt or schema first.
- Then re-run **only the targets that are left**, e.g.:

```bash
cd backend && ../.venv/bin/python ../scripts/capture_live_fixtures.py reader:hinglish reader:no_categories reader:handwritten_photo reader:prompt_injection
```

- A quality gate failing in step 5 (e.g. jargon in a Doctor sentence) costs nothing more. Fix the prompt, then re-capture only that one target.

Other useful commands (run from `backend/`):

```bash
../.venv/bin/python ../scripts/capture_live_fixtures.py --dry-run reader:meera_cakes doctor:all
```

```bash
../.venv/bin/python ../scripts/capture_live_fixtures.py --report
```

## 5. Put the fixtures in the repo

Set `.env` back to `CLAUDE_MODE=fixture`, run the full tests, then commit only the fixture files:

```bash
cd backend && ../.venv/bin/pytest -q && REQUIRE_LIVE_FIXTURES=1 ../.venv/bin/pytest -q tests/test_s6_agents.py && cd ..
```

```bash
git checkout -b live-fixtures && git add backend/tests/fixtures/claude/ && git status --short
```

```bash
git commit -m "S6: live Claude fixtures (Reader x8, Namer, Doctor x8)" && git push -u origin live-fixtures
```

Then paste the `--report` output into PROGRESS.md under "Cost per launch" (or ask Claude Code to do it from that output).

## What the quality gates check (`backend/tests/test_s6_agents.py`)

- **Reader:** every reply validates against `Profile`. It also checks:
  - Messy WhatsApp text: real prices and phone number kept.
  - Hinglish: answer in English, UPI ID copied exactly.
  - No categories: 8 items grouped into 2–5 categories.
  - Handwritten photo: all 6 prices read correctly.
  - Prompt injection: no "Hacked", no ₹1 prices, no "closed", real name and prices kept.
- **Namer:** at least 6 usable names, both .in and .com, 4–15 letters only (no digits or hyphens), clearly about Meera's cakes.
- **Doctor:** exactly one sentence, at most 30 words, none of MX/DNS/TXT/SPF/DKIM/DMARC/HTTPS/SSL/certificate/server/record/IP,
  and the fix is one the playbook allows for that check. A separate test sends every disallowed (check, fix) pair and
  made-up fix ids: all are refused and logged, and nothing is written.
