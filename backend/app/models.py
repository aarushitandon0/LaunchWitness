"""SQLite tables. Fields are minimal for M0 and will grow per milestone."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


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
    owner_key_hash: str = ""  # sha256 of the secret owner link token (the token itself is never stored)
    visitor: str = ""  # hashed client IP that created it (daily limit)
    paused: bool = False  # team pause: the public shop shows a neutral "paused" page and takes no orders
    demo_fault: str = ""  # admin demo switch, consumed by the next check run: "" | "dmarc" | "mx"
    created_at: datetime = Field(default_factory=utcnow)


class Plan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    mode: str = "sandbox"  # sandbox | full
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
    is_test: bool = False  # placed by the launch check, not a customer
    nonce: str = ""  # test orders: random code in the email subject + body, so an old email can never pass
    visitor: str = Field(default="", index=True)  # hashed client IP (order rate limit); never the IP itself
    client_token: str = Field(default="", index=True)  # hidden form field: a double submit makes one order
    email_status: str = "pending"  # pending | sent | failed
    email_message_id: str = ""
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
