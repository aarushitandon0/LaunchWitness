"""SQLite tables. Fields are minimal for M0 and will grow per milestone."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    """A seller (or the admin). Signs in with an email link; no passwords are stored anywhere."""

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)  # lowercase, trimmed; proven at first sign-in
    status: str = "pending"  # pending (practice only) | approved (real launches) | suspended | deleted
    role: str = "seller"  # seller | admin
    status_reason: str = ""  # shown to the user when rejected / suspended
    created_at: datetime = Field(default_factory=utcnow)
    last_login_at: datetime | None = None


class LoginToken(SQLModel, table=True):
    """A single-use emailed link (sign in, or confirm deleting the account). Only the SHA-256
    of the token is stored, so a copy of the database can't be used to sign in."""

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    email: str = Field(index=True)
    purpose: str = "login"  # login | delete_account
    visitor: str = Field(default="", index=True)  # hashed IP that asked (rate limit)
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "sessions"

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    user_agent: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    revoked: bool = False


class Membership(SQLModel, table=True):
    """Who may manage which shop. One owner per shop for now; the table allows teams later."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    role: str = "owner"
    created_at: datetime = Field(default_factory=utcnow)


class ShopReport(SQLModel, table=True):
    """A visitor's "Report this shop" message, for the team's queue."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    reason: str
    note: str = ""
    visitor: str = Field(default="", index=True)  # hashed IP (limit), never the IP itself
    status: str = "open"  # open | closed
    closed_note: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Business(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    owner_email: str = ""
    description: str = ""
    price_list_text: str = ""
    profile_json: str = "{}"  # Reader output (M2)
    # e.g. "meerascakes.in". Unique among real businesses / among practice ones (checked in code),
    # so a practice launch can never hold a real seller's domain.
    domain: str | None = Field(default=None, index=True)
    subdomain: str | None = Field(default=None, unique=True, index=True)  # label under APP_DOMAIN
    status: str = "draft"  # draft | planned | launching | live | failed
    # Practice businesses always run against the fake world (never real GoDaddy/DNS/email).
    # Only businesses created with the admin token on a real server are not practice.
    practice: bool = True
    # Guest practice: sha256 of the anonymous visitor cookie that made this shop. Cleared when the
    # visitor signs in (the shop then belongs to their account through a Membership row).
    guest_hash: str = Field(default="", index=True)
    paused_reason: str = ""
    # Go-live policy check: "" (not checked) | held (the team must look) | cleared (OK to launch)
    review: str = ""
    review_reason: str = ""
    visitor: str = ""  # hashed client IP that created it (daily limit)
    paused: bool = False  # team pause: the public shop shows a neutral "paused" page and takes no orders
    demo_fault: str = ""  # admin demo switch, consumed by the next check run: "" | "dmarc" | "mx"
    created_at: datetime = Field(default_factory=utcnow)


class Plan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    mode: str = "sandbox"  # sandbox | full
    practice: bool = True  # a practice plan ran in the pretend world; its results never count as real proof
    zone: str = ""  # the DNS zone this launch writes to (APP_DOMAIN or the seller's domain)
    site_host: str = ""  # e.g. meera.<APP_DOMAIN> or meerascakes.in
    mailbox: str = ""  # address orders are emailed to
    steps_json: str = "[]"  # [{id, kind, title, detail, status, message, started_at, finished_at}]
    dns_json: str = "[]"  # [{zone, type, name, before: [...], after: [...], say, deferred}]
    total_cost_usd: float = 0.0
    status: str = "draft"  # draft | approved | running | done | failed | blocked
    visitor: str = ""  # hashed client IP that approved it (daily launch limit)
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Approval(SQLModel, table=True):
    """The owner's explicit OK for one money-spending action."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="plan.id")
    action: str  # e.g. "buy_domain", "buy_mailbox"
    target: str  # e.g. the domain name
    amount_usd: float  # the exact cost the owner saw and approved
    approved_by: str
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class DnsBackup(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="plan.id", index=True)
    domain: str
    records_json: str
    created_at: datetime = Field(default_factory=utcnow)


class CheckRun(SQLModel, table=True):
    """One round of checks: after a launch, on "Run checks now", or by the monitor."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    plan_id: int = Field(foreign_key="plan.id", index=True)
    trigger: str  # launch | manual | monitor_quick | monitor_daily | monitor_recheck
    status: str = "running"  # running | done
    passed: bool | None = None
    repairs_json: str = "[]"  # Doctor attempts: [{check, fixed, attempts: [{explanation, fix_id, applied, message, passed}]}]
    info_json: str = "{}"  # e.g. {"cert_days_left": 80, "domain_days_left": 300}
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None


class CheckResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="plan.id", index=True)
    run_id: int | None = Field(default=None, foreign_key="checkrun.id", index=True)
    attempt: int = 0  # 0 = first check, 1..3 = re-check after a repair
    check: str  # e.g. "https", "dns_a", "mx", "test_order"
    passed: bool
    detail: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class AuditEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int | None = Field(default=None, foreign_key="business.id", index=True)
    actor: str  # "owner", "system", "executor", "doctor", ...
    user_id: int | None = Field(default=None, index=True)  # the signed-in user who did it, when there is one
    action: str
    target: str = ""
    result: str  # "ok" | "blocked" | "failed" | ...
    detail: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class Alert(SQLModel, table=True):
    """An email sent to the owner by monitoring. Used so each warning is sent once."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    kind: str  # check_failed | domain_expiry | cert_expiry
    key: str  # e.g. the check name, or "<expiry date>:<days threshold>"
    sent_to: str = ""
    resolved_at: datetime | None = None  # check_failed: set when the check passes again
    created_at: datetime = Field(default_factory=utcnow)


class Order(SQLModel, table=True):
    """An order a customer placed through a seller's site form (no payment taken)."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    customer_name: str
    customer_phone: str
    items_json: str = "[]"  # [{"name", "qty", "price_inr"}]
    total_inr: int = 0
    note: str = ""
    ref: str = Field(default="", index=True)  # public order reference, e.g. LW-4F2K7Q9M (random, not a count)
    is_test: bool = False  # placed by the launch check, not a customer
    nonce: str = ""  # test orders: random code in the email subject + body, so an old email can never pass
    visitor: str = Field(default="", index=True)  # hashed client IP (order rate limit); never the IP itself
    client_token: str = Field(default="", index=True)  # hidden form field: a double submit makes one order
    email_status: str = "pending"  # pending | sent | failed
    email_message_id: str = ""
    # S10.5: the owner's own progress on the order (sites/orders.py STATUS_STEPS). Only the owner sets it.
    status: str = Field(default="new", index=True)  # new | confirmed | paid | done | cancelled
    status_changed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ClaudeUsage(SQLModel, table=True):
    """One live Claude call: tokens and cost, used to enforce the daily spend cap."""

    id: int | None = Field(default=None, primary_key=True)
    day: str = Field(index=True)  # UTC date, YYYY-MM-DD
    purpose: str  # e.g. "reader_meera_cakes"
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    created_at: datetime = Field(default_factory=utcnow)


