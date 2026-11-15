#!/usr/bin/env bash
# Secret scan of the repo AND its whole git history. Prints only where (file / line number) and what kind,
# never a value. Exit code = number of problems.
#
#   bash scripts/secret_scan.sh
#
# 1. Strict key patterns (scripts/transcript_scrub.py: Anthropic keys, private keys, GitHub/AWS keys,
#    password=/api_secret= assignments that aren't code) over every tracked file and over `git log -p --all`.
# 2. If .env exists: every real secret VALUE in it (keys named *KEY*, *SECRET*, *PASSWORD*, *TOKEN*, at least
#    8 characters) searched for literally in tracked files and in the whole history. The values go to grep
#    through a file descriptor, never on a command line, never on screen.

set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
PY="${PYTHON:-}"
[ -z "$PY" ] && for c in .venv/Scripts/python .venv/bin/python python3 python; do [ -x "$c" ] || command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
PROBLEMS=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "1. Patterns"
# Key-shaped hits (anthropic_key, private_key, github_token, aws_key_id) FAIL. The loose ones (password=..., api_secret=...,
# a webmail address) are listed for a person to review: tests and docs use placeholders like "pw-for-test-only".
HARD='anthropic_key|private_key|github_token|aws_key_id'
git log -p --all --no-color > "$TMP/history.txt" 2>/dev/null
git ls-files -z | xargs -0 cat -- 2>/dev/null > "$TMP/tracked.txt"
while IFS= read -r f; do
  case "$f" in *.png|*.jpg|*.jpeg|*.ico|*.webp|*.gif) continue;; esac
  out="$("$PY" scripts/transcript_scrub.py --check "$f" 2>&1)"
  echo "$out" | grep -q "SECRET SCAN: clean" && continue
  kinds="$(echo "$out" | grep -oE "($HARD|password|api_secret|email)" | sort | uniq -c | tr -s ' ' | tr '
' ',' | sed 's/,$//')"
  if echo "$out" | grep -qE "$HARD"; then echo "  FAIL   $f:$kinds"; PROBLEMS=$((PROBLEMS + 1))
  else echo "  review $f:$kinds"; fi
done < <(git ls-files)
out="$("$PY" scripts/transcript_scrub.py --check "$TMP/history.txt" 2>&1)"
kinds="$(echo "$out" | grep -oE "($HARD|password|api_secret|email)" | sort | uniq -c | tr -s ' ' | tr '
' ',' | sed 's/,$//')"
if echo "$out" | grep -q "SECRET SCAN: clean"; then echo "  history: clean"
elif echo "$out" | grep -qE "$HARD"; then echo "  FAIL   git history:$kinds"; PROBLEMS=$((PROBLEMS + 1))
else echo "  review git history ($(wc -l < "$TMP/history.txt") lines):$kinds"; fi

echo "2. Values from .env"
if [ -f .env ]; then
  grep -E '^[A-Z_]*(KEY|SECRET|PASSWORD|TOKEN)[A-Z_]*=' .env | while IFS='=' read -r k v; do
    v="$(printf '%s' "$v" | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
    [ "${#v}" -ge 8 ] && [ "$v" != "change-me" ] && printf '%s\t%s\n' "$k" "$v"
  done > "$TMP/vals.tsv"
  n=0
  while IFS=$'\t' read -r k v; do
    n=$((n + 1))
    hit=""
    grep -qF -f <(printf '%s\n' "$v") "$TMP/tracked.txt" && hit="tracked files"
    grep -qF -f <(printf '%s\n' "$v") "$TMP/history.txt" && hit="${hit:+$hit + }git history"
    if [ -n "$hit" ]; then echo "  FOUND: the value of $k is in $hit"; PROBLEMS=$((PROBLEMS + 1)); fi
  done < "$TMP/vals.tsv"
  echo "  checked $n secret value(s) from .env against tracked files and the whole history"
else
  echo "  (no .env here: skipped)"
fi
echo
[ "$PROBLEMS" -eq 0 ] && echo "Secret scan: clean." || echo "Secret scan: $PROBLEMS problem(s)."
exit "$PROBLEMS"
