"""App settings, read from environment variables / `.env`.

Every field here must also appear in `.env.example` (a test checks this).
Defaults are the safe ones: sandbox GoDaddy, fixture Claude, purchases off.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
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
    admin_token: SecretStr = SecretStr("change-me")
    # Public IP of the VPS; seller sites' A records point here.
    server_ip: str = "127.0.0.1"
    # true = GoDaddy, availability, mailbox, DNS checks and HTTP probes are in-memory
    # fakes (practice mode, nothing real changes). Set false on the VPS once the
    # real integrations are filled in (see PROGRESS.md "Real integration TODO").
    use_fakes: bool = True
    # Live-link guards (per visitor = per client IP, per UTC day; admin is exempt).
    visitor_describes_per_day: int = 5
    visitor_launches_per_day: int = 3
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
    email_plan_estimate_usd: float = 24.0

    # --- Mail ---
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
