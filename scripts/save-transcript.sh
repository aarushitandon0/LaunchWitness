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
#   defaults to the repo's git user.email) AND any personal webmail address
#   (gmail, yahoo, outlook, hotmail, live, icloud, proton, rediffmail).
# - Secret-scans the result. On ANY match the copy is deleted and the script
#   exits 1: never commit a transcript the scan flagged.

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
python3 - "$SRC" "$DEST" "$EMAILS" <<'PY'
import re, sys
src, dest, emails = sys.argv[1], sys.argv[2], [e.strip() for e in sys.argv[3].split(",") if e.strip()]
text = open(src, encoding="utf-8", errors="replace").read()
for e in emails:
    text = re.sub(re.escape(e), "[redacted-email]", text, flags=re.IGNORECASE)
WEBMAIL = r"[A-Za-z0-9._%+-]+@(gmail|googlemail|yahoo|outlook|hotmail|live|icloud|me|proton|protonmail|rediffmail)\.[a-z.]{2,6}"
text = re.sub(WEBMAIL, "[redacted-email]", text, flags=re.IGNORECASE)
open(dest, "w", encoding="utf-8").write(text)
PY

# Secret scan (same patterns as build-replay.sh, plus common key formats and the
# redacted addresses themselves in case a variant slipped through).
PATTERN='(sk-ant-[a-z0-9_-]{10,}|api[_-]?secret["'"'"' :=]+[a-z0-9]{12,}|password["'"'"' :=]+[^ "'"'"'$<{]{6,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})'
HITS="$(grep -Ein "$PATTERN" "$DEST" | cut -d: -f1 | sort -un | head -20 | sed 's/^/possible secret on line /' || true)"
if grep -Eiq '[A-Za-z0-9._%+-]+@(gmail|googlemail|yahoo|outlook|hotmail|live|icloud|me|proton|protonmail|rediffmail)\.[a-z.]{2,6}' "$DEST"; then
  HITS="$HITS"$'\n'"unredacted webmail address"
fi
for e in ${EMAILS//,/ }; do
  if grep -qiF "$e" "$DEST"; then HITS="$HITS"$'\n'"unredacted email"; fi
done
if [ -n "${HITS//[$'\n ']/}" ]; then
  rm -f "$DEST"
  echo "SECRET SCAN MATCHED — transcript NOT saved (values are not printed):" >&2
  echo "$HITS" | sed '/^$/d' >&2
  exit 1
fi
echo "Saved $DEST (redacted, secret scan clean)"
