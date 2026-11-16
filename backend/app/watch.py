"""Watch an address (S10.5b): the same read-only public checks as "Check any address", once a day, for up to
WATCH_LIMIT addresses per signed-in account, with one email per NEW problem.

What it never does: submit forms, send email to that domain, or change anything there. It reads public DNS and
opens the home page over HTTPS through the SSRF-safe fetcher (`SafeWeb`), exactly like the public tool. The only
email goes to the account's own sign-in address.
"""

import json
from datetime import timedelta

from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

from app import audit
from app.checks.dns_resolver import DnsResolver
from app.checks.safe_fetch import SafeWeb
from app.mail.smtp import Mailer
from app.models import AuditEvent, User, WatchedAddress, utcnow

WATCH_LIMIT = 3  # addresses per account
ADDS_PER_DAY = 10  # adding (each add runs one check right away): rate limit per account


def problems_of(results: list[dict]) -> dict[str, str]:
    """{check: plain sentence} for every check that failed (unknowns don't count)."""
    return {r["check"]: r["plain"] for r in results if r.get("ok") is False}


def check_now(session: Session, w: WatchedAddress, dns: DnsResolver, web: SafeWeb) -> dict[str, str]:
    """Run the read-only checks for one watch and store the result. Returns the NEW problems (not seen last time)."""
    from app.routers.proof import address_results

    results = address_results(w.host, dns, web)
    now_bad = problems_of(results)
    before = set(json.loads(w.problems_json or "[]"))
    new = {k: v for k, v in now_bad.items() if k not in before}
    w.problems_json = json.dumps(sorted(now_bad))
    w.results_json = json.dumps(results, ensure_ascii=False)
    w.last_checked_at = utcnow()
    session.add(w)
    session.commit()
    session.refresh(w)
    return new


def adds_today(session: Session, user_id: int) -> int:
    since = utcnow() - timedelta(days=1)
    return session.exec(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.user_id == user_id, AuditEvent.action == "watch_added", AuditEvent.created_at >= since)).one()


def alert_email(host: str, new: dict[str, str]) -> tuple[str, str]:
    lines = "\n".join(f"  - {text}" for text in new.values())
    return (f"Something changed on {host}",
            f"Hello,\n\nYou asked LaunchWitness to watch {host}. Today's read-only check found:\n\n{lines}\n\n"
            "We only read public information about that address: we didn't change anything there or contact it. "
            "You won't hear about these again unless they go away and come back. To stop watching it, open "
            "My shops in LaunchWitness and press Remove.\n\n— LaunchWitness")


def run_daily(engine: Engine, mailer: Mailer, dns: DnsResolver, web: SafeWeb) -> int:
    """The daily job: check every watched address once; email the owner once per new problem. Returns emails sent."""
    sent = 0
    with Session(engine) as s:
        ids = s.exec(select(WatchedAddress.id)).all()
    for wid in ids:
        with Session(engine) as s:
            w = s.get(WatchedAddress, wid)
            user = s.get(User, w.user_id) if w else None
            if w is None or user is None or user.status not in ("pending", "approved"):
                continue
            try:
                new = check_now(s, w, dns, web)
            except Exception as e:  # one bad address never stops the others
                audit.record(s, actor="monitor", action="watch_check", target=f"watch:{w.id}", result="failed",
                             user_id=user.id, detail=type(e).__name__)
                continue
            if not new:
                continue
            subject, body = alert_email(w.host, new)
            try:
                mailer.send(to=user.email, subject=subject, body=body)
                result = "sent"
                sent += 1
            except Exception as e:
                result = f"failed: {type(e).__name__}"
                # not sent: forget that we "know" these problems, so tomorrow's run tries the email again
                w.problems_json = json.dumps(sorted(set(json.loads(w.problems_json or "[]")) - set(new)))
                s.add(w)
                s.commit()
            audit.record(s, actor="monitor", action="watch_alert", target=f"watch:{w.id}", result=result.split(":")[0],
                         user_id=user.id, detail=", ".join(sorted(new)))
    return sent
