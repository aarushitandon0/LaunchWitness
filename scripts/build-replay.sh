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
# Usage:   bash scripts/build-replay.sh            -> replay/build.html
#          INCLUDE_SUBAGENTS=1 bash scripts/build-replay.sh
#
# Needs: node/npx (for claude-replay), python3.
# Redaction of secrets is ON (claude-replay default). Still review before publishing.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="${CLAUDE_PROJECTS_DIR:-$HOME/.claude/projects}"
OUT_DIR="$REPO/replay"
OUT="$OUT_DIR/build.html"
RAW="$OUT_DIR/raw"          # git-ignored working copies
mkdir -p "$OUT_DIR" "$RAW"

# 1) Find every transcript whose working directory is this repo (or inside it),
#    sorted by the first timestamp in each file.
mapfile -t FILES < <(python3 - "$PROJECTS" "$REPO" "${INCLUDE_SUBAGENTS:-0}" "$REPO/replay/sessions" <<'PY'
import json, os, sys
root, repo, include_sub, committed = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4]


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
                cwd = d.get("cwd") or ""
                if cwd == repo or cwd.startswith(repo + os.sep):
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

# 3) Render one page (secret redaction is on by default).
npx --yes claude-replay "${INPUTS[@]}" -o "$OUT"

# 4) Quick secret scan of the output as a second safety net.
if [ -f "$OUT" ] && grep -Eiq '(sk-ant-[a-z0-9_-]{10,}|api[_-]?secret["'"'"' :=]+[a-z0-9]{12,}|password["'"'"' :=]+[^ "'"'"']{6,})' "$OUT"; then
  echo "WARNING: possible secret found in $OUT — review before publishing." >&2
fi

echo "Wrote $OUT"
