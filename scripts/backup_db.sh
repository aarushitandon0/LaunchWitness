#!/usr/bin/env bash
# Back up the app's SQLite database from the running `app` container with SQLite's ONLINE backup API
# (consistent while the app runs; never a `cp` of a live WAL database), check it, and rotate:
# 7 daily copies in backups/daily/ plus 4 weekly copies in backups/weekly/ (one a week).
#
#   bash scripts/backup_db.sh [backup-dir]          # default <repo>/backups (git-ignored), mode 600 files
#   LOCAL=1 bash scripts/backup_db.sh               # the local production-like stack (deploy/README.md)
# Restore: bash scripts/restore_db.sh <backup file>
# Nightly on the VPS (crontab -e), 03:15 server time:
#   15 3 * * * cd $HOME/LaunchWitness && bash scripts/backup_db.sh >> backups/backup.log 2>&1
#
# OFF-SERVER COPY: not automated (no cloud service chosen). The owner copies backups/ off the VPS by hand, e.g.
#   scp -i ~/.ssh/launchwitness -r lw@<VPS_IP>:LaunchWitness/backups ./lw-backups-$(date +%F)
# A backup that only lives on the server is lost with the server.

export MSYS_NO_PATHCONV=1  # Git Bash on Windows: never rewrite container paths like /app/...
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
DIR="${1:-$REPO/backups}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
if [ "${LOCAL:-}" = "1" ]; then
  COMPOSE=(docker compose -f "$REPO/deploy/docker-compose.yml" -f "$REPO/deploy/docker-compose.prod.yml" -f "$REPO/deploy/docker-compose.local.yml")
else
  ENV_ARGS=()
  [ -f "$REPO/.env" ] && ENV_ARGS=(--env-file "$REPO/.env")
  COMPOSE=(docker compose "${ENV_ARGS[@]}" -f "$REPO/deploy/docker-compose.yml" -f "$REPO/deploy/docker-compose.prod.yml")
fi

CID="$("${COMPOSE[@]}" ps -q app)"
[ -n "$CID" ] || { echo "FAIL: the app container isn't running." >&2; exit 1; }

umask 077
mkdir -p "$DIR/daily" "$DIR/weekly"
TS="$(date -u +%Y%m%d-%H%M%S)"
TMP="/app/backend/data/.backup-$TS.db"
OUT="$DIR/daily/launchwitness-$TS.db"

COUNTS="$(docker exec -i "$CID" python -m app.backup create "$TMP")"
docker cp "$CID:$TMP" "$OUT" >/dev/null
docker exec "$CID" rm -f "$TMP"
chmod 600 "$OUT"

# One weekly copy when the newest weekly one is 7+ days old (or there is none).
if [ -z "$(find "$DIR/weekly" -name 'launchwitness-*.db' -mtime -7 2>/dev/null | head -n1)" ]; then
  cp -p "$OUT" "$DIR/weekly/"
  echo "weekly copy: $DIR/weekly/$(basename "$OUT")"
fi
ls -1t "$DIR"/daily/launchwitness-*.db 2>/dev/null | tail -n +"$((KEEP_DAILY + 1))" | xargs -r rm -f
ls -1t "$DIR"/weekly/launchwitness-*.db 2>/dev/null | tail -n +"$((KEEP_WEEKLY + 1))" | xargs -r rm -f

echo "OK: $OUT ($(du -h "$OUT" | cut -f1)); rows $COUNTS"
echo "Kept: $(ls "$DIR"/daily/*.db | wc -l) daily, $(ls "$DIR"/weekly/*.db 2>/dev/null | wc -l) weekly."
echo "Restore (stops the app briefly): bash scripts/restore_db.sh $OUT"
