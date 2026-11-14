"""Database engine and session helpers (SQLite via SQLModel)."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.config import get_settings

_engine: Engine | None = None


def make_engine(database_url: str) -> Engine:
    if database_url in ("sqlite://", "sqlite:///:memory:"):
        # One shared in-memory DB across threads (tests).
        return create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if database_url.startswith("sqlite:///"):
        Path(database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args={"check_same_thread": False})


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine(get_settings().database_url)
    return _engine


def init_db(engine: Engine | None = None) -> None:
    SQLModel.metadata.create_all(engine or get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Tests override this."""
    with Session(get_engine()) as session:
        yield session
