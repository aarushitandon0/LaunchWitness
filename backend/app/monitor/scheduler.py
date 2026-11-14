"""Light monitoring (SPEC §7), with APScheduler.

- Every 15 minutes: site points + opens over HTTPS.
- Daily: the same, plus email settings and "settings unchanged since launch", and
  days left on the certificate and domain.
- A failure is re-checked once a minute later (rule out blips). If it still fails,
  the Doctor explains and applies a safe playbook fix; anything still broken is
  emailed to the owner's PERSONAL email (once per problem until it passes again).
- Domain expiry warnings at 30 / 7 / 1 days (renewal costs money: alert only).
  Certificate warnings at 7 / 1 days (Caddy renews certificates by itself well before that).
- Practice businesses use the fake world, so their "emails" never leave the server.

Switch off with MONITOR_ENABLED=false. Tests never start the scheduler; they call
the job methods directly.
"""

import json
from collections.abc import Callable
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit
from app.agents.claude_client import Claude
from app.agents.launch_check import NotLaunched, latest_launched_plan, run_checks
from app.config import Settings
from app.integrations import Integrations
from app.models import Alert, Business, CheckRun, utcnow

QUICK_MINUTES = 15
RECHECK_SECONDS = 60
QUICK_CHECKS = ["site_points", "https"]
EMAIL_CHECKS = ["email_mx", "email_spf", "email_dkim", "email_dmarc"]
DOMAIN_WARN_DAYS = (30, 7, 1)
CERT_WARN_DAYS = (7, 1)


def daily_checks(mode: str) -> list[str]:
    return QUICK_CHECKS + (EMAIL_CHECKS if mode == "full" else []) + ["settings_match"]


