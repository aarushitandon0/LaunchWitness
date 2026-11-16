"""Tamper-evident proof log (S11d): every Evidence row is a link in a per-shop hash chain.

  hash = sha256(prev_hash + canonical_json(row fields))      first row: prev_hash = genesis(shop)

Canonical JSON: sorted keys, no whitespace, ASCII, times as UTC ISO with microseconds. The row id is
NOT hashed: order is proven by the prev_hash links (walked in id order), so one INSERT writes a row.

Evidence is append-only: `append` is the only way in, updates are refused, deletes are refused except
inside `purge` (a shop or account being deleted). What this does NOT prove: someone who can write the
database file can rewrite a whole chain, or cut rows off its end. A receipt (the chain head) that
somebody saved earlier is what such a rewrite cannot match.
"""

import hashlib
import json
import threading
from collections.abc import Mapping
from contextvars import ContextVar
from datetime import UTC, datetime

from sqlalchemy import event, or_, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import object_session
from sqlmodel import Session, delete, func, select

from app import audit
from app.models import Evidence

# Every stored fact of a row. A new Evidence column must be added here (a test checks the list).
FIELDS = ("business_id", "run_id", "check", "step", "at", "source", "server", "message_id", "nonce",
          "status_code", "cert_not_after", "answer", "practice")
RECEIPT_LEN = 12

_LOCK = threading.Lock()  # one app process (app.singleton): this lock makes "read head, insert" atomic
_purging: ContextVar[bool] = ContextVar("evidence_purging", default=False)


class AppendOnly(RuntimeError):
    """Evidence rows are never changed or removed (only a whole shop's chain, by `purge`)."""


def genesis(business_id: int) -> str:
    return hashlib.sha256(f"launchwitness:evidence-chain:v1:{business_id}".encode()).hexdigest()


def _utc(v: datetime) -> datetime:
    return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)


def _plain(v):
    return _utc(v).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if isinstance(v, datetime) else v


def canonical(row: Mapping | Evidence) -> str:
    get = row.__getitem__ if isinstance(row, Mapping) else lambda f: getattr(row, f)
    data = {f: _plain(get(f)) for f in FIELDS}
    data["practice"] = bool(data["practice"])
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def row_hash(prev_hash: str, row: Mapping | Evidence) -> str:
    return hashlib.sha256((prev_hash + canonical(row)).encode()).hexdigest()


def append(session: Session, row: Evidence) -> Evidence:
    """THE way an evidence row is written: take the shop's chain head and insert, in one transaction."""
    for f in ("at", "cert_not_after"):  # SQLite keeps the wall-clock digits only: make them UTC first
        if isinstance(getattr(row, f), datetime):
            setattr(row, f, _utc(getattr(row, f)))
    with _LOCK:
        head = session.exec(select(Evidence.hash).where(Evidence.business_id == row.business_id)
                            .order_by(Evidence.id.desc()).limit(1)).first()
        row.prev_hash = head or genesis(row.business_id)
        row.hash = row_hash(row.prev_hash, row)
        session.add(row)
        session.commit()
    session.refresh(row)
    return row


def verify(session: Session, business_id: int) -> dict:
    """Recompute the shop's chain. Only counts and hashes come out: never a row's contents.
    `altered_at` is the 1-based position of the first row that doesn't fit."""
    rows = session.exec(select(Evidence).where(Evidence.business_id == business_id).order_by(Evidence.id)).all()
    prev = genesis(business_id)
    for n, row in enumerate(rows, start=1):
        if row.prev_hash != prev or row.hash != row_hash(prev, row):
            return {"intact": False, "altered_at": n}
        prev = row.hash
    return {"intact": True, "rows": len(rows), "head": prev if rows else ""}


def receipt(session: Session, business_id: int) -> str:
    """First 12 hex of the chain head ("" when the shop has no evidence yet)."""
    head = session.exec(select(Evidence.hash).where(Evidence.business_id == business_id)
                        .order_by(Evidence.id.desc()).limit(1)).first()
    return (head or "")[:RECEIPT_LEN]


def purge(session: Session, business_id: int) -> int:
    """Remove a shop's whole chain (the shop is being deleted). Returns how many rows went. No commit."""
    n = session.exec(select(func.count()).select_from(Evidence).where(Evidence.business_id == business_id)).one()
    token = _purging.set(True)
    try:
        session.exec(delete(Evidence).where(Evidence.business_id == business_id))
    finally:
        _purging.reset(token)
    return n


def backfill(engine: Engine) -> int:
    """Startup migration, once: rows written before S11d get their links, per shop, in id order.
    The chain can only vouch for those rows as they were at this moment."""
    t = Evidence.__table__
    unchained = or_(t.c.hash == "", t.c.hash.is_(None))
    done = 0
    with engine.begin() as conn:
        shops = conn.execute(select(t.c.business_id).where(unchained).distinct().order_by(t.c.business_id)).scalars().all()
        for business_id in shops:
            prev = genesis(business_id)
            for r in conn.execute(select(t).where(t.c.business_id == business_id).order_by(t.c.id)).mappings().all():
                if r["hash"]:
                    prev = r["hash"]
                    continue
                h = row_hash(prev, r)
                conn.execute(update(t).where(t.c.id == r["id"]).values(prev_hash=prev, hash=h))
                prev, done = h, done + 1
    if done:
        with Session(engine) as s:
            audit.record(s, actor="system", action="evidence_chain_backfilled", result="ok",
                         detail=f"{done} earlier proof row(s) in {len(shops)} shop(s) chained; the chain starts here")
    return done


# ---------- append-only guards (the ORM refuses; anything done behind its back, verify() finds) ----------

@event.listens_for(Evidence, "before_update")
def _no_update(_mapper, _conn, target) -> None:
    s = object_session(target)
    if s is None or s.is_modified(target):
        raise AppendOnly("evidence rows are never changed")


@event.listens_for(Evidence, "before_delete")
def _no_delete(_mapper, _conn, _target) -> None:
    raise AppendOnly("evidence rows are never deleted one by one")


@event.listens_for(SASession, "do_orm_execute")
def _no_bulk_change(state) -> None:
    if not (state.is_update or state.is_delete):
        return
    mapper = state.bind_mapper
    if mapper is not None and mapper.class_ is Evidence and (state.is_update or not _purging.get()):
        raise AppendOnly("evidence rows are never changed or deleted (only a whole shop's chain, on purge)")
