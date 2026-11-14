#!/usr/bin/env bash
# Back up the app's SQLite database from the running `app` container (safe while the app runs:
# uses SQLite's online backup API), keep the newest $KEEP copies, and print how to restore.
#
# Usage (on the VPS, from anywhere):   bash scripts/backup_db.sh [backup-dir]
#   default backup-dir: <repo>/backups (git-ignored).  KEEP=14 by default.
# Restore:  bash scripts/backup_db.sh --restore backups/launchwitness-<time>.db
#   (stops the app, copies the file onto the data volume owned by the app user, starts the app)
# Nightly (crontab -e):   15 3 * * * cd ~/LaunchWitness && bash scripts/backup_db.sh >> backups/backup.log 2>&1

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${1:-$REPO/backups}"
KEEP="${KEEP:-14}"
ENV_ARGS=()
[ -f "$REPO/.env" ] && ENV_ARGS=(--env-file "$REPO/.env")
COMPOSE=(docker compose "${ENV_ARGS[@]}" -f "$REPO/deploy/docker-compose.yml" -f "$REPO/deploy/docker-compose.prod.yml")

if [ "${1:-}" = "--restore" ]; then
  FILE="$(cd "$(dirname "${2:?backup file to restore}")" && pwd)/$(basename "$2")"
  [ -f "$FILE" ] || { echo "FAIL: no such file: $FILE" >&2; exit 1; }
  "${COMPOSE[@]}" stop app
  # Run the app image as root just to copy the file and hand it to the app user (uid lw).
  "${COMPOSE[@]}" run --rm --no-deps --user root -v "$FILE:/restore.db:ro" --entrypoint sh app -c \
    'cp /restore.db /app/backend/data/launchwitness.db && chown lw /app/backend/data/launchwitness.db && chmod 600 /app/backend/data/launchwitness.db'
  "${COMPOSE[@]}" start app
  echo "OK: restored $FILE. Check: curl -s https://\$APP_DOMAIN/api/health"
  exit 0
fi

CID="$("${COMPOSE[@]}" ps -q app)"
if [ -z "$CID" ]; then
  echo "FAIL: the app container isn't running. Start it first (see docs/RUNBOOK_M1.md)." >&2
  exit 1
fi

mkdir -p "$DIR"
TS="$(date -u +%Y%m%d-%H%M%S)"
TMP="/app/backend/data/.backup-$TS.db"
OUT="$DIR/launchwitness-$TS.db"

# Online backup inside the container, to the data volume.
docker exec -i "$CID" python - "$TMP" <<'PY'
import sqlite3, sys
from app.config import get_settings
url = get_settings().database_url
assert url.startswith("sqlite:///"), f"not a SQLite file database: {url}"
src = sqlite3.connect(url.removeprefix("sqlite:///"))
dst = sqlite3.connect(sys.argv[1])
src.backup(dst)
ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
dst.close(); src.close()
assert ok == "ok", ok
PY
docker cp "$CID:$TMP" "$OUT" >/dev/null
docker exec "$CID" rm -f "$TMP"
chmod 600 "$OUT"   # holds customer names/phones: owner-only

# Keep the newest $KEEP backups.
ls -1t "$DIR"/launchwitness-*.db 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f

echo "OK: backed up to $OUT ($(du -h "$OUT" | cut -f1)), keeping the newest $KEEP."
echo "Restore (stops the app briefly):  bash scripts/backup_db.sh --restore $OUT"
