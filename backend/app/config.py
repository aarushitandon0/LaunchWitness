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
