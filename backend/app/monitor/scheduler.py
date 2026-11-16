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
import threading
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from app import audit, outbox, renewals
from app.agents.claude_client import Claude
from app.agents.launch_check import AlreadyChecking, NotLaunched, latest_launched_plan, run_checks
from app.config import Settings
from app.integrations import Integrations
from app.models import Alert, Business, CheckRun, utcnow
from app.safety.access import owner_emails

QUICK_MINUTES = 15
OUTBOX_SECONDS = 20  # S13: how often the outbox's sender job looks for due email
RECHECK_SECONDS = 60
SHOP_BUDGET = {"quick": 90, "daily": 300, "recheck": 300}  # seconds one shop may take in a round
# S13 B: one check may take at most this long before we stop waiting for it ("couldn't finish"). Above the padlock
# check's own 2-minute retry for a certificate being issued, so a real slow issue is still seen as a failure.
CHECK_WATCHDOG = 150
ROUND_DEADLINE = {"quick": 12 * 60, "daily": 40 * 60}  # a round stops waiting for a shop after this (it keeps going)
TICK_SECONDS = 60  # the scheduler beat: each tick checks only the shops whose slot it is
DAILY_SLOTS = 24 * 60  # one slot a minute through the day
OVERDUE = {"quick": timedelta(minutes=QUICK_MINUTES + 5), "daily": timedelta(hours=25)}
INBOX_PASS_SECONDS, INBOX_PASSES = 60, 3  # the test order's later inbox look: every minute, three times
FLAP_WINDOW = timedelta(days=1)
QUICK_CHECKS = ["site_points", "https"]
EMAIL_CHECKS = ["email_mx", "email_spf", "email_dkim", "email_dmarc"]  # read-only on shops under the app's domain
DOMAIN_WARN_DAYS = renewals.THRESHOLDS  # one set for everything a person renews (S10)
CERT_WARN_DAYS = renewals.CERT_THRESHOLDS


def daily_checks(mode: str) -> list[str]:
    # The daily test order carries a fresh code. For an inbox we can't read it proves "form accepted ->
    # mail server accepted" only (the report says so); delivery needs the owner's tap on that email.
    return QUICK_CHECKS + EMAIL_CHECKS + ["settings_match", "test_order"]


def proof_aware(when):
    """SQLite hands datetimes back without a timezone; ours are always UTC."""
    return when if when.tzinfo is not None else when.replace(tzinfo=utcnow().tzinfo)


