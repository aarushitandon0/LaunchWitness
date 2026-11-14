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
    domain: str | None = Field(default=None, unique=True, index=True)  # e.g. "meerascakes.in"
    subdomain: str | None = Field(default=None, unique=True, index=True)  # label under APP_DOMAIN
    status: str = "draft"  # draft | planned | launching | live | failed
    created_at: datetime = Field(default_factory=utcnow)


class Plan(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
    steps_json: str = "[]"
    total_cost_usd: float = 0.0
    status: str = "draft"  # draft | approved | running | done | failed
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
    domain: str
    records_json: str
    created_at: datetime = Field(default_factory=utcnow)


class CheckResult(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    business_id: int = Field(foreign_key="business.id", index=True)
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
