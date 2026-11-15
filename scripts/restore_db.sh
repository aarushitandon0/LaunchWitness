#!/usr/bin/env bash
# Restore the app's database from a backup made by scripts/backup_db.sh.
#
#   bash scripts/restore_db.sh backups/daily/launchwitness-<time>.db
#   LOCAL=1 bash scripts/restore_db.sh <file>      # the local production-like stack
#
# What it does: (1) a safety backup of the CURRENT database first (backups/pre-restore-<time>.db), (2) stops the
# app (Caddy keeps running and shows an error page for a moment), (3) checks the backup, deletes the old -wal/-shm
# files and copies the backup in with SQLite's backup API (app/backup.py, as the app user), (4) compares row counts
# with the backup, (5) starts the app and waits until it's healthy.

export MSYS_NO_PATHCONV=1  # Git Bash on Windows: never rewrite container paths like /app/...
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
SRC="${1:?usage: bash scripts/restore_db.sh <backup file>}"
[ -f "$SRC" ] || { echo "FAIL: no such file: $SRC" >&2; exit 1; }
SRC="$(cd "$(dirname "$SRC")" && (pwd -W 2>/dev/null || pwd))/$(basename "$SRC")"
if [ "${LOCAL:-}" = "1" ]; then
  COMPOSE=(docker compose -f "$REPO/deploy/docker-compose.yml" -f "$REPO/deploy/docker-compose.prod.yml" -f "$REPO/deploy/docker-compose.local.yml")
else
  ENV_ARGS=()
  [ -f "$REPO/.env" ] && ENV_ARGS=(--env-file "$REPO/.env")
  COMPOSE=(docker compose "${ENV_ARGS[@]}" -f "$REPO/deploy/docker-compose.yml" -f "$REPO/deploy/docker-compose.prod.yml")
fi

umask 077
mkdir -p "$REPO/backups"
if [ -n "$("${COMPOSE[@]}" ps -q app)" ]; then
  CID="$("${COMPOSE[@]}" ps -q app)"
  TS="$(date -u +%Y%m%d-%H%M%S)"
  docker exec -i "$CID" python -m app.backup create "/app/backend/data/.pre-restore-$TS.db" >/dev/null
  docker cp "$CID:/app/backend/data/.pre-restore-$TS.db" "$REPO/backups/pre-restore-$TS.db" >/dev/null
  docker exec "$CID" rm -f "/app/backend/data/.pre-restore-$TS.db"
  echo "safety copy of the current database: backups/pre-restore-$TS.db"
fi

WANT="$(cd "$REPO/backend" 2>/dev/null && python3 -c "import sqlite3,json,sys
con=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True)
n=[r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'\")]
print(json.dumps({t:con.execute(f'SELECT count(*) FROM \"{t}\"').fetchone()[0] for t in sorted(n)}))" "$SRC" 2>/dev/null || echo "")"

"${COMPOSE[@]}" stop app
# The app image, with the backup mounted read-only, running as the app user (it owns the data volume).
GOT="$("${COMPOSE[@]}" run --rm --no-deps -T -v "$SRC:/restore.db:ro" --entrypoint python app -m app.backup restore /restore.db)"
"${COMPOSE[@]}" up -d --wait app >/dev/null
echo "restored rows: $GOT"
if [ -n "$WANT" ] && [ "$WANT" != "$GOT" ]; then
  echo "FAIL: row counts differ from the backup file: $WANT" >&2; exit 1
fi
echo "OK: restored $SRC and the app is healthy again."
