"""S13: the durable email outbox. Every email the app sends is saved here first, then sent.

- `send(...)`: save the email under a unique key (the same order / alert / link is never saved or sent twice),
  then try it at once with a short timeout while the person waits. If that fails, the sender job keeps trying.
- `run_once(...)`: the sender job (one process, in the monitor's scheduler): claims each due email atomically,
  sends it, and on a temporary error waits longer each time (exponential backoff with jitter). A permanent
  error (the server refused that recipient, a bad address) or too many tries makes it `dead`, shown to the team.
- Priorities: 0 = sign-in links + orders (never held back), 1 = alerts + team mail, 2 = test orders + the digest.
  `SMTP_DAILY_LIMIT` is the budget for the real mail server: from 80% priority 2 waits, at 100% priority 1 waits.
  Practice mail (the pretend world) never leaves the server and doesn't count.
- A sign-in link that would arrive expired is dropped, and its body (which holds the link) is emptied.
- `reconcile(...)`: at startup, mail left `sending` by a crash goes back to the queue. It may have been sent just
  before the crash, so it can arrive twice; it keeps the same Message-ID, so mail apps show it once.

Nothing here logs or stores a secret or a body in `last_error`: only the error kind and the SMTP code.
"""

import json
import random
import smtplib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import make_msgid

from sqlalchemy import func, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import audit
from app.config import Settings
from app.mail import layout
from app.mail.smtp import Mailer
from app.models import Order, Outbox, utcnow

PRIORITY = {"login": 0, "order": 0, "alert": 1, "team": 1, "watch": 1, "contact": 1, "test_order": 2, "digest": 2}
LOW_SHARE = 0.8  # from this share of the daily budget, priority-2 mail waits
BASE_DELAY_S, MAX_DELAY_S, MAX_ATTEMPTS = 30, 30 * 60, 10  # about 2 hours of trying, then dead
HOLD_S = 15 * 60  # mail held back by the budget looks again after this
STALE_SENDING = timedelta(minutes=10)  # a claim older than this lost its sender (it can't still be talking)
NOW_TIMEOUT_S = {"login": 5.0, "order": 10.0}  # trying at once while a person waits; others 15 s
JOB_TIMEOUT_S = 30.0
LINK_MARGIN = timedelta(minutes=2)  # a sign-in link must arrive with at least this long left to use it
OPEN = ("queued", "failed")


def aware(when: datetime | None) -> datetime | None:
    return when if when is None or when.tzinfo is not None else when.replace(tzinfo=UTC)


