"""App settings, read from environment variables / `.env`.

Every field here must also appear in `.env.example` (a test checks this).
Defaults are the safe ones: sandbox GoDaddy, fixture Claude, purchases off.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_domain: str = "localhost"
    app_base_url: str = "http://localhost"
    # The app's own origin (scheme://host[:port]) for CSRF checks. Empty = taken from APP_BASE_URL.
    app_origin: str = ""
    # Emergency / command-line admin only (X-Admin-Token header). People sign in as admin with ADMIN_EMAIL.
    admin_token: SecretStr = SecretStr("change-me")
    # This address is the admin: created at startup, approved, role admin. Signs in by email link like everyone.
    admin_email: str = ""
    # LOCAL DEVELOPMENT ONLY. Uses plain-http cookie names/flags and shows the sign-in link on screen
    # instead of emailing it. The app refuses to start with this on an https APP_BASE_URL.
    dev_mode: bool = False
    # Accounts and limits
    session_days: int = 14
    signin_links_per_email_per_day: int = 5
    signin_links_per_ip_per_hour: int = 10
    max_shops_per_user: int = 3
    user_describes_per_day: int = 5  # each "describe" is one Claude call: this is the per-user daily Claude cap
    # Every live shop needs its own HTTPS certificate, and the certificate authority allows about
    # 50 new ones a week per domain. This cap (and admin approval) keeps us under it.
    max_live_shops: int = 40
    shop_reports_per_visitor_per_day: int = 3
    # Public IP of the VPS; seller sites' A records point here.
    server_ip: str = "127.0.0.1"
    # true = GoDaddy, availability, mailbox, DNS checks and HTTP probes are in-memory
    # fakes (practice mode, nothing real changes). Set false on the VPS once the
    # real integrations are filled in (see PROGRESS.md "Real integration TODO").
    use_fakes: bool = True
    # Live-link guards (per visitor = per client IP, per UTC day; admin is exempt).
    visitor_describes_per_day: int = 5
    visitor_launches_per_day: int = 3
    visitor_contacts_per_day: int = 5
    # Order form limits on every public shop (test orders from the checker don't count).
    orders_per_visitor_per_hour: int = 5
    orders_per_shop_per_day: int = 200
    # Light monitoring (APScheduler). Off in tests; the scheduler only starts with the app.
    monitor_enabled: bool = True

    # --- Claude ---
    anthropic_api_key: SecretStr = SecretStr("")
    claude_mode: Literal["fixture", "live"] = "fixture"
    claude_model_strong: str = "claude-sonnet-5-5"
    claude_model_cheap: str = "claude-haiku-5-5"
    claude_max_tokens: int = 1500
    claude_daily_spend_cap_usd: float = 3.0

    # --- GoDaddy ---
    godaddy_env: Literal["ote", "prod"] = "ote"
    godaddy_api_key: SecretStr = SecretStr("")
    godaddy_api_secret: SecretStr = SecretStr("")
    godaddy_ote_api_key: SecretStr = SecretStr("")
    godaddy_ote_api_secret: SecretStr = SecretStr("")

    # --- Spend guards ---
    allow_purchase: bool = False
    max_spend_usd: float = 15.0
    # Shown on the approval card only ("Email plan, bought separately on GoDaddy").
    # PLACEHOLDER: check against the real GoDaddy cart. Not covered by the spend guard.
    email_plan_estimate_usd: float = 23.88  # GoDaddy Professional Email Pro Light, 1-yr term ($1.99/mo); monthly term is $5.99/mo

    # --- Mail ---
    # Which email service the mailbox is on: decides the mail settings we expect to see (app/mail/providers.py).
    mail_provider: Literal["secureserver", "titan"] = "secureserver"
    smtp_host: str = "smtpout.secureserver.net"
    smtp_port: int = 465
    smtp_user: str = "hello@example.com"
    smtp_password: SecretStr = SecretStr("")
    imap_host: str = "imap.secureserver.net"
    imap_port: int = 993
    imap_user: str = "hello@example.com"
    imap_password: SecretStr = SecretStr("")

    # --- Database ---
    database_url: str = "sqlite:///./data/launchwitness.db"


    @model_validator(mode="after")
    def _dev_mode_never_in_production(self):
        if self.dev_mode and self.app_base_url.lower().startswith("https://"):
            raise ValueError("DEV_MODE=true is for local http development only; remove it on an https server.")
        return self

    @property
    def origin(self) -> str:
        """scheme://host[:port] of the app, used to check Origin / Referer on state-changing requests."""
        from urllib.parse import urlsplit

        u = urlsplit(self.app_origin or self.app_base_url)
        return f"{u.scheme}://{u.netloc}".lower()

    @property
    def session_cookie(self) -> str:
        return "lw_session" if self.dev_mode else "__Host-lw_session"

    @property
    def guest_cookie(self) -> str:
        return "lw_guest" if self.dev_mode else "__Host-lw_guest"


@lru_cache
def get_settings() -> Settings:
    return Settings()