class Monitor:
    def __init__(self, engine: Engine, settings: Settings, integ_for: Callable[[Business], Integrations],
                 claude: Claude, scheduler: BackgroundScheduler | None = None):
        self.engine, self.settings, self.integ_for, self.claude = engine, settings, integ_for, claude
        self.scheduler = scheduler or BackgroundScheduler(timezone="UTC")

    # ---------- scheduler wiring ----------

    def register(self) -> None:
        self.scheduler.add_job(self.run_quick, "interval", minutes=QUICK_MINUTES, id="monitor_quick",
                               replace_existing=True, max_instances=1, coalesce=True)
        self.scheduler.add_job(self.run_daily, "interval", days=1, id="monitor_daily",
                               replace_existing=True, max_instances=1, coalesce=True)

    def start(self) -> None:
        self.register()
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule_recheck(self, business_id: int, names: list[str]) -> None:
        self.scheduler.add_job(self.recheck, "date", run_date=utcnow() + timedelta(seconds=RECHECK_SECONDS),
                               args=[business_id, names], id=f"recheck-{business_id}", replace_existing=True)

    # ---------- jobs ----------

    def live_business_ids(self) -> list[int]:
        with Session(self.engine) as s:
            return list(s.exec(select(Business.id).where(Business.status == "live")).all())

    def run_quick(self) -> None:
        for bid in self.live_business_ids():
            self.check_business(bid, "quick")

    def run_daily(self) -> None:
        for bid in self.live_business_ids():
            self.check_business(bid, "daily")

    def _context(self, business_id: int):
        with Session(self.engine) as s:
            b = s.get(Business, business_id)
            plan = latest_launched_plan(s, business_id) if b else None
            if b is None or plan is None:
                return None
            s.expunge_all()
            return b, plan

    def check_business(self, business_id: int, kind: str) -> list[str]:
        """Run the quick or daily checks without fixing. Returns the failing check names."""
        found = self._context(business_id)
        if found is None:
            return []
        b, plan = found
        names = QUICK_CHECKS if kind == "quick" else daily_checks(plan.mode)
        try:
            summary = run_checks(self.engine, self.settings, self.integ_for(b), self.claude, plan.id,
                                 trigger=f"monitor_{kind}", names=names, fix=False)
        except NotLaunched:
            return []
        failing = [f.check for f in summary.failed]
        if failing:
            self.schedule_recheck(business_id, failing)
        else:
            self.resolve(business_id, names)
        if kind == "daily":
            self.expiry_alerts(business_id, summary.run_id)
        return failing

    def recheck(self, business_id: int, names: list[str]) -> list[str]:
        """A minute later: re-check; the Doctor fixes what it safely can; alert on what's left."""
        found = self._context(business_id)
        if found is None:
            return []
        b, plan = found
        summary = run_checks(self.engine, self.settings, self.integ_for(b), self.claude, plan.id,
                             trigger="monitor_recheck", names=names, fix=True)
        still = summary.failed
        self.resolve(business_id, [n for n in names if n not in {f.check for f in still}])
        for f in still:
            self.alert(business_id, "check_failed", f.check,
                       subject=f"Something needs attention on {plan.site_host}",
                       body=(f"Hello,\n\nOur regular check of your website found a problem we couldn't fix by ourselves:\n\n"
                             f"  {f.plain}\n\nOpen your launch report (from your saved owner link) to see the details and "
                             f"press \"Run checks now\" after any change.\n\n— LaunchWitness"))
        return [f.check for f in still]

    # ---------- alerts ----------

    def resolve(self, business_id: int, names: list[str]) -> None:
        with Session(self.engine) as s:
            for a in s.exec(select(Alert).where(Alert.business_id == business_id, Alert.kind == "check_failed",
                                                Alert.resolved_at == None)).all():  # noqa: E711
                if a.key in names:
                    a.resolved_at = utcnow()
                    s.add(a)
            s.commit()

    def alert(self, business_id: int, kind: str, key: str, *, subject: str, body: str) -> bool:
        """Email the owner's personal address once per (kind, key) until resolved. True if sent."""
        with Session(self.engine) as s:
            b = s.get(Business, business_id)
            open_ = s.exec(select(Alert).where(Alert.business_id == business_id, Alert.kind == kind,
                                               Alert.key == key, Alert.resolved_at == None)).first()  # noqa: E711
            if open_ is not None:
                return False
            if not b.owner_email:
                audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result="skipped",
                             business_id=business_id, detail="no personal email saved")
                return False
            try:
                self.integ_for(b).mailer.send(to=b.owner_email, subject=subject, body=body)
            except Exception as e:
                audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result="failed",
                             business_id=business_id, detail=type(e).__name__)
                return False
            s.add(Alert(business_id=business_id, kind=kind, key=key, sent_to=b.owner_email))
            s.commit()
            audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result="sent",
                         business_id=business_id, detail=subject)
            return True

    def expiry_alerts(self, business_id: int, run_id: int) -> None:
        with Session(self.engine) as s:
            run = s.get(CheckRun, run_id)
            info = json.loads(run.info_json) if run else {}
        self._expiry(business_id, "domain_expiry", info.get("domain_days_left"), DOMAIN_WARN_DAYS,
                     lambda d: (f"Your website name ends in {d} day{'s' if d != 1 else ''}",
                                f"Hello,\n\nYour website name (domain) runs out in {d} day{'s' if d != 1 else ''}. "
                                "Renewing it costs money, so we won't do it for you. Please renew it on godaddy.com "
                                "before then, or your website and order emails will stop working.\n\n— LaunchWitness"))
        self._expiry(business_id, "cert_expiry", info.get("cert_days_left"), CERT_WARN_DAYS,
                     lambda d: (f"Your website's security certificate ends in {d} day{'s' if d != 1 else ''}",
                                f"Hello,\n\nYour website's security certificate (the padlock) runs out in {d} "
                                f"day{'s' if d != 1 else ''} and hasn't renewed itself yet. It costs nothing and you "
                                "don't need to do anything — we're looking into it.\n\n— LaunchWitness"))

    def _expiry(self, business_id: int, kind: str, days: int | None, thresholds: tuple[int, ...], text) -> None:
        if days is None:
            return
        crossed = [t for t in thresholds if days <= t]
        if not crossed:  # renewed (or far away): clear old warnings so the next cycle warns again
            with Session(self.engine) as s:
                for a in s.exec(select(Alert).where(Alert.business_id == business_id, Alert.kind == kind,
                                                    Alert.resolved_at == None)).all():  # noqa: E711
                    a.resolved_at = utcnow()
                    s.add(a)
                s.commit()
            return
        nearest = min(crossed)
        subject, body = text(max(days, 0))
        if self.alert(business_id, kind, f"{nearest}d", subject=subject, body=body):
            with Session(self.engine) as s:  # skip the bigger thresholds we're already past
                for t in crossed:
                    seen = s.exec(select(Alert).where(Alert.business_id == business_id, Alert.kind == kind,
                                                      Alert.key == f"{t}d", Alert.resolved_at == None)).first()  # noqa: E711
                    if t != nearest and seen is None:
                        s.add(Alert(business_id=business_id, kind=kind, key=f"{t}d", sent_to="(skipped)"))
                s.commit()

