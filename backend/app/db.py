"""Database engine and session helpers (SQLite via SQLModel)."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import get_settings

_engine: Engine | None = None


BUSY_TIMEOUT_MS = 5000


def _sqlite_pragmas(dbapi_conn, _record, *, wal: bool) -> None:
    """Set on EVERY new connection: wait up to 5 s for a lock instead of failing at once, enforce
    foreign keys, and (file databases) use WAL so readers never block the one writer."""
    cur = dbapi_conn.cursor()
    cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    cur.execute("PRAGMA foreign_keys=ON")
    if wal:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")  # safe with WAL; a power cut loses at most the last commit
    cur.close()


def make_engine(database_url: str) -> Engine:
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        # One shared in-memory DB across threads (tests).
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        event.listen(engine, "connect", lambda c, r: _sqlite_pragmas(c, r, wal=False))
        return engine
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", lambda c, r: _sqlite_pragmas(c, r, wal=True))
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def add_missing_columns(engine: Engine) -> list[str]:
    """Tiny forward-only migration: a table that already exists gets any column the models added
    since (SQLite `ALTER TABLE ... ADD COLUMN` with the model's default). Never drops or rewrites."""
    from sqlalchemy import inspect, text

    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
                if default is not None:
                    value = int(default) if isinstance(default, bool) else default
                    ddl += " DEFAULT " + (str(value) if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'")
                conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
    return added


def init_db(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    SQLModel.metadata.create_all(engine)
    add_missing_columns(engine)
    from app import chain

    chain.backfill(engine)  # S11d: evidence rows from before the hash chain get their links, once


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Tests override this."""
    with Session(get_engine()) as session:
        yield session
