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

from app import audit, renewals
from app.agents.claude_client import Claude
from app.agents.launch_check import AlreadyChecking, NotLaunched, latest_launched_plan, run_checks
from app.config import Settings
from app.integrations import Integrations
from app.models import Alert, Business, CheckRun, utcnow
from app.safety.access import owner_emails

QUICK_MINUTES = 15
RECHECK_SECONDS = 60
QUICK_CHECKS = ["site_points", "https"]
EMAIL_CHECKS = ["email_mx", "email_spf", "email_dkim", "email_dmarc"]  # read-only on shops under the app's domain
DOMAIN_WARN_DAYS = renewals.THRESHOLDS  # one set for everything a person renews (S10)
CERT_WARN_DAYS = renewals.CERT_THRESHOLDS


def daily_checks(mode: str) -> list[str]:
    # The daily test order carries a fresh code. For an inbox we can't read it proves "form accepted ->
    # mail server accepted" only (the report says so); delivery needs the owner's tap on that email.
    return QUICK_CHECKS + EMAIL_CHECKS + ["settings_match", "test_order"]


class Monitor:
    def __init__(self, engine: Engine, settings: Settings, integ_for: Callable[[Business], Integrations],
                 claude: Claude, scheduler: BackgroundScheduler | None = None, team: Integrations | None = None):
        self.engine, self.settings, self.integ_for, self.claude = engine, settings, integ_for, claude
        self.team = team  # the server's own integrations: the app domain, the team mailbox, the app zone
        self.scheduler = scheduler or BackgroundScheduler(timezone="UTC")

    # ---------- scheduler wiring ----------

    def register(self) -> None:
        self.scheduler.add_job(self.run_quick, "interval", minutes=QUICK_MINUTES, id="monitor_quick",
                               replace_existing=True, max_instances=1, coalesce=True)
        self.scheduler.add_job(self.run_daily, "interval", days=1, id="monitor_daily",
                               replace_existing=True, max_instances=1, coalesce=True)
        if self.team is not None:
            self.scheduler.add_job(self.team_renewals, "interval", days=1, id="team_renewals",
                                   replace_existing=True, max_instances=1, coalesce=True)
            self.scheduler.add_job(self.zone_hygiene, "interval", days=1, id="zone_hygiene",
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
        """Shops to watch: live, not paused. Guest practice shops are short-lived and aren't watched."""
        with Session(self.engine) as s:
            return list(s.exec(select(Business.id).where(Business.status == "live", Business.paused == False,  # noqa: E712
                                                         Business.guest_hash == "")).all())

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
        except (NotLaunched, AlreadyChecking):  # e.g. the owner just pressed "Run checks now": skip this round
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
        try:
            summary = run_checks(self.engine, self.settings, self.integ_for(b), self.claude, plan.id,
                                 trigger="monitor_recheck", names=names, fix=True)
        except (NotLaunched, AlreadyChecking):
            return []
        still = summary.failed
        self.resolve(business_id, [n for n in names if n not in {f.check for f in still}])
        for f in still:
            self.alert(business_id, "check_failed", f.check,
                       subject=f"Something needs attention on {plan.site_host}",
                       body=(f"Hello,\n\nOur regular check of your website found a problem we couldn't fix by ourselves:\n\n"
                             f"  {f.plain}\n\nSign in to LaunchWitness and open your shop's report to see the details, and "
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
            to = ", ".join(owner_emails(s, business_id))
            if not to:
                audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result="skipped",
                             business_id=business_id, detail="the shop has no signed-in owner")
                return False
            try:
                self.integ_for(b).mailer.send(to=to, subject=subject, body=body)
            except Exception as e:
                audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result="failed",
                             business_id=business_id, detail=type(e).__name__)
                return False
            s.add(Alert(business_id=business_id, kind=kind, key=key, sent_to=to))
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


    # ---------- the team's own renewals (S10): the app domain and the team mailbox ----------

    def team_renewals(self, today=None) -> list[str]:
        """Email ADMIN_EMAIL at 30 / 7 / 1 days before the app domain or the team mailbox runs out. Never renews
        or pays: both cost money, so a person decides. Returns the alert keys sent this time."""
        from datetime import date

        from app.agents.launch_check import days_left
        from app.models import TeamAlert

        domain_days = None
        if self.team is not None:
            try:
                domain_days = days_left(self.team.godaddy.domain_expires(self.settings.app_domain))
            except Exception as e:  # informational; try again tomorrow
                with Session(self.engine) as s:
                    audit.record(s, actor="monitor", action="team_renewals", target=self.settings.app_domain,
                                 result="failed", detail=type(e).__name__)
        sent: list[str] = []
        for kind, days, what in (
                ("app_domain_expiry", domain_days, f"the app domain {self.settings.app_domain}"),
                ("mailbox_expiry", renewals.mailbox_days(self.settings, today or date.today()),
                 f"the team mailbox {self.settings.smtp_user} (sign-in links, orders and alerts all use it)")):
            hit = renewals.crossed(days, renewals.THRESHOLDS)
            with Session(self.engine) as s:
                open_ = s.exec(select(TeamAlert).where(TeamAlert.kind == kind, TeamAlert.resolved_at == None)).all()  # noqa: E711
                if not hit:  # renewed (or far away): the next cycle warns again
                    for a in open_:
                        a.resolved_at = utcnow()
                        s.add(a)
                    s.commit()
                    continue
                key = f"{min(hit)}d"
                if any(a.key == key for a in open_):
                    continue  # this threshold was already sent
                to = self.settings.admin_email.strip()
                subject = f"LaunchWitness: {what.split(' (')[0]} runs out in {max(days, 0)} day(s)"
                body = (f"Hello team,\n\n{what[0].upper() + what[1:]} runs out in {max(days, 0)} day(s). "
                        "Renewing costs money, so LaunchWitness won't do it: please renew it on godaddy.com.\n\n"
                        "- LaunchWitness monitoring")
                result = "skipped"
                if to and self.team is not None:
                    try:
                        self.team.mailer.send(to=to, subject=subject, body=body)
                        result = "sent"
                    except Exception as e:
                        result = f"failed: {type(e).__name__}"
                if result == "sent":
                    for t in hit:  # bigger thresholds we're already past count as sent too
                        if not any(a.key == f"{t}d" for a in open_):
                            s.add(TeamAlert(kind=kind, key=f"{t}d", sent_to=to if t == min(hit) else "(skipped)"))
                    sent.append(f"{kind}:{key}")
                s.commit()
                audit.record(s, actor="monitor", action=f"alert_{kind}", target=key, result=result.split(":")[0],
                             detail=subject)
        return sent

    def zone_hygiene(self) -> int:
        """Daily: compare the app zone's shop A records with the shops (proposals only; the admin decides)."""
        from app.zone_hygiene import scan

        if self.team is None:
            return 0
        try:
            return len(scan(self.engine, self.settings, self.team.godaddy))
        except Exception as e:
            with Session(self.engine) as s:
                audit.record(s, actor="zone_hygiene", action="zone_scan", target=self.settings.app_domain,
                             result="failed", detail=type(e).__name__)
            return 0
