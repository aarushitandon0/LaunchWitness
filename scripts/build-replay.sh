#!/usr/bin/env bash
# Build ONE combined replay page of every Claude Code session run in this repo,
# from the first prompt to the latest, in chronological order.
#
# Sources (both are read):
#   - ~/.claude/projects/**.jsonl  (sessions run on this machine, cwd inside the repo)
#   - replay/sessions/*.jsonl      (committed, redacted copies — see scripts/save-transcript.sh)
# The same session (by sessionId) found in both is used once; the committed
# replay/sessions copy wins because it is already redacted.
#
# Usage:   REDACT_EMAILS=<owner email> bash scripts/build-replay.sh   -> replay/build.html
#          INCLUDE_SUBAGENTS=1 ...
#
# Needs: node/npx (for claude-replay), python3.
# The page is PUBLIC (served at /build), so:
#   - claude-replay's own secret redaction stays on, and every address in REDACT_EMAILS
#     (default: git user.email) is replaced with [redacted-email];
#   - afterwards the turn data is extracted back out of the HTML and scanned, and the HTML
#     text itself is scanned too (scripts/transcript_scrub.py --check). If anything
#     real-looking is found, build.html is DELETED and the script exits 1.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="${CLAUDE_PROJECTS_DIR:-$HOME/.claude/projects}"
OUT_DIR="$REPO/replay"
OUT="$OUT_DIR/build.html"
RAW="$OUT_DIR/raw"          # git-ignored working copies
mkdir -p "$OUT_DIR" "$RAW"
# A Python that really runs (on Windows `python3` can be the Store stub): $PYTHON, the repo's venv, then the PATH.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in "$REPO/.venv/Scripts/python" "$REPO/.venv/bin/python" python3 python; do
    if "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "No working python found (set PYTHON=...)" >&2; exit 1; }

# 1) Find every transcript whose working directory is this repo (or inside it),
#    sorted by the first timestamp in each file.
mapfile -t FILES < <("$PY" - "$PROJECTS" "$REPO" "${INCLUDE_SUBAGENTS:-0}" "$REPO/replay/sessions" <<'PY'
import json, os, re, sys


def norm(p):
    """One spelling for a path on any OS: Git Bash /c/Users/x and the c-colon-backslash form are one folder."""
    p = p.replace(chr(92), "/").rstrip("/")
    m = re.match(r"^/([A-Za-z])(/.*)?$", p)
    if m:
        p = m.group(1) + ":" + (m.group(2) or "/")
    if re.match(r"^[A-Za-z]:", p):
        p = p.lower()
    return p


root, repo, include_sub, committed = sys.argv[1], norm(sys.argv[2]), sys.argv[3] == "1", sys.argv[4]


def scan(p, need_repo):
    """Return (first_ts, session_id) if the file belongs to this repo, else None."""
    first_ts, sid, in_repo = None, None, not need_repo
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                cwd = norm(d.get("cwd") or "")
                if cwd and (cwd == repo or cwd.startswith(repo + "/")):
                    in_repo = True
                if first_ts is None and d.get("timestamp"):
                    first_ts = d["timestamp"]
                if sid is None and d.get("sessionId"):
                    sid = d["sessionId"]
                if in_repo and first_ts and sid:
                    break
    except OSError:
        return None
    return (first_ts or "", sid or p) if in_repo else None


by_session = {}  # session id -> (first_ts, path); committed copies first so they win
if os.path.isdir(committed):
    for n in sorted(os.listdir(committed)):
        if n.endswith(".jsonl"):
            p = os.path.join(committed, n)
            r = scan(p, need_repo=False)
            if r:
                by_session.setdefault(r[1], (r[0], p))
if os.path.isdir(root):
    for dirpath, _, names in os.walk(root):
        if not include_sub and "subagents" in dirpath.split(os.sep):
            continue
        for n in names:
            if n.endswith(".jsonl"):
                p = os.path.join(dirpath, n)
                r = scan(p, need_repo=True)
                if r:
                    by_session.setdefault(r[1], (r[0], p))
for _, p in sorted(by_session.values()):
    print(p)
PY
)

COUNT=${#FILES[@]}
if [ "$COUNT" -eq 0 ]; then
  echo "No Claude Code sessions found for $REPO under $PROJECTS or replay/sessions" >&2
  exit 1
fi
echo "Found $COUNT session file(s) for this repo."

# 2) claude-replay chains up to 20 inputs. Above that, concatenate the files
#    (whole sessions, in chronological order) into one input file.
if [ "$COUNT" -le 20 ]; then
  INPUTS=("${FILES[@]}")
else
  echo "More than 20 sessions: concatenating into one input file."
  COMBINED="$RAW/all-sessions.jsonl"
  : > "$COMBINED"
  for f in "${FILES[@]}"; do cat "$f" >> "$COMBINED"; echo >> "$COMBINED"; done
  INPUTS=("$COMBINED")
fi

# 3) Render one page (claude-replay's secret redaction is on by default) + redact owner emails.
EMAILS="${REDACT_EMAILS:-$(git -C "$REPO" config user.email 2>/dev/null || true)}"
REDACT_ARGS=()
IFS=',' read -ra _emails <<< "$EMAILS"
for e in "${_emails[@]}"; do
  e="$(echo "$e" | xargs)"
  [ -n "$e" ] && REDACT_ARGS+=(--redact "$e=[redacted-email]")
done
npx --yes claude-replay "${INPUTS[@]}" -o "$OUT" "${REDACT_ARGS[@]}" \
  --title "How LaunchWitness was built with Claude Code" \
  --description "Every Claude Code session that built LaunchWitness, from the first prompt to the latest."

# 4) Secret scan of what will be published: the turn data extracted from the page, and the page text.
npx --yes claude-replay extract "$OUT" -o "$RAW/extracted.jsonl" >/dev/null
if ! "$PY" "$REPO/scripts/transcript_scrub.py" --check "$RAW/extracted.jsonl" "$EMAILS" \
   || ! "$PY" "$REPO/scripts/transcript_scrub.py" --check "$OUT" "$EMAILS"; then
  rm -f "$OUT"
  echo "FAIL: secret scan found something in the replay; $OUT was deleted. Do not publish." >&2
  exit 1
fi

echo "Wrote $OUT ($(du -h "$OUT" | cut -f1), secret scan clean)"
