"""SQLite backup and restore, used by scripts/backup_db.sh and scripts/restore_db.sh (inside the app container).

- `create`: SQLite's online backup API (consistent even while the app writes; never `cp` of a live WAL database),
  then `PRAGMA integrity_check` on the copy.
- `restore`: only with the app STOPPED. Checks the backup, removes the old `-wal`/`-shm` files (an old WAL next to
  a restored file would be replayed into it), then copies the backup in with the same online backup API.
- `counts`: rows per table, so a restore can be compared with its backup.

    python -m app.backup create <out.db>
    python -m app.backup restore <backup.db> [<db path>]
    python -m app.backup counts [<db path>]
"""

import json
import os
import sqlite3
import sys

from app.config import get_settings


def db_path() -> str:
    url = get_settings().database_url
    if not url.startswith("sqlite:///") or url.endswith(":memory:"):
        raise SystemExit(f"not a SQLite file database: {url}")
    return url.removeprefix("sqlite:///")


def _check(con: sqlite3.Connection) -> None:
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise SystemExit(f"integrity check failed: {ok}")


def counts(path: str) -> dict[str, int]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {n: con.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in sorted(names)}
    finally:
        con.close()


def create(src_path: str, out_path: str) -> dict[str, int]:
    if os.path.exists(out_path):
        raise SystemExit(f"refusing to overwrite {out_path}")
    src = sqlite3.connect(src_path, timeout=30)
    dst = sqlite3.connect(out_path)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")  # a backup is one self-contained file
        _check(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(out_path, 0o600)  # customers' names and phones: owner-only
    return counts(out_path)


def restore(backup_path: str, target_path: str) -> dict[str, int]:
    """The app must be stopped. Returns the restored database's row counts (equal to the backup's)."""
    probe = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    try:
        _check(probe)
    finally:
        probe.close()
    for suffix in ("-wal", "-shm", "-journal"):
        if os.path.exists(target_path + suffix):
            os.remove(target_path + suffix)
    if os.path.exists(target_path):
        os.remove(target_path)
    src = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    dst = sqlite3.connect(target_path)
    try:
        src.backup(dst)
        _check(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(target_path, 0o600)
    got, want = counts(target_path), counts(backup_path)
    if got != want:
        raise SystemExit(f"restored row counts differ from the backup: {got} != {want}")
    return got


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "create" and len(argv) == 3:
        print(json.dumps(create(db_path(), argv[2])))
    elif cmd == "restore" and len(argv) in (3, 4):
        print(json.dumps(restore(argv[2], argv[3] if len(argv) == 4 else db_path())))
    elif cmd == "counts":
        print(json.dumps(counts(argv[2] if len(argv) == 3 else db_path())))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
