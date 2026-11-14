"""Planner (code only): every step, DNS setting and cost of a launch, before anything happens.

Two modes, same engine:
- sandbox: free site at <subdomain>.<APP_DOMAIN>; one A record on the app's own zone;
  orders go to the app mailbox.
- full: the seller's own domain (bought by the owner, or by the guarded purchase step);
  A record, mailbox, and email records (MX, SPF, DKIM, DMARC) on that domain.

The plan's `dns_json` is the before/after diff shown on the approval card.
"""

import json
from datetime import datetime

from sqlmodel import Session, select

from app import audit
from app.config import Settings
from app.godaddy.email import TITAN_MX, TITAN_SPF
from app.integrations import Integrations
from app.models import Business, Plan
from app.agents.namer import DOMAIN

DKIM_PENDING = "(filled in after your mailbox is created)"
DMARC = "v=DMARC1; p=quarantine; adkim=r; aspf=r"
TTL = 600


class PlanError(ValueError):
    """Message is shown to the seller as-is."""


def step(sid: str, kind: str, title: str, detail: str) -> dict:
    return {"id": sid, "kind": kind, "title": title, "detail": detail, "status": "pending", "message": "",
            "started_at": None, "finished_at": None}


def _texts(records: list[dict]) -> list[str]:
    out = []
    for r in records:
        if r["type"] == "MX":
            out.append(f"{r.get('priority', 10)} {r['data']}")
        else:
            out.append(r["data"])
    return out


def change(zone: str, rtype: str, name: str, before_zone: list[dict], after: list[dict], say: str,
           deferred: bool = False) -> dict:
    before = [r for r in before_zone if r["type"] == rtype and r["name"] == name]
    after = [{"type": rtype, "name": name, "ttl": TTL, **r} for r in after]
    return {"zone": zone, "type": rtype, "name": name, "before": before, "after": after, "say": say,
            "deferred": deferred, "before_text": _texts(before), "after_text": _texts(after)}


def fqdn(zone: str, name: str) -> str:
    return zone if name == "@" else f"{name}.{zone}"


def active_plan(session: Session, business_id: int) -> Plan | None:
    return session.exec(
        select(Plan).where(Plan.business_id == business_id, Plan.status.in_(("approved", "running")))  # type: ignore[attr-defined]
    ).first()


def build_plan(session: Session, settings: Settings, integ: Integrations, business: Business, *, mode: str,
               domain: str | None = None) -> Plan:
    if active_plan(session, business.id) is not None:
        raise PlanError("A launch is already running for this business. Please wait for it to finish.")
    if not settings.server_ip:
        raise PlanError("The server address isn't configured yet (SERVER_IP).")
    if mode == "sandbox":
        plan = _sandbox(session, settings, integ, business)
    elif mode == "full":
        plan = _full(session, settings, integ, business, (domain or "").strip().lower())
    else:
        raise PlanError("Unknown launch type.")
    session.add(plan)
    session.commit()
    session.refresh(plan)
    audit.record(session, actor="planner", action="plan_created", target=plan.site_host, result="ok",
                 business_id=business.id, detail=f"plan #{plan.id} {plan.mode}, ${plan.total_cost_usd:.2f}")
    return plan


def _sandbox(session: Session, settings: Settings, integ: Integrations, business: Business) -> Plan:
    if not business.subdomain:
        raise PlanError("Please choose your website address first.")
    zone, sub = settings.app_domain, business.subdomain
    host = fqdn(zone, sub)
    current = integ.godaddy.get_records(zone)
    changes = [change(zone, "A", sub, current, [{"data": settings.server_ip}],
                      f"Point {host} to your website")]
    steps = [
        step("backup", "backup_dns", "Save a copy of the current settings",
             f"Read every DNS record on {zone} and store it as JSON so any change can be undone."),
        step("point", "point_site", f"Point {host} to your website",
             f"Set A {sub}.{zone} → {settings.server_ip} (TTL {TTL})."),
        step("mailbox", "use_app_mailbox", "Send your orders to the LaunchWitness inbox",
             f"Practice launch: order emails go to {settings.smtp_user}."),
        step("wait", "wait_dns", "Wait until the internet sees the change",
             f"Ask GoDaddy's nameservers for {host} until it answers {settings.server_ip}."),
        step("live", "go_live", "Turn your website on",
             f"Mark the business live; HTTPS is issued on first visit (Caddy on-demand TLS, ask = {host})."),
    ]
    return Plan(business_id=business.id, mode="sandbox", zone=zone, site_host=host, mailbox=settings.smtp_user,
                steps_json=json.dumps(steps), dns_json=json.dumps(changes), total_cost_usd=0.0)