class Monitor:
    def __init__(self, engine: Engine, settings: Settings, integ_for: Callable[[Business], Integrations],
                 claude: Claude, scheduler: BackgroundScheduler | None = None, team: Integrations | None = None,
                 mailer_for: Callable | None = None):
        self.engine, self.settings, self.integ_for, self.claude = engine, settings, integ_for, claude
        self.team = team  # the server's own integrations: the app domain, the team mailbox, the app zone
        self.mailer_for = mailer_for  # S13: outbox channel -> mailer, for the sender job
        self.scheduler = scheduler or BackgroundScheduler(timezone="UTC")
        # S13 B: shops are checked side by side by a small pool (tests may scale these times down)
        self.budgets, self.check_seconds = dict(SHOP_BUDGET), CHECK_WATCHDOG
        self.round_deadline, self.inbox_pass_seconds = dict(ROUND_DEADLINE), INBOX_PASS_SECONDS
        self.tick_wait = TICK_SECONDS * 0.8
        self.pool = ThreadPoolExecutor(max_workers=max(1, settings.monitor_workers), thread_name_prefix="monitor")
        self._round_lock, self._busy_lock = threading.Lock(), threading.Lock()
        self._busy: set[int] = set()  # shops being checked right now (never two checks of one shop at once)

    # ---------- scheduler wiring ----------

    def register(self) -> None:
        if self.mailer_for is not None:  # S13: the outbox's sender job (the same one process, its own short beat)
            self.scheduler.add_job(self.send_mail, "interval", seconds=OUTBOX_SECONDS, id="outbox_send",
                                   replace_existing=True, max_instances=1, coalesce=True)
        # S13 B: one beat a minute; each shop has a stable slot, so the shops are spread over the 15 minutes
        # (and the day) instead of all starting at once
        self.scheduler.add_job(self.tick, "interval", seconds=TICK_SECONDS, id="monitor_tick",
                               replace_existing=True, max_instances=1, coalesce=True)
        if self.team is not None:
            self.scheduler.add_job(self.watch_addresses, "interval", days=1, id="watch_addresses",
                                   replace_existing=True, max_instances=1, coalesce=True)
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
        self.pool.shutdown(wait=False, cancel_futures=True)

    def schedule_recheck(self, business_id: int, names: list[str]) -> None:
        self.scheduler.add_job(self.recheck, "date", run_date=utcnow() + timedelta(seconds=RECHECK_SECONDS),
                               args=[business_id, names], id=f"recheck-{business_id}", replace_existing=True)

    # ---------- jobs ----------

    def send_mail(self) -> dict:
        return outbox.run_once(self.engine, self.settings, self.mailer_for)

    def live_business_ids(self) -> list[int]:
        """Shops to watch: live, not paused. Guest practice shops are short-lived and aren't watched."""
        with Session(self.engine) as s:
            return list(s.exec(select(Business.id).where(Business.status == "live", Business.paused == False,  # noqa: E712
                                                         Business.guest_hash == "")).all())

    def run_quick(self) -> dict:
        return self._round("quick")

    def run_daily(self) -> dict:
        return self._round("daily")

    @staticmethod
    def slot(business_id: int, slots: int) -> int:
        """A stable per-shop offset (the same in every process and after restarts; Python's hash() isn't)."""
        return zlib.crc32(f"shop:{business_id}".encode()) % slots

    def last_runs(self, kind: str) -> dict[int, datetime]:
        with Session(self.engine) as s:
            rows = s.exec(select(CheckRun.business_id, CheckRun.started_at).where(
                CheckRun.trigger == f"monitor_{kind}")).all()
        last: dict[int, datetime] = {}
        for bid, at in rows:
            at = proof_aware(at)
            if bid not in last or at > last[bid]:
                last[bid] = at
        return last

    def due(self, now: datetime | None = None) -> dict[str, list[int]]:
        """Which shops this tick checks: those whose slot it is, plus any that missed theirs (overdue)."""
        now = now or utcnow()
        minute = now.hour * 60 + now.minute
        ids = self.live_business_ids()
        out: dict[str, list[int]] = {}
        for kind, slots, at in (("daily", DAILY_SLOTS, minute), ("quick", QUICK_MINUTES, minute % QUICK_MINUTES)):
            last = self.last_runs(kind)
            out[kind] = [b for b in ids if self.slot(b, slots) == at
                         or (b in last and now - last[b] > OVERDUE[kind])]
        out["quick"] = [b for b in out["quick"] if b not in out["daily"]]  # daily includes the quick checks
        return out

    def tick(self, now: datetime | None = None) -> dict:
        due = self.due(now)
        got = {}
        for kind in ("daily", "quick"):
            if due[kind]:  # a beat waits at most most of a minute: a slow shop never makes the next beat skip
                got[kind] = self._round(kind, due[kind], deadline=self.tick_wait)
        return got

    def _round(self, kind: str, ids: list[int] | None = None, deadline: float | None = None) -> dict:
        """Live shops side by side in a small pool. A shop whose check blows up is recorded as "couldn't finish"
        (never as passed); a shop still running at the deadline is recorded as unfinished and nobody waits for it.
        A second round never stacks on one still running, and a shop is never checked twice at once."""
        if not self._round_lock.acquire(blocking=False):
            with Session(self.engine) as s:
                audit.record(s, actor="monitor", action="monitor_round", target=kind, result="skipped",
                             detail="the previous round is still running")
            return {"skipped_round": True}
        try:
            futures, busy = {}, []
            for bid in (self.live_business_ids() if ids is None else ids):
                with self._busy_lock:
                    if bid in self._busy:
                        busy.append(bid)
                        continue
                    self._busy.add(bid)
                futures[self.pool.submit(self._shop, bid, kind)] = bid
            _done, late = wait(futures, timeout=deadline or self.round_deadline[kind])
            for f in late:
                bid = futures[f]
                with Session(self.engine) as s:
                    audit.record(s, actor="monitor", action="monitor_shop", target=f"business:{bid}", result="unfinished",
                                 business_id=bid, detail=f"{kind} check still running when the round ended")
            for bid in busy:
                with Session(self.engine) as s:
                    audit.record(s, actor="monitor", action="monitor_shop", target=f"business:{bid}", result="skipped",
                                 business_id=bid, detail=f"{kind}: the previous check of this shop is still running")
            return {"checked": len(futures) - len(late), "unfinished": sorted(futures[f] for f in late),
                    "busy": sorted(busy)}
        finally:
            self._round_lock.release()

    def _shop(self, bid: int, kind: str) -> None:
        try:
            self.check_business(bid, kind)
        except Exception as e:
            with Session(self.engine) as s:
                audit.record(s, actor="monitor", action="monitor_shop", target=f"business:{bid}", result="failed",
                             business_id=bid, detail=f"{kind} check couldn't finish: {type(e).__name__}")
        finally:
            with self._busy_lock:
                self._busy.discard(bid)

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
                                 trigger=f"monitor_{kind}", names=names, fix=False,
                                 budget_seconds=self.budgets[kind], check_seconds=self.check_seconds,
                                 inbox_wait=False)
        except (NotLaunched, AlreadyChecking):  # e.g. the owner just pressed "Run checks now": skip this round
            return []
        # "couldn't finish" / "our lookup failed" is not a failure of the shop: no re-check as one, no alert,
        # and it doesn't clear an open alert either (we simply don't know)
        failing = [f.check for f in summary.failed if not f.unfinished]
        if failing:
            self.schedule_recheck(business_id, failing)
        for item in summary.inbox:  # S13 B: "accepted" is recorded; look for "seen" in a short later pass
            self.schedule_inbox_pass(business_id, summary.run_id, item, 1)
        self.resolve(business_id, [n for n in names if n not in {f.check for f in summary.failed}])
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
                                 trigger="monitor_recheck", names=names, fix=True,
                                 budget_seconds=self.budgets["recheck"], check_seconds=self.check_seconds)
        except (NotLaunched, AlreadyChecking):
            return []
        still = [f for f in summary.failed if not f.unfinished]
        self.resolve(business_id, [n for n in names if n not in {f.check for f in summary.failed}])
        for f in still:
            self.check_alert(business_id, plan.site_host, f)
        return [f.check for f in still]

    # ---------- S13 B: the test order's later inbox look ----------

    def schedule_inbox_pass(self, business_id: int, run_id: int, item: dict, n: int) -> None:
        self.scheduler.add_job(self.inbox_pass, "date",
                               run_date=utcnow() + timedelta(seconds=self.inbox_pass_seconds),
                               args=[business_id, run_id, item, n], id=f"inbox-{business_id}-{item['nonce']}",
                               replace_existing=True)

    def inbox_pass(self, business_id: int, run_id: int, item: dict, n: int) -> str:
        """Look for the daily test order in the inbox we can read. Found: proof (`imap_seen`, through the chain)
        and the run's test-order row says so. Still missing after the last look: the row says so and the usual
        re-check (blocking look, Doctor, alert) takes over. Returns "seen" | "later" | "missing" | "gone"."""
        from app import proof
        from app.models import CheckResult

        found = self._context(business_id)
        if found is None:
            return "gone"
        b, _plan = found
        integ = self.integ_for(b)
        since = datetime.fromisoformat(item["since"])
        seen = integ.inbox.find(subject_contains=item["nonce"], since=since)
        if not seen and n < INBOX_PASSES:
            self.schedule_inbox_pass(business_id, run_id, item, n + 1)
            return "later"
        with Session(self.engine) as s:
            row = s.exec(select(CheckResult).where(CheckResult.run_id == run_id, CheckResult.check == "test_order")
                         .order_by(CheckResult.id.desc())).first()
            biz = s.get(Business, business_id)
            if seen:
                proof.add(s, business=biz, run_id=run_id, check="test_order", step="imap_seen",
                          practice=bool(integ.fake or biz.practice), nonce=item["nonce"],
                          server="pretend inbox" if integ.fake else self.settings.imap_host,
                          source=self.settings.imap_user)
                plain, ok = "A test order reached your inbox.", True
                detail = f"order {item['ref']} code {item['nonce']} found (look {n})"
            else:
                plain, ok = "A test order was sent but hasn't arrived in your inbox.", False
                detail = f"order {item['ref']} code {item['nonce']} not found after {n} looks"
            if row is not None:
                row.passed, row.detail = ok, json.dumps({"plain": plain, "detail": detail, "waiting": False})
                s.add(row)
                if not ok:
                    run = s.get(CheckRun, run_id)
                    if run is not None:
                        run.passed = False
                        s.add(run)
                s.commit()
            audit.record(s, actor="monitor", action="inbox_pass", target=f"run:{run_id}",
                         result="seen" if ok else "missing", business_id=business_id, detail=detail)
        if not ok:
            self.schedule_recheck(business_id, ["test_order"])
        return "seen" if ok else "missing"

    def check_alert(self, business_id: int, host: str, f) -> None:
        """One email per problem. A problem that keeps coming back (fail → fine → fail again within a day, or
        fixed by us too many times today) gets ONE "keeps breaking" email, then silence for the rest of the day."""
        since = utcnow() - FLAP_WINDOW
        with Session(self.engine) as s:
            rows = s.exec(select(Alert).where(Alert.business_id == business_id, Alert.key == f.check,
                                              Alert.kind.in_(("check_failed", "check_flapping")))).all()
            if any(a.kind == "check_failed" and a.resolved_at is None for a in rows):
                return  # already told, still open
            recent = [a for a in rows if proof_aware(a.created_at) >= since]
            came_back = any(a.kind == "check_failed" for a in recent)
            told_flapping = any(a.kind == "check_flapping" for a in recent)
            for a in rows:  # yesterday's "keeps breaking" no longer blocks a new one
                if a.kind == "check_flapping" and a.resolved_at is None and proof_aware(a.created_at) < since:
                    a.resolved_at = utcnow()
                    s.add(a)
            s.commit()
        if not (f.keeps_breaking or came_back):
            self.alert(business_id, "check_failed", f.check,
                       subject=f"Something needs attention on {host}",
                       body=(f"Hello,\n\nOur regular check of your website found a problem we couldn't fix by ourselves:\n\n"
                             f"  {f.plain}\n\nSign in to LaunchWitness and open your shop's report to see the details, and "
                             f"press \"Run checks now\" after any change.\n\n— LaunchWitness"))
            return
        note = "(already told today: keeps breaking)"
        if not told_flapping:
            why = ("We fixed it several times today and it broke again, so we've stopped fixing it automatically."
                   if f.keeps_breaking else "It was fine for a while and has now broken again.")
            if not self.alert(business_id, "check_flapping", f.check,
                              subject=f"Something keeps breaking on {host}",
                              body=(f"Hello,\n\nThis keeps breaking on your website:\n\n  {f.plain}\n\n{why} Something "
                                    "outside LaunchWitness is probably changing it back. Sign in to LaunchWitness and open "
                                    "your shop's report for the exact next step. We won't email you about this one again "
                                    "today.\n\n— LaunchWitness")):
                return  # couldn't send: nothing is marked, so the next round tries again
            note = "(in the keeps-breaking email)"
        with Session(self.engine) as s:  # keep the problem itself on record as open, without another email
            s.add(Alert(business_id=business_id, kind="check_failed", key=f.check, sent_to=note))
            s.commit()

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
            # S13: through the outbox. The key counts earlier alerts of this kind, so a problem that was
            # resolved and came back is a new email, while the same open problem is never emailed twice.
            # Not sent at once: the outbox keeps trying, and each monitoring round also tries it again.
            integ = self.integ_for(b)
            told = len(s.exec(select(Alert.id).where(Alert.business_id == business_id, Alert.kind == kind,
                                                      Alert.key == key)).all())
            row = outbox.send(s, self.settings, integ.mailer, kind="alert", retry_now=True,
                              key=f"alert:{business_id}:{kind}:{key}:{told}", to=to, subject=subject, body=body,
                              channel=outbox.channel_of(integ), business_id=business_id,
                              ref={"audit": {"actor": "monitor", "action": f"alert_{kind}", "target": key}})
            if row.status != "sent":
                return False
            s.add(Alert(business_id=business_id, kind=kind, key=key, sent_to=to))
            s.commit()
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


    def watch_addresses(self) -> int:
        """S10.5b: read-only daily checks of the addresses users asked us to watch; one email per new problem,
        sent from the team mailbox to the user's own sign-in address."""
        from app import watch
        from app.checks.safe_fetch import SafeWeb
        from app.routers.proof import get_public_dns

        return watch.run_daily(self.engine, self.team.mailer, get_public_dns(), SafeWeb(lambda _h: True, timeout=8.0),
                               channel=outbox.channel_of(self.team), settings=self.settings)

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
                if to and self.team is not None:  # S13: via the outbox; once sent, the next run marks it
                    row = outbox.send(s, self.settings, self.team.mailer, kind="team", retry_now=True,
                                      key=f"team:{kind}:{key}:{len(open_)}", to=to, subject=subject, body=body,
                                      channel=outbox.channel_of(self.team))
                    result = "sent" if row.status == "sent" else f"failed: {row.last_error or row.status}"
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
