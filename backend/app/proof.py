"""The proof chain (S9F Phase 3): evidence rows, test-order tickets, the owner's "Yes, I got it",
and the web client the checker uses to order from the shop like a customer would.

Hops of a test order, each stored separately as Evidence:
  form_post      the shop's public form accepted the order (status code, order ref)
  smtp_accepted  our mail server accepted the email (message id). This is NOT delivery.
  imap_seen      the email was found in an inbox we can read (only mailboxes we hold)
  owner_confirmed the owner tapped "Yes, I got it" in the test email (single-use link)
"Accepted" is never shown as "delivered": only imap_seen or owner_confirmed count as delivered.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Protocol

from sqlmodel import Session, select

from app import audit
from app.checks.safe_fetch import Page, SafeWeb
from app.config import Settings
from app.models import Business, Evidence, Order, TestTicket, utcnow
from app.safety.access import sha

TICKET_MINUTES = 15  # the form POST must come this soon after the ticket
CONFIRM_DAYS = 7  # "Yes, I got it" works for a week, once
DELIVERED = ("imap_seen", "owner_confirmed")
STALE_HOURS = 24


def aware(when: datetime | None) -> datetime | None:
    return when if when is None or when.tzinfo else when.replace(tzinfo=UTC)


def shop_tag(business: Business) -> str:
    return business.subdomain or str(business.id)


def marker(business: Business) -> str:
    """The tag every shop page carries, so a parked page with a valid certificate can't pass as the shop."""
    return f'<meta name="lw-shop" content="{shop_tag(business)}">'


# ---------- evidence ----------

def add(session: Session, *, business: Business, run_id: int | None, check: str, step: str, practice: bool,
        **fields) -> Evidence:
    from app import chain

    row = Evidence(business_id=business.id, run_id=run_id, check=check, step=step, practice=practice, **fields)
    return chain.append(session, row)  # the only way in: every row is a link in the shop's hash chain


def evidence_for_run(session: Session, run_id: int) -> list[Evidence]:
    return list(session.exec(select(Evidence).where(Evidence.run_id == run_id).order_by(Evidence.id)).all())


# ---------- test-order tickets ----------

def new_ticket(session: Session, business: Business, run_id: int | None) -> TestTicket:
    t = TestTicket(business_id=business.id, run_id=run_id, nonce=secrets.token_hex(8))
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


def open_ticket(session: Session, business: Business, nonce: str) -> TestTicket | None:
    """The unused, recent ticket for THIS shop with this nonce, else None (then it's a normal order)."""
    if not nonce or len(nonce) > 64:
        return None
    t = session.exec(select(TestTicket).where(TestTicket.nonce == nonce, TestTicket.business_id == business.id)).first()
    if t is None or t.used_at is not None or utcnow() - aware(t.created_at) > timedelta(minutes=TICKET_MINUTES):
        return None
    return t


def ticket_used(session: Session, ticket: TestTicket, order: Order) -> None:
    ticket.used_at, ticket.order_id = utcnow(), order.id
    session.add(ticket)
    session.commit()


def issue_confirm_link(session: Session, settings: Settings, ticket: TestTicket) -> str:
    raw = secrets.token_urlsafe(32)
    ticket.confirm_hash = sha(raw)
    session.add(ticket)
    session.commit()
    return f"{settings.app_base_url.rstrip('/')}/#/got-it?token={raw}"


def confirm(session: Session, raw: str) -> TestTicket | None:
    """The owner's tap. Works once, for a week. Writes `owner_confirmed` evidence on the ticket's run."""
    if not raw or len(raw) > 200:
        return None
    t = session.exec(select(TestTicket).where(TestTicket.confirm_hash == sha(raw))).first()
    if t is None or t.confirmed_at is not None or t.used_at is None:
        return None
    if utcnow() - aware(t.created_at) > timedelta(days=CONFIRM_DAYS):
        return None
    t.confirmed_at = utcnow()
    session.add(t)
    session.commit()
    b = session.get(Business, t.business_id)
    if b is not None:
        add(session, business=b, run_id=t.run_id, check="test_order", step="owner_confirmed", practice=b.practice,
            source="owner's tap on the test email", nonce=t.nonce)
        audit.record(session, actor="owner", action="test_order_confirmed", target=f"business:{b.id}", result="ok",
                     business_id=b.id, detail=f"code {t.nonce}")
    return t


# ---------- the web client the checker uses ----------

class ShopWeb(Protocol):
    source: str

    def get(self, url: str) -> Page: ...
    def post(self, url: str, fields: dict[str, str]) -> Page: ...


def real_shop_web(host: str, allow_private: bool = False) -> SafeWeb:
    """Over the internet, to this ONE shop host only (SSRF guard in SafeWeb)."""
    web = SafeWeb(lambda h: h == host.lower(), allow_private=allow_private)
    web.source = f"https://{host}"
    return web


