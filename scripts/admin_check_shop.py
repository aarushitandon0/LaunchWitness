"""Team tool (S19B): run one round of checks for a shop from the command line, inside the app container, through the
same code the app uses. Prints results, the test email's SUBJECT only (never addresses, bodies or secrets), the
shared-report count and whether the proof chain is intact. Every run is audited (actor "admin (cli)").

    docker compose ... exec -T app python /app/scripts/admin_check_shop.py <subdomain> manual|daily

manual = what "Run checks now" does (test email to the shop's order address, with "Yes, I got it").
daily  = one daily monitoring round (test email to LaunchWitness's check mailbox), plus the later inbox passes.
"""

import json
import sys
import time

from sqlmodel import Session, select

from app import audit, chain, proof
from app.agents.launch_check import latest_launched_plan, run_checks
from app.config import get_settings
from app.db import get_engine
from app.integrations import for_business, get_integrations, get_practice_integrations
from app.models import Business, CheckResult, CheckRun, Order, Outbox, TestTicket
from app.routers.businesses import get_claude
from app.routers.report import run_out
from app.sites.orders import TEST_BANNER


def since_of(t: TestTicket):
    from datetime import UTC, timedelta

    at = t.created_at if t.created_at.tzinfo else t.created_at.replace(tzinfo=UTC)
    return at - timedelta(minutes=2)


def main(subdomain: str, kind: str) -> int:
    settings, engine = get_settings(), get_engine()
    server, practice = get_integrations(), get_practice_integrations()
    integ_for = lambda b: for_business(b, server, practice)  # noqa: E731
    claude = get_claude(settings)
    with Session(engine) as s:
        b = s.exec(select(Business).where(Business.subdomain == subdomain)).first()
        if b is None:
            print("no such shop")
            return 2
        plan = latest_launched_plan(s, b.id)
        audit.record(s, actor="admin (cli)", action="run_checks_now" if kind == "manual" else "monitor_daily_now",
                     target=plan.site_host, result="ok", business_id=b.id, detail="scripts/admin_check_shop.py")
        bid, plan_id = b.id, plan.id
    if kind == "manual":
        summary = run_checks(engine, settings, integ_for(b), claude, plan_id, trigger="manual")
        run_id = summary.run_id
    else:
        from app.monitor.scheduler import Monitor

        mon = Monitor(engine, settings, integ_for, claude)
        mon.check_business(bid, "daily")
        jobs = [j for j in mon.scheduler.get_jobs() if j.id.startswith("inbox-")]
        for job in jobs:  # the later inbox passes the running scheduler would do, one minute apart
            _b, run_id, item, n = job.args
            while True:
                time.sleep(60)
                got = mon.inbox_pass(bid, run_id, item, n)
                print("inbox pass", n, got)
                if got != "later":
                    break
                n += 1
        with Session(engine) as s:
            run_id = s.exec(select(CheckRun.id).where(CheckRun.business_id == bid, CheckRun.trigger == "monitor_daily")
                            .order_by(CheckRun.id.desc())).first()
    with Session(engine) as s:
        run = s.get(CheckRun, run_id)
        out = run_out(s, run)
        counts = proof.summary(s, out)
        print(f"run {run.id} trigger={run.trigger} passed={run.passed} "
              f"proven {counts['proven']} of {counts['total']}, needs you {counts['needs_you']}")
        for c in out["checks"]:
            print(f"  {c['check']:<12} {c.get('state', ''):<10} {c['title']}  | {c['plain'][:110]}")
            if c["check"] == "test_order":
                print("     hops:", " -> ".join(h["title"] for h in c["hops"]))
        t = s.exec(select(TestTicket).where(TestTicket.run_id == run.id)).first()
        if t and t.order_id:
            o = s.get(Order, t.order_id)
            row = s.exec(select(Outbox).where(Outbox.key == f"order:{o.id}")).first()
            app_box = settings.smtp_user.lower()
            print(f"  test ticket audience={t.audience or 'order address'} confirm_link={'yes' if t.confirm_hash else 'no'}")
            print(f"  test email to the check mailbox: {app_box in row.to_addr.lower()}; recipients: "
                  f"{len([a for a in row.to_addr.split(',') if a.strip()])}")
            found = [] if server.fake else server.inbox.find(subject_contains=t.nonce, since=since_of(t))
            for m in found[:1]:
                print(f"  IMAP subject: {m.subject}")
                print(f"  body opens with the TEST banner: {m.body.lstrip().startswith(TEST_BANNER)}; "
                      f"no customer links: {'wa.me' not in m.body and 'tel:' not in m.body}")
        print("  chain:", json.dumps(chain.verify(s, bid))[:200])
        latest = s.exec(select(CheckResult).where(CheckResult.business_id == bid).order_by(CheckResult.id.desc())).first()
        print("  latest result row:", latest.check if latest else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "manual"))
