"""Watched addresses (S10.5b): a signed-in user's up-to-3 addresses, checked read-only once a day.

Every route needs a signed-in user, and every query is filtered by that user: someone else's watch answers 404.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app import audit, watch
from app.checks.dns_resolver import DnsResolver
from app.checks.safe_fetch import SafeWeb
from app.db import get_session
from app.models import User, WatchedAddress
from app.routers.proof import clean_address, get_public_dns, get_public_web
from app.safety.access import require_user

router = APIRouter(prefix="/api", tags=["watch"])
NOT_FOUND = "We couldn't find that address in your list."


def out(w: WatchedAddress) -> dict:
    return {"id": w.id, "address": w.host, "problems": json.loads(w.problems_json or "[]"),
            "results": json.loads(w.results_json or "[]"),
            "last_checked_at": w.last_checked_at.replace(tzinfo=None).isoformat() + "Z" if w.last_checked_at else None}


@router.get("/watches")
def list_watches(user: Annotated[User, Depends(require_user)],
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    rows = session.exec(select(WatchedAddress).where(WatchedAddress.user_id == user.id)
                        .order_by(WatchedAddress.id)).all()
    return {"limit": watch.WATCH_LIMIT, "watches": [out(w) for w in rows]}


class AddWatch(BaseModel):
    address: str = Field(max_length=300)


@router.post("/watches", status_code=201)
def add_watch(body: AddWatch, user: Annotated[User, Depends(require_user)],
              session: Annotated[Session, Depends(get_session)],
              dns: Annotated[DnsResolver, Depends(get_public_dns)],
              web: Annotated[SafeWeb, Depends(get_public_web)]) -> dict:
    """Add an address and check it once right away (read-only). Up to 3 per account; adds are rate-limited."""
    host = clean_address(body.address)
    if host is None:
        raise HTTPException(status_code=422, detail="Please type a web address, like myshop.com.")
    mine = session.exec(select(WatchedAddress).where(WatchedAddress.user_id == user.id)).all()
    if any(w.host == host for w in mine):
        raise HTTPException(status_code=409, detail="You're already watching that address.")
    if len(mine) >= watch.WATCH_LIMIT:
        raise HTTPException(status_code=409, detail=f"You can watch up to {watch.WATCH_LIMIT} addresses. "
                            "Remove one to add another.")
    if watch.adds_today(session, user.id) >= watch.ADDS_PER_DAY:
        raise HTTPException(status_code=429, detail="You've added several addresses today. Please try again tomorrow.")
    w = WatchedAddress(user_id=user.id, host=host)
    session.add(w)
    session.commit()
    session.refresh(w)
    audit.record(session, actor="owner", action="watch_added", target=f"watch:{w.id}", result="ok", user_id=user.id,
                 detail="read-only daily checks")  # the address itself isn't written to the audit log
    watch.check_now(session, w, dns, web)  # the first look; problems found now are shown, not emailed
    return out(w)


@router.delete("/watches/{watch_id}")
def remove_watch(watch_id: int, user: Annotated[User, Depends(require_user)],
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    w = session.exec(select(WatchedAddress).where(WatchedAddress.id == watch_id,
                                                  WatchedAddress.user_id == user.id)).first()
    if w is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    session.delete(w)
    session.commit()
    audit.record(session, actor="owner", action="watch_removed", target=f"watch:{watch_id}", result="ok",
                 user_id=user.id)
    left = session.exec(select(func.count()).select_from(WatchedAddress).where(WatchedAddress.user_id == user.id)).one()
    return {"ok": True, "left": left}
