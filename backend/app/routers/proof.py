"""Proof routes (S9F Phase 3): the owner's "Yes, I got it", shareable read-only reports, and the
public read-only "Check any address" tool."""

import secrets
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app import audit, chain, proof
from app.agents.launch_check import latest_launched_plan
from app.checks.dns_resolver import DnsResolver, RealDnsResolver
from app.checks.safe_fetch import SafeWeb
from app.config import Settings, get_settings
from app.db import get_session
from app.models import AddressCheck, Business, CheckRun, ReportShare, utcnow
from app.routers.report import OWNER_RUNS, run_out
from app.safety.access import ActorDep, require_business_access, sha, visitor_id
from app.sites.brand import ICON_LINKS

router = APIRouter(tags=["proof"])


# ---------- "Yes, I got it" ----------

class Token(BaseModel):
    token: str = Field(max_length=200)


@router.post("/api/proof/confirm")
def confirm_test_order(body: Token, session: Annotated[Session, Depends(get_session)]) -> dict:
    """The button on the page the test email links to. Opening the link uses nothing up."""
    t = proof.confirm(session, body.token)
    if t is None:
        raise HTTPException(status_code=400, detail="This link has expired or was already used.")
    b = session.get(Business, t.business_id)
    return {"ok": True, "shop": b.name if b else ""}


# ---------- shareable read-only report ----------