class Evidence(SQLModel, table=True):
    """One proven hop of a check, stored as it happened (S9F Phase 3). The report only claims what is here."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    run_id: int | None = Field(default=None, index=True)  # the CheckRun
    check: str  # site_points | https | test_order | email_* ...
    step: str  # dns_answer | http_response | form_post | smtp_accepted | imap_seen | owner_confirmed
    at: datetime = Field(default_factory=utcnow)
    source: str = ""  # which server or tool gave the answer, e.g. "ns1.domaincontrol.com", "imap.secureserver.net"
    server: str = ""  # the server asked (nameserver IP, mail server host)
    message_id: str = ""
    nonce: str = ""
    status_code: int | None = None
    cert_not_after: datetime | None = None
    answer: str = ""  # DNS answer or a short excerpt
    practice: bool = False  # from the pretend world: always labelled


class TestTicket(SQLModel, table=True):
    """A test order the checker is about to place. The form POST carries `lw_test=<nonce>`; only an open
    ticket for that shop turns the POST into a hidden test order. The test email's "Yes, I got it" link
    carries a second random token; only its SHA-256 is stored, and it works once."""

    __test__ = False  # not a pytest test class

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    run_id: int | None = Field(default=None, index=True)
    nonce: str = Field(index=True, unique=True)
    confirm_hash: str = Field(default="", index=True)
    order_id: int | None = None
    used_at: datetime | None = None  # the form POST used it
    confirmed_at: datetime | None = None  # the owner tapped "Yes, I got it"
    created_at: datetime = Field(default_factory=utcnow)


class ReportShare(SQLModel, table=True):
    """A read-only shared report at /r/<token>. Only the token's SHA-256 is stored; the owner can revoke it."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    revoked_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class AddressCheck(SQLModel, table=True):
    """Rate limit for the public "Check any address" tool: hashed visitor + time only, never the address."""

    id: int | None = Field(default=None, primary_key=True)
    visitor: str = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)


class TeamAlert(SQLModel, table=True):
    """An email to the team (ADMIN_EMAIL) about something no seller can fix: the app domain or the team
    mailbox running out. Sent once per (kind, threshold) until it's renewed (S10)."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str = Field(index=True)  # app_domain_expiry | mailbox_expiry
    key: str  # threshold, e.g. "30d"
    sent_to: str = ""
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ZoneFinding(SQLModel, table=True):
    """Zone hygiene (S10): an A record on the app's own domain that doesn't match the shops in the database,
    with the fix we propose. Nothing is changed until the admin approves it on the team page."""

    id: int | None = Field(default=None, primary_key=True)
    business_id: int | None = Field(default=None, index=True)  # the shop involved, if any (no FK: may be deleted)
    kind: str  # dangling | missing | wrong_target
    name: str  # the record name (a shop label), never @ / www
    found: str = ""  # what the zone has now ("" = no record)
    want: str = ""  # what it should be ("" = no record)
    fix: str  # delete | set
    plain: str = ""
    status: str = Field(default="open", index=True)  # open | fixed | dismissed | gone (fixed itself)
    decided_by: str = ""
    result: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None