def _full(session: Session, settings: Settings, integ: Integrations, business: Business, domain: str) -> Plan:
    if not DOMAIN.match(domain):
        raise PlanError("That doesn't look like a website name we can use (for example: meerascakes.in).")
    if domain == settings.app_domain or domain.endswith("." + settings.app_domain):
        raise PlanError("That name belongs to LaunchWitness. Please pick your own.")
    other = session.exec(select(Business).where(Business.domain == domain, Business.id != business.id)).first()
    if other is not None:
        raise PlanError("That name is already used by another business here.")

    owned = integ.godaddy.is_owned(domain)
    price = 0.0
    if not owned:
        quote = integ.availability.check([domain])[0]
        if not quote.available or quote.price_usd is None:
            raise PlanError(f"Sorry, {domain} is no longer available. Please pick another name.")
        price = float(quote.price_usd)

    current = integ.godaddy.get_records(domain) if owned else []
    mailbox = f"orders@{domain}"
    other_txt = [{"data": r["data"]} for r in current
                 if r["type"] == "TXT" and r["name"] == "@" and not r["data"].lower().startswith("v=spf1")]
    changes = [
        change(domain, "A", "@", current, [{"data": settings.server_ip}], f"Point {domain} to your website"),
        change(domain, "MX", "@", current, [{"data": host, "priority": prio} for prio, host in TITAN_MX],
               f"Deliver email for {domain} to your mailbox"),
        change(domain, "TXT", "@", current, other_txt + [{"data": TITAN_SPF}],
               "Allow your mailbox to send email for you (so it doesn't land in spam)"),
        change(domain, "TXT", "titan1._domainkey", current, [{"data": DKIM_PENDING}],
               "Sign your emails so customers can trust they're from you", deferred=True),
        change(domain, "TXT", "_dmarc", current, [{"data": DMARC}],
               "Tell email services to treat fake emails in your name as spam"),
    ]
    buy_title = f"Use {domain}, which you already own" if owned else f"Buy {domain} (${price:.2f} for the first year)"
    steps = [
        step("domain", "get_domain", buy_title,
             "Already in the GoDaddy account: adopt it." if owned else
             f"Purchase only if ALLOW_PURCHASE=true, cost ≤ MAX_SPEND_USD and your approval of ${price:.2f}."),
        step("backup", "backup_dns", "Save a copy of the current settings",
             f"Read every DNS record on {domain} and store it as JSON so any change can be undone."),
        step("point", "point_site", f"Point {domain} to your website", f"Set A @ → {settings.server_ip}."),
        step("mailbox", "setup_mailbox", f"Create your email address {mailbox}",
             "Create or adopt the mailbox, then check every 10 seconds until it's ready (retries if busy)."),
        step("email", "email_records", "Set up your email settings",
             "Set MX, SPF (TXT @), DKIM (TXT titan1._domainkey, value from the mailbox service) and DMARC."),
        step("wait", "wait_dns", "Wait until the internet sees the changes",
             f"Ask GoDaddy's nameservers for {domain} until it answers {settings.server_ip}."),
        step("live", "go_live", "Turn your website on",
             "Mark the business live; HTTPS is issued on first visit (Caddy on-demand TLS)."),
    ]
    return Plan(business_id=business.id, mode="full", zone=domain, site_host=domain, mailbox=mailbox,
                steps_json=json.dumps(steps), dns_json=json.dumps(changes), total_cost_usd=price)


def plan_out(plan: Plan) -> dict:
    def iso(v):
        return v.replace(tzinfo=None).isoformat() + "Z" if isinstance(v, datetime) else v

    return {
        "id": plan.id, "business_id": plan.business_id, "mode": plan.mode, "zone": plan.zone,
        "site_host": plan.site_host, "mailbox": plan.mailbox, "status": plan.status,
        "total_cost_usd": plan.total_cost_usd, "steps": json.loads(plan.steps_json),
        "changes": json.loads(plan.dns_json), "created_at": iso(plan.created_at),
    }