@router.get("/api/businesses/{business_id}/share")
def share_status(b: Annotated[Business, Depends(require_business_access)],
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    row = active_share(session, b.id)
    return {"active": row is not None, "created_at": proof.iso(row.created_at) if row else None}


@router.post("/api/businesses/{business_id}/share")
def share_create(b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
                 settings: Annotated[Settings, Depends(get_settings)],
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    """A new link (any older one stops working). The link is shown once; only its hash is stored."""
    revoke_all(session, b.id)
    raw = secrets.token_urlsafe(24)
    session.add(ReportShare(business_id=b.id, token_hash=sha(raw)))
    session.commit()
    audit.record(session, actor=actor.label, action="report_shared", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id)
    return {"url": f"{settings.app_base_url.rstrip('/')}/r/{raw}"}


@router.delete("/api/businesses/{business_id}/share")
def share_revoke(b: Annotated[Business, Depends(require_business_access)], actor: ActorDep,
                 session: Annotated[Session, Depends(get_session)]) -> dict:
    n = revoke_all(session, b.id)
    audit.record(session, actor=actor.label, action="report_unshared", target=f"business:{b.id}", result="ok",
                 business_id=b.id, user_id=actor.user_id, detail=f"{n} link(s) stopped")
    return {"ok": True}


def active_share(session: Session, business_id: int) -> ReportShare | None:
    return session.exec(select(ReportShare).where(ReportShare.business_id == business_id,
                                                  ReportShare.revoked_at == None)).first()  # noqa: E711


def revoke_all(session: Session, business_id: int) -> int:
    rows = session.exec(select(ReportShare).where(ReportShare.business_id == business_id,
                                                  ReportShare.revoked_at == None)).all()  # noqa: E711
    for r in rows:
        r.revoked_at = utcnow()
        session.add(r)
    session.commit()
    return len(rows)


GONE = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Report not available</title>" + ICON_LINKS + "<body style='font-family:system-ui;max-width:36rem;margin:3rem auto;"
        "padding:0 1rem'><h1>This report isn't available</h1><p>The link may have been turned off by the shop owner.</p>")


@router.get("/r/{token}", response_class=HTMLResponse)
def shared_report(token: str, session: Annotated[Session, Depends(get_session)]):
    """Read-only. No customer data at all: check names, results, hop times and the servers that answered."""
    b = shared_business(session, token)
    if b is None:
        return HTMLResponse(GONE, status_code=404)
    plan = latest_launched_plan(session, b.id)
    run_row = session.exec(select(CheckRun).where(CheckRun.business_id == b.id, CheckRun.trigger.in_(OWNER_RUNS),
                                                  CheckRun.status == "done").order_by(CheckRun.id.desc())).first()
    run = run_out(session, run_row) if run_row and plan else None
    summary = proof.summary(session, run)
    from app import incidents

    html = render_shared(b, run, summary, receipt=chain.receipt(session, b.id),
                         verify_href=f"/r/{quote(token, safe='')}/verify",
                         timeline=incidents.timeline(session, b.id, public=True))
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


def shared_business(session: Session, token: str) -> Business | None:
    """The shop behind a share link, or None: unknown or revoked link, or a shop the team has paused
    (a paused shop shows no "Proven" page to the public)."""
    row = session.exec(select(ReportShare).where(ReportShare.token_hash == sha(token[:200]))).first()
    b = session.get(Business, row.business_id) if row and row.revoked_at is None else None
    return None if b is None or b.paused else b


VERIFY_PER_MINUTE = 20
_verify_hits: dict[str, deque[float]] = {}  # hashed visitor -> recent hit times (one process, in memory)


def verify_allowed(visitor: str) -> bool:
    now = time.monotonic()
    if len(_verify_hits) > 10_000:  # never grows without bound
        _verify_hits.clear()
    hits = _verify_hits.setdefault(visitor, deque())
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= VERIFY_PER_MINUTE:
        return False
    hits.append(now)
    return True


@router.get("/r/{token}/verify")
def verify_receipt(token: str, request: Request, session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    """Recompute the shop's proof chain. Answers only intact / rows / head (or where it breaks):
    no customer data, no evidence contents, not even the shop's name."""
    if not verify_allowed(visitor_id(request)):
        raise HTTPException(status_code=429, detail="That's a lot of checks for now. Please try again in a minute.")
    b = shared_business(session, token)
    if b is None:
        raise HTTPException(status_code=404, detail="This report isn't available.")
    return JSONResponse(chain.verify(session, b.id), headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


def hhmmss(iso: str | None) -> str:
    if not iso:
        return ""
    at = datetime.fromisoformat(iso.rstrip("Z")).replace(tzinfo=UTC) + timedelta(hours=5, minutes=30)
    return at.strftime("%d %b %H:%M:%S IST")


INCIDENT_WORDS = {"open": "Open", "fixed": "Fixed", "needs_you": "Needs the owner", "keeps_breaking": "Keeps breaking"}

# The Verify button: asks /r/<token>/verify to recompute the chain and says what it answered. No other data.
VERIFY_JS = """<script>
document.getElementById('lw-verify').addEventListener('click', function () {
  var out = document.getElementById('lw-verify-out'), btn = this;
  btn.disabled = true; out.textContent = 'Checking…';
  fetch(btn.getAttribute('data-href'), {headers: {'Accept': 'application/json'}})
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (v) {
      out.textContent = v.intact
        ? 'Intact: all ' + v.rows + ' saved proof steps still link up, and the latest matches this receipt' +
          (v.head && v.head.indexOf(btn.getAttribute('data-receipt')) === 0 ? '.' : ' (a newer step was added since this page loaded).')
        : 'Changed: saved proof step ' + v.altered_at + ' no longer matches what was recorded, so the steps after it can\u2019t be trusted.';
      out.style.color = v.intact ? '#166534' : '#b91c1c';
    })
    .catch(function () { out.textContent = 'We couldn\u2019t check just now. Please try again in a minute.'; })
    .finally(function () { btn.disabled = false; });
});
</script>"""


def render_timeline(timeline: list[dict]) -> str:
    if not timeline:
        return ""
    items = []
    for e in timeline:
        steps = " → ".join(escape(s["what"]) for s in e["steps"])
        items.append(f"<li><strong>{escape(e['title'])}</strong> · {INCIDENT_WORDS.get(e['status'], e['status'])} · "
                     f"{escape(hhmmss(e['opened_at']))}<br><small>{steps}</small></li>")
    return "<h2 style='font-size:1.1rem'>What went wrong, and what happened next</h2><ul>" + "".join(items) + "</ul>"


def render_shared(b: Business, run: dict | None, summary: dict, receipt: str = "", verify_href: str = "",
                  timeline: list[dict] | None = None) -> str:
    proof_line = (f"<p style='color:#6b7280;font-size:.9rem'>Receipt <code>{escape(receipt)}</code> · "
                  f"<button type=button id=lw-verify data-href='{escape(verify_href)}' data-receipt='{escape(receipt)}'>"
                  f"Verify</button> <span id=lw-verify-out role=status></span> "
                  f"<noscript><a href='{escape(verify_href)}'>verify</a></noscript><br>The receipt is a fingerprint "
                  "of every proof step saved for this shop, each linked to the one before. Verify recomputes it; if "
                  "any saved step had been edited, it says which one.</p>" + VERIFY_JS) if receipt else ""
    practice = b.practice or any(h.get("practice") for c in (run or {}).get("checks", []) for h in c.get("hops", []))
    rows = []
    for c in (run or {}).get("checks", []):
        state = {"proven": "Proven", "needs_you": "Waiting for the owner", "failed": "Not passing"}[c["state"]]
        hops = " → ".join(f"{escape(h['title'])} {escape(hhmmss(h['at']))}" for h in c.get("hops", []))
        rows.append(f"<li><strong>{escape(c['title'])}</strong> · {state}"
                    + (f"<br><small>{hops}</small>" if hops else "") + "</li>")
    head = (f"{summary['proven']} of {summary['total']} proven"
            + (f", {summary['needs_you']} waiting for the owner" if summary["needs_you"] else "")) if run else \
        "Not checked yet"
    label = "<p style='background:#fdf3d8;padding:.5rem .8rem;border-radius:8px'>Practice: these results come from a " \
            "pretend GoDaddy, not the real internet.</p>" if practice else ""
    stale = "<p style='color:#888'>These results are more than a day old.</p>" if summary.get("stale") else ""
    return ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,"
            "initial-scale=1'><meta name=robots content=noindex><title>Launch proof · " + escape(b.name) + "</title>"
            + ICON_LINKS +
            "<body style='font-family:system-ui,Arial,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;"
            "line-height:1.5;color:#1f2937'><p style='color:#6b7280'>LaunchWitness launch proof</p><h1>"
            + escape(b.name) + "</h1>" + label + f"<p><strong>{escape(head)}</strong>"
            + (f" · last checked {escape(hhmmss(summary['last_checked_at']))}" if summary.get("last_checked_at") else "")
            + "</p>" + stale + "<ul>" + "".join(rows) + "</ul><p style='color:#6b7280;font-size:.9rem'>Read-only. "
            "No customer details are shown. \"Mail server accepted\" means our mail server took the email; it is "
            "counted as delivered only when it was seen in the inbox or the owner confirmed it.</p>"
            + render_timeline(timeline or []) + proof_line + "</body></html>")


# ---------- "Check any address" (public, read-only) ----------

class Address(BaseModel):
    address: str = Field(max_length=300)


def get_public_dns() -> DnsResolver:
    """FastAPI dependency: ordinary public DNS lookups (read-only). Tests override this."""
    return RealDnsResolver()


def get_public_web() -> SafeWeb:
    """FastAPI dependency: any public https host, SSRF-guarded. Tests override this."""
    return SafeWeb(lambda _h: True, timeout=8.0)


def clean_address(raw: str) -> str | None:
    from urllib.parse import urlsplit

    from app.checks.safe_fetch import is_ip_literal
    from app.sites.hosts import HOSTNAME

    text = raw.strip().lower()
    if "://" not in text:
        text = "https://" + text
    try:
        host = (urlsplit(text).hostname or "").rstrip(".")
        if not host.isascii():  # an internationalised name (münchen.de): check its ASCII form, show it readably
            host = host.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        return None
    if not host or "." not in host or is_ip_literal(host) or not HOSTNAME.match(host) or host.endswith(".local"):
        return None
    return host


@router.post("/api/check-address")
def check_address(body: Address, request: Request, settings: Annotated[Settings, Depends(get_settings)],
                  session: Annotated[Session, Depends(get_session)],
                  dns: Annotated[DnsResolver, Depends(get_public_dns)],
                  web: Annotated[SafeWeb, Depends(get_public_web)]) -> dict:
    """Read-only public checks of any web address, in plain English. Sends no email, stores nothing
    about the address (only a hashed visitor + time, for the rate limit)."""
    host = clean_address(body.address)
    if host is None:
        raise HTTPException(status_code=422, detail="Please type a web address, like myshop.com.")
    visitor = visitor_id(request)
    hour_ago = utcnow() - timedelta(hours=1)
    mine = session.exec(select(func.count()).select_from(AddressCheck).where(
        AddressCheck.visitor == visitor, AddressCheck.created_at >= hour_ago)).one()
    everyone = session.exec(select(func.count()).select_from(AddressCheck).where(
        AddressCheck.created_at >= utcnow() - timedelta(days=1))).one()
    if mine >= settings.address_checks_per_hour or everyone >= settings.address_checks_per_day:
        raise HTTPException(status_code=429, detail="That's a lot of checks for now. Please try again in an hour.")
    session.add(AddressCheck(visitor=visitor))
    session.commit()
    from app.checks.web_setup import readable

    return {"address": host, "shown_as": readable(host), "read_only": True, "results": address_results(host, dns, web)}


def dangling_cname(name: str, dns: DnsResolver, add) -> None:
    """Read-only: if `name` is a CNAME whose target doesn't exist (NXDOMAIN), say so. No other names are tried."""
    target = next((t.rstrip(".") for t in dns.resolve(name, "CNAME")), "")
    exists = getattr(dns, "exists", None)
    if not target or exists is None:
        return
    if exists(target) is False:
        add("dangling_cname", False, f"Possible dangling record: {name} points to {target}, which doesn't exist. "
            "Anyone who claims that service could serve pages on this address.", f"CNAME {name} -> {target} (NXDOMAIN)")


def address_results(host: str, dns: DnsResolver, web: SafeWeb) -> list[dict]:
    """Read-only findings for any address: the website (`web_setup`), then its email setup (`mail_setup`).
    Each has ok (True / False a real problem / None a note or "not sure"), plain words, technical detail,
    how sure we are, and the email service's own steps. Nothing here offers or applies a fix."""
    from app.checks.mail_setup import SEEN, finding, mail_findings
    from app.checks.web_setup import web_findings

    out = web_findings(host, dns, web)

    def add(check: str, ok: bool | None, plain: str, detail: str = "") -> None:
        out.append(finding(check, ok, plain, detail, SEEN, check, "Remove that record where your domain is managed, "
                           "or point it at a service you still use."))

    zone = host.removeprefix("www.")
    for name in dict.fromkeys((zone, f"www.{zone}")):  # only the names typed: the address itself and its www
        dangling_cname(name, dns, add)
    return out + mail_findings(host, dns)
