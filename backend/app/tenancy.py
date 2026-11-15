"""Things that happen to a whole shop: taking it down, deleting it, clearing old guest workspaces."""

from datetime import timedelta

from sqlalchemy.engine import Engine
from sqlmodel import Session, delete, select

from app import audit
from app.config import Settings
from app.integrations import Integrations
from app.models import (
    Alert,
    Approval,
    AuditEvent,
    Business,
    CheckResult,
    CheckRun,
    DnsBackup,
    Membership,
    Order,
    Plan,
    ShopReport,
    utcnow,
)
from app.sites.hosts import is_public

GUEST_HOURS = 24


def unpublish(session: Session, settings: Settings, integ: Integrations, b: Business) -> None:
    """Take a real shop off the internet: remove its address record (through the guarded client)
    and mark it not live. Best effort on the record: the shop is unpublished either way."""
    if not is_public(b):
        return
    try:
        if b.subdomain:
            integ.godaddy.delete_records(settings.app_domain, "A", b.subdomain)
        result, detail = "ok", "address record removed"
    except Exception as e:  # the page is gone anyway (status), the stray record points at a 404
        result, detail = "failed", type(e).__name__
    b.status = "draft"
    session.add(b)
    session.commit()
    audit.record(session, actor="system", action="unpublish", target=f"business:{b.id}", result=result,
                 business_id=b.id, detail=detail)


def purge_business(session: Session, settings: Settings, integ: Integrations, b: Business) -> None:
    """Delete a shop and everything personal that hangs off it (orders hold customers' names and
    phone numbers). The audit rows of the shop go too; the caller writes one anonymous record."""
    unpublish(session, settings, integ, b)
    for table in (Alert, CheckResult, CheckRun, Order, Approval, DnsBackup, AuditEvent, Membership, ShopReport):
        session.exec(delete(table).where(table.business_id == b.id))
    _purge_extra(session, b.id)
    session.exec(delete(Plan).where(Plan.business_id == b.id))
    session.delete(b)
    session.commit()


def _purge_extra(session: Session, business_id: int) -> None:
    """Tables added by later phases (evidence, shared reports) register here."""
    from app import models

    for name in ("Evidence", "ReportShare"):
        table = getattr(models, name, None)
        if table is not None:
            session.exec(delete(table).where(table.business_id == business_id))


def purge_old_guest_shops(engine: Engine, settings: Settings, integ: Integrations) -> int:
    """Guest practice workspaces live for 24 hours, then they are deleted."""
    with Session(engine) as s:
        cutoff = utcnow() - timedelta(hours=GUEST_HOURS)
        old = s.exec(select(Business).where(Business.guest_hash != "", Business.created_at < cutoff)).all()
        for b in old:
            purge_business(s, settings, integ, b)
        if old:
            audit.record(s, actor="system", action="guest_cleanup", result="ok", detail=f"{len(old)} practice shop(s) older than 24 h removed")
        return len(old)