def start_of_day(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def channel_of(integ) -> str:
    """Practice integrations (the pretend world) never reach the real mail server."""
    return "practice" if getattr(integ, "fake", False) else "smtp"


# ---------- saving ----------

def enqueue(session: Session, settings: Settings, *, kind: str, key: str, to: str, subject: str, body: str,
            html: str = "", channel: str = "smtp", business_id: int | None = None, order_id: int | None = None,
            user_id: int | None = None, ref: dict | None = None, expires_at: datetime | None = None) -> tuple[Outbox, bool]:
    """Save an email once. Returns (row, created). An existing key returns the existing row unchanged."""
    found = session.exec(select(Outbox).where(Outbox.key == key)).first()
    if found is not None:
        return found, False
    ref = dict(ref or {})
    ref.setdefault("planned_id", make_msgid(domain=settings.smtp_user.rsplit("@", 1)[-1] or "launchwitness.com"))
    row = Outbox(key=key, kind=kind, priority=PRIORITY.get(kind, 1), channel=channel, to_addr=to, subject=subject,
                 body=body, html=html or "", business_id=business_id, order_id=order_id, user_id=user_id,
                 ref_json=json.dumps(ref), expires_at=expires_at)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:  # the same key saved a moment ago by someone else: theirs wins
        session.rollback()
        return session.exec(select(Outbox).where(Outbox.key == key)).one(), False
    session.refresh(row)
    _settle(session, row)
    return row, True


def send(session: Session, settings: Settings, mailer: Mailer, *, retry_now: bool = False,
         timeout: float | None = None, **fields) -> Outbox:
    """Save (once) and try at once. `retry_now`: a row already saved and not yet sent is tried again now
    (the caller's own round is the retry, e.g. monitoring). Returns the row as it is afterwards."""
    row, created = enqueue(session, settings, **fields)
    if row.status in OPEN and (created or retry_now):
        row = attempt(session, settings, mailer, row.id, timeout=timeout or NOW_TIMEOUT_S.get(row.kind, 15.0),
                      ignore_backoff=True)
    return row


# ---------- sending ----------

def sent_today(session: Session, now: datetime | None = None) -> int:
    return session.exec(select(func.count()).select_from(Outbox).where(
        Outbox.channel == "smtp", Outbox.status == "sent", Outbox.sent_at >= start_of_day(now))).one()


def held_by_budget(session: Session, settings: Settings, row: Outbox, now: datetime | None = None) -> bool:
    if row.channel != "smtp" or row.priority == 0:
        return False  # sign-in links and orders are never held back; practice mail isn't real mail
    used, limit = sent_today(session, now), max(settings.smtp_daily_limit, 0)
    return used >= (limit if row.priority == 1 else limit * LOW_SHARE)


def permanent(e: Exception) -> bool:
    """Errors that another try can't fix. A refused sign-in is NOT permanent: the team can fix the password."""
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return bool(e.recipients) and all(int(code) >= 500 for code, _ in e.recipients.values())
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(e, smtplib.SMTPResponseException):
        return 500 <= int(e.smtp_code) < 600
    return isinstance(e, (ValueError, UnicodeError))


def error_text(e: Exception) -> str:
    """Kind + SMTP code only: the server's words can contain addresses."""
    code = getattr(e, "smtp_code", None)
    if isinstance(e, smtplib.SMTPRecipientsRefused) and e.recipients:
        code = ",".join(sorted({str(c) for c, _ in e.recipients.values()}))
    return f"{type(e).__name__}{f' {code}' if code else ''}"[:120]


def backoff(attempts: int) -> float:
    return min(MAX_DELAY_S, BASE_DELAY_S * 2 ** max(attempts - 1, 0)) * random.uniform(0.8, 1.2)


def claim(session: Session, row_id: int, now: datetime, ignore_backoff: bool = False) -> bool:
    """Atomic: only one sender can move a row to `sending` (one UPDATE with the status in its WHERE)."""
    cond = [Outbox.id == row_id, Outbox.status.in_(OPEN)]
    if not ignore_backoff:
        cond.append(Outbox.next_try_at <= now)
    result = session.exec(update(Outbox).where(*cond).values(  # type: ignore[call-overload]
        status="sending", claimed_at=now, attempts=Outbox.attempts + 1, updated_at=now))
    session.commit()
    return result.rowcount == 1


def attempt(session: Session, settings: Settings, mailer: Mailer, row_id: int, *, timeout: float = JOB_TIMEOUT_S,
            ignore_backoff: bool = False, now: datetime | None = None) -> Outbox:
    now = now or utcnow()
    row = session.get(Outbox, row_id)
    if row is None or row.status not in OPEN:
        return row
    if row.expires_at is not None and aware(row.expires_at) <= now:
        return _finish(session, row, "dead", now, error="expired before it could be sent: dropped")
    if held_by_budget(session, settings, row, now):
        row.next_try_at, row.last_error, row.updated_at = now + timedelta(seconds=HOLD_S), "waiting: daily send budget", now
        session.add(row)
        session.commit()
        return row
    if not claim(session, row_id, now, ignore_backoff):
        session.refresh(row)
        return row  # someone else has it (or it isn't due): never two sends
    session.refresh(row)
    ref = json.loads(row.ref_json or "{}")
    try:
        html = row.html or layout.wrap(row.kind, row.subject, row.body)  # S17: every email in the branded layout
        message_id = mailer.send(to=row.to_addr, subject=row.subject, body=row.body, html=html,
                                 message_id=ref.get("planned_id"), timeout=timeout)
    except Exception as e:
        if permanent(e) or row.attempts >= MAX_ATTEMPTS:
            return _finish(session, row, "dead", utcnow(), error=error_text(e))
        row.next_try_at = utcnow() + timedelta(seconds=backoff(row.attempts))
        return _finish(session, row, "failed", utcnow(), error=error_text(e))
    row.message_id, row.sent_at = str(message_id or ""), utcnow()
    return _finish(session, row, "sent", row.sent_at)


def _finish(session: Session, row: Outbox, status: str, now: datetime, error: str = "") -> Outbox:
    row.status, row.updated_at, row.claimed_at = status, now, None
    if error:
        row.last_error = error
    elif status == "sent":
        row.last_error = ""
    if status in ("sent", "dead") and row.kind == "login":
        row.body = row.html = ""  # the link is a key to the account: don't keep it once it's out (or dropped)
    session.add(row)
    session.commit()
    session.refresh(row)
    _settle(session, row)
    return row


def order_email_status(status: str) -> str:
    return {"sent": "sent", "dead": "failed", "failed": "retrying"}.get(status, "queued")


def _settle(session: Session, row: Outbox) -> None:
    """What the rest of the app sees: the order's email status, the watched problems, the audit trail."""
    ref = json.loads(row.ref_json or "{}")
    if row.order_id is not None:
        order = session.get(Order, row.order_id)
        if order is not None:
            order.email_status = order_email_status(row.status)
            order.email_message_id = row.message_id if row.status == "sent" else ""
            session.add(order)
            session.commit()
    if row.kind == "watch" and row.status == "sent" and ref.get("watch_id"):
        from app.models import WatchedAddress

        w = session.get(WatchedAddress, ref["watch_id"])
        if w is not None:  # told now: these problems are known (the daily run forgot them when the first try failed)
            w.problems_json = json.dumps(sorted(set(json.loads(w.problems_json or "[]")) | set(ref.get("problems", []))))
            session.add(w)
            session.commit()
    a = ref.get("audit")
    if a and row.status in ("sent", "failed", "dead"):
        audit.record(session, actor=a.get("actor", "system"), action=a["action"], target=a.get("target", ""),
                     result=row.status if row.status != "dead" else "failed", business_id=row.business_id,
                     user_id=row.user_id, detail=f"outbox:{row.id} {row.last_error or row.message_id}"[:200])


# ---------- the sender job ----------

def run_once(engine: Engine, settings: Settings, mailer_for: Callable[[str], Mailer], now: datetime | None = None,
             batch: int = 40) -> dict[str, int]:
    """One pass: free stale claims, then send every due email, most important first. Returns counts by result."""
    now = now or utcnow()
    out: dict[str, int] = {}
    with Session(engine) as s:
        stale = s.exec(update(Outbox).where(Outbox.status == "sending",  # type: ignore[call-overload]
                                            Outbox.claimed_at < now - STALE_SENDING).values(
            status="failed", claimed_at=None, last_error="sender stopped mid-send: trying again", updated_at=now))
        s.commit()
        if stale.rowcount:
            out["reclaimed"] = stale.rowcount
        ids = s.exec(select(Outbox.id).where(Outbox.status.in_(OPEN), Outbox.next_try_at <= now)
                     .order_by(Outbox.priority, Outbox.created_at).limit(batch)).all()
    for row_id in ids:
        with Session(engine) as s:
            row = s.get(Outbox, row_id)
            if row is None:
                continue
            try:
                done = attempt(s, settings, mailer_for(row.channel), row_id, now=now)
            except Exception:  # one bad row never stops the others
                out["error"] = out.get("error", 0) + 1
                continue
            label = done.status if done.last_error != "waiting: daily send budget" else "held"
            out[label] = out.get(label, 0) + 1
    return out


def reconcile(session: Session) -> int:
    """Startup: mail left `sending` by a crash is queued again (same Message-ID)."""
    now = utcnow()
    result = session.exec(update(Outbox).where(Outbox.status == "sending").values(  # type: ignore[call-overload]
        status="failed", claimed_at=None, next_try_at=now, updated_at=now,
        last_error="server restarted while sending: trying again (it may already have arrived)"))
    session.commit()
    return result.rowcount


# ---------- the team's view ----------

def summary(session: Session, settings: Settings, recent: int = 10) -> dict:
    """Counts by status and the last errors: no bodies, no addresses, no customer data."""
    counts = dict(session.exec(select(Outbox.status, func.count()).group_by(Outbox.status)).all())
    errors = session.exec(select(Outbox).where(Outbox.last_error != "").order_by(Outbox.updated_at.desc())
                          .limit(recent)).all()
    return {"counts": {k: counts.get(k, 0) for k in ("queued", "sending", "sent", "failed", "dead")},
            "sent_today": sent_today(session), "daily_limit": settings.smtp_daily_limit,
            "recent_errors": [{"id": r.id, "kind": r.kind, "status": r.status, "attempts": r.attempts,
                               "error": r.last_error, "at": aware(r.updated_at).isoformat()} for r in errors]}


def dead_recently(session: Session, days: int = 1) -> int:
    return session.exec(select(func.count()).select_from(Outbox).where(
        Outbox.status == "dead", Outbox.updated_at >= utcnow() - timedelta(days=days),
        ~Outbox.last_error.startswith("expired"))).one()
