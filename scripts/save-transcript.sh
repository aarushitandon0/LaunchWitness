#!/usr/bin/env bash
# Save THIS session's Claude Code transcript into the repo, redacted and scanned.
#
# Usage:  bash scripts/save-transcript.sh <session-number> <milestone> [transcript.jsonl]
#   e.g.  bash scripts/save-transcript.sh 2 m2
#   -> replay/sessions/<YYYY-MM-DD>-s2-m2.jsonl
#
# - Without a path, takes the most recently modified transcript for this repo
#   under ~/.claude/projects (subagent files are skipped).
# - Replaces with [redacted-email]: every address in REDACT_EMAILS (comma-separated;
#   defaults to the repo's git user.email) AND any personal webmail address.
# - Replaces each secret-looking VALUE with [REDACTED] (strict patterns: Anthropic,
#   GitHub, AWS keys, private keys, api_secret=…, password=…) and keeps the rest.
#   Code like `password: SecretStr` and base64 screenshot data are not flagged.
# - Re-scans; if anything real-looking remains, nothing is saved and it exits 1:
#   never commit a transcript the scan refused.

set -euo pipefail

N="${1:?session number, e.g. 2}"
MS="${2:?milestone, e.g. m2}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="${CLAUDE_PROJECTS_DIR:-$HOME/.claude/projects}"
SRC="${3:-}"

if [ -z "$SRC" ]; then
  SRC="$(python3 - "$PROJECTS" "$REPO" <<'PY'
import json, os, sys
root, repo = sys.argv[1], sys.argv[2]
best = None
for dirpath, _, names in os.walk(root):
    if "subagents" in dirpath.split(os.sep):
        continue
    for n in names:
        if not n.endswith(".jsonl"):
            continue
        p = os.path.join(dirpath, n)
        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    cwd = json.loads(line).get("cwd") or ""
                except Exception:
                    continue
                if cwd == repo or cwd.startswith(repo + os.sep):
                    m = os.path.getmtime(p)
                    if best is None or m > best[0]:
                        best = (m, p)
                    break
print(best[1] if best else "")
PY
)"
fi
[ -n "$SRC" ] && [ -f "$SRC" ] || { echo "No transcript found for $REPO" >&2; exit 1; }

DEST_DIR="$REPO/replay/sessions"
mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/$(date +%F)-s${N}-${MS}.jsonl"

EMAILS="${REDACT_EMAILS:-$(git -C "$REPO" config user.email 2>/dev/null || true)}"
# Redact (emails + secret values -> [REDACTED]), re-scan, and refuse to save if
# anything real-looking remains. Values are never printed. See transcript_scrub.py.
if ! python3 "$REPO/scripts/transcript_scrub.py" "$SRC" "$DEST" "$EMAILS"; then
  rm -f "$DEST"
  echo "Transcript NOT saved — do not commit it." >&2
  exit 1
fi
echo "Saved $DEST (redacted, secret scan clean)"
