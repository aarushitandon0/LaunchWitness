"""Exactly one app process per database.

The monitor (APScheduler) runs inside the app process, and SQLite has one writer. Two app
processes on the same database would mean two copies of every alert email and every daily test
order. So the app takes an exclusive lock on a file next to the database at startup and refuses
to start if another process already holds it (e.g. someone ran uvicorn with `--workers 4`).
"""

import os
from pathlib import Path

_held = None  # keep the file object (and so the lock) for the life of the process


class SecondProcess(RuntimeError):
    pass


def lock_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        return None
    return Path(database_url.removeprefix("sqlite:///")).with_suffix(".lock")


def acquire(database_url: str) -> bool:
    """True when this process now holds the lock (or no lock applies). Raises SecondProcess otherwise."""
    global _held
    workers = os.environ.get("WEB_CONCURRENCY", "1").strip() or "1"
    if workers != "1":
        raise SecondProcess(f"WEB_CONCURRENCY={workers}: LaunchWitness must run as ONE process (scheduler + SQLite).")
    path = lock_path(database_url)
    if path is None or _held is not None:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        f.close()
        raise SecondProcess(f"Another LaunchWitness process already uses {path.parent}. Run exactly one "
                            "(one uvicorn worker, one app container).") from e
    _held = f
    return True


def release() -> None:
    global _held
    if _held is not None:
        _held.close()
        _held = None
