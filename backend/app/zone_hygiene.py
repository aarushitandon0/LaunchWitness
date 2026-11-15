"""Zone hygiene for our own shop zone (S10, feature 16, scoped down).

Once a day we compare every A record on the app's domain with the shops in the database:
- **dangling**: a record for a shop name that is deleted, not live, or practice. Anyone who later takes that
  name would inherit a working address, and a stray record points customers at a "not found" page.
- **missing**: a live shop whose address has no record: customers can't reach it.
- **wrong_target**: a shop's record points anywhere other than SERVER_IP.

Nothing is changed by the scan. Each finding carries a proposed fix; the admin approves it on the team page,
and only then is it applied through the guarded GoDaddy client (which itself refuses anything but an A record
for a shop name). Never `@`, `www`, `*`, a reserved name, MX, TXT or CNAME. Every step is audit-logged.
"""

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.config import Settings
from app.models import Business, ZoneFinding, utcnow
from app.sites.hosts import slug_problem

TTL = 600


def shop_names(records: list[dict]) -> dict[str, list[str]]:
    """A records whose name could be a shop (everything else in the zone is never looked at)."""
    out: dict[str, list[str]] = {}
    for r in records:
        name = str(r.get("name", "")).lower()
        if r.get("type") == "A" and name not in ("@", "www", "*") and slug_problem(name) is None:
            out.setdefault(name, []).append(str(r.get("data", "")))
    return out


def compare(settings: Settings, session: Session, records: list[dict]) -> list[dict]:
    """What's wrong right now: [{kind, name, found, want, fix, plain, business_id}]. Reads only."""
    zone, ip = settings.app_domain, settings.server_ip
    # On a practice server the "real" zone is the pretend one that practice launches write to as well.
    real = (lambda b: True) if settings.use_fakes else (lambda b: not b.practice)
    have = shop_names(records)
    shops = {b.subdomain: b for b in session.exec(select(Business).where(Business.subdomain != None)).all()}  # noqa: E711
    out = []
    for name, datas in sorted(have.items()):
        b = shops.get(name)
        if b is None or not real(b) or b.status != "live":
            why = "no shop has this name" if b is None else "this shop isn't live"
            out.append({"kind": "dangling", "name": name, "found": ", ".join(datas), "want": "", "fix": "delete",
                        "business_id": b.id if b else None,
                        "plain": f"{name}.{zone} still points at a server, but {why}. Remove the record."})
        elif sorted(datas) != [ip]:
            out.append({"kind": "wrong_target", "name": name, "found": ", ".join(datas), "want": ip, "fix": "set",
                        "business_id": b.id,
                        "plain": f"{name}.{zone} points at {', '.join(datas)}, not at our server {ip}. Point it here."})
    for name, b in sorted(shops.items()):
        if b.status == "live" and real(b) and name not in have and slug_problem(name) is None:
            out.append({"kind": "missing", "name": name, "found": "", "want": ip, "fix": "set", "business_id": b.id,
                        "plain": f"{b.name} is live but {name}.{zone} has no address record. Add it."})
    return out


def scan(engine: Engine, settings: Settings, godaddy) -> list[ZoneFinding]:
    """Read the zone, record new findings as proposals, close the ones that went away. Returns open findings."""
    records = godaddy.get_records(settings.app_domain)
    with Session(engine) as s:
        now = compare(settings, s, records)
        keys = {(f["kind"], f["name"]) for f in now}
        open_ = s.exec(select(ZoneFinding).where(ZoneFinding.status == "open")).all()
        for f in open_:
            if (f.kind, f.name) not in keys:
                f.status, f.decided_at, f.result = "gone", utcnow(), "no longer found"
                s.add(f)
        known = {(f.kind, f.name) for f in open_}
        for f in now:
            if (f["kind"], f["name"]) not in known:
                s.add(ZoneFinding(**f))
                audit.record(s, actor="zone_hygiene", action="zone_finding", target=f"A {f['name']}",
                             result="proposed", business_id=None, detail=f["plain"][:300])
        s.commit()
        audit.record(s, actor="zone_hygiene", action="zone_scan", target=settings.app_domain, result="ok",
                     detail=f"{len(records)} records read, {len(now)} finding(s)")
        return list(s.exec(select(ZoneFinding).where(ZoneFinding.status == "open")).all())


class NoLongerTrue(Exception):
    pass


def approve(engine: Engine, settings: Settings, godaddy, finding_id: int, by: str) -> ZoneFinding:
    """The admin said yes: check the finding still holds, then apply its fix through the guarded client."""
    with Session(engine) as s:
        f = s.get(ZoneFinding, finding_id)
        if f is None or f.status != "open":
            raise LookupError("finding")
        still = {(x["kind"], x["name"]): x for x in compare(settings, s, godaddy.get_records(settings.app_domain))}
        if (f.kind, f.name) not in still:
            f.status, f.decided_at, f.decided_by, f.result = "gone", utcnow(), by, "no longer true when approved"
            s.add(f)
            s.commit()
            raise NoLongerTrue(f.name)
        before = f.found
        try:
            if f.fix == "delete":
                godaddy.delete_records(settings.app_domain, "A", f.name)
            else:
                godaddy.set_records(settings.app_domain, "A", f.name, [{"data": settings.server_ip, "ttl": TTL}])
            f.status, f.result = "fixed", "ok"
        except Exception as e:  # e.g. the guard refused, or GoDaddy failed: stays open, nothing assumed
            f.result = f"failed: {type(e).__name__}"
        f.decided_at, f.decided_by = utcnow(), by
        s.add(f)
        s.commit()
        audit.record(s, actor="admin", action="zone_fix", target=f"A {f.name}", result="ok" if f.status == "fixed" else "failed",
                     detail=f"{f.fix} {f.name}: before [{before}] after [{'' if f.fix == 'delete' else settings.server_ip}]"
                            f" approved by {by}; {f.result}"[:300])
        s.refresh(f)
        return f


def dismiss(engine: Engine, finding_id: int, by: str) -> ZoneFinding:
    with Session(engine) as s:
        f = s.get(ZoneFinding, finding_id)
        if f is None or f.status != "open":
            raise LookupError("finding")
        f.status, f.decided_at, f.decided_by, f.result = "dismissed", utcnow(), by, "left as it is"
        s.add(f)
        s.commit()
        audit.record(s, actor="admin", action="zone_dismiss", target=f"A {f.name}", result="ok", detail=f"by {by}")
        s.refresh(f)
        return f


def finding_out(f: ZoneFinding) -> dict:
    return {"id": f.id, "kind": f.kind, "name": f.name, "found": f.found, "want": f.want, "fix": f.fix,
            "plain": f.plain, "status": f.status, "result": f.result, "business_id": f.business_id,
            "created_at": f.created_at.isoformat(), "decided_by": f.decided_by}