class PracticeShopWeb:
    """Practice: the same page a customer would get (the shop template) and the same form handler,
    called in-process. Practice shops are never on the internet, so nothing else could be fetched."""

    source = "practice: the shop page and form handler, in-process"

    def __init__(self, session: Session, settings: Settings, mailer, business: Business, host: str):
        self.session, self.settings, self.mailer, self.business, self.host = session, settings, mailer, business, host

    def _mine(self, url: str) -> bool:
        from urllib.parse import urlsplit

        return (urlsplit(url).hostname or "").lower() == self.host.lower()

    def get(self, url: str) -> Page:
        from app.agents.reader import Profile
        from app.sites.render import render_site

        if not self._mine(url):
            return Page(404, "", url, error="not this shop")
        profile = Profile.model_validate_json(self.business.profile_json)
        return Page(200, render_site(profile, shop=shop_tag(self.business)), url, server="in-process")

    def post(self, url: str, fields: dict[str, str]) -> Page:
        from app.agents.reader import Profile
        from app.sites.orders import accept_order_form

        if not self._mine(url):
            return Page(404, "", url, error="not this shop")
        profile = Profile.model_validate_json(self.business.profile_json)
        status, html = accept_order_form(self.session, self.settings, self.mailer, business=self.business,
                                         profile=profile, form=fields, visitor="")
        return Page(status, html, url, server="in-process")


def in_process(ctx) -> PracticeShopWeb:
    """The fake world's way to reach a shop (also used by tests that stand in for the real server)."""
    return PracticeShopWeb(ctx.session, ctx.settings, ctx.integ.mailer, ctx.business, ctx.plan.site_host)


# ---------- reading the order form like a browser would ----------

@dataclass
class OrderForm:
    action: str
    hidden: dict[str, str]
    qty_fields: list[str]


class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.form: OrderForm | None = None
        self._in = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "order-form" and (a.get("method") or "").lower() == "post":
            self.form, self._in = OrderForm(a.get("action") or "/", {}, []), True
        elif self._in and tag == "input" and a.get("name"):
            name = a["name"]
            if (a.get("type") or "").lower() == "hidden":
                self.form.hidden[name] = a.get("value") or ""
            elif name.startswith("qty_"):
                self.form.qty_fields.append(name)

    def handle_endtag(self, tag):
        if tag == "form":
            self._in = False


def find_order_form(html: str) -> OrderForm | None:
    p = _FormParser()
    p.feed(html)
    return p.form if p.form and p.form.qty_fields else None


# ---------- what the report shows ----------

STEP_TITLES = {"dns_answer": "Address answered", "http_response": "Page opened", "form_post": "Form accepted",
               "smtp_accepted": "Mail server accepted", "imap_seen": "In the inbox",
               "owner_confirmed": "Owner confirmed"}


def iso(v: datetime | None) -> str | None:
    return v.replace(tzinfo=None).isoformat() + "Z" if v else None


def evidence_out(e: Evidence) -> dict:
    return {"check": e.check, "step": e.step, "title": STEP_TITLES.get(e.step, e.step), "at": iso(e.at),
            "source": e.source, "server": e.server, "message_id": e.message_id, "status_code": e.status_code,
            "cert_not_after": iso(e.cert_not_after), "answer": e.answer[:200], "practice": e.practice}


def summary(session: Session, run: dict | None) -> dict:
    """'5 of 6 proven, 1 needs you', with the hops behind each check. Built only from stored evidence."""
    if not run:
        return {"proven": 0, "total": 0, "needs_you": 0, "checks": {}, "last_checked_at": None, "stale": False}
    rows = evidence_for_run(session, run["id"])
    by_check: dict[str, list[dict]] = {}
    for e in rows:
        by_check.setdefault(e.check, []).append(evidence_out(e))
    proven = needs = 0
    for c in run["checks"]:
        hops = by_check.get(c["check"], [])
        c["hops"] = hops
        delivered = any(h["step"] in DELIVERED for h in hops)
        if c["check"] == "test_order" and c["passed"]:
            c["state"] = "proven" if delivered else "needs_you"
        else:
            c["state"] = "proven" if c["passed"] else "failed"
        proven += c["state"] == "proven"
        needs += c["state"] == "needs_you"
    finished = run.get("finished_at")
    stale = False
    if finished:
        at = datetime.fromisoformat(finished.rstrip("Z")).replace(tzinfo=UTC)
        stale = datetime.now(UTC) - at > timedelta(hours=STALE_HOURS)
    return {"proven": proven, "total": len(run["checks"]), "needs_you": needs, "last_checked_at": finished,
            "stale": stale}
