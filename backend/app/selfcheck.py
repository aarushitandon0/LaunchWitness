"""Startup self-check: settings that are wrong for a real server, in plain words. Never includes a secret.

Logged at startup. `/api/health` shows the PUBLIC ones to anyone (nothing an attacker could use) and all of
them to the admin (signed-in admin or X-Admin-Token). `scripts/check_m1.sh` prints them too.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date

from app.config import Settings

MAILBOX_WARN_DAYS = 14


@dataclass(frozen=True)
class Warning_:
    code: str
    text: str
    public: bool = False  # safe to show on the public health page


def real_server(settings: Settings) -> bool:
    return not settings.use_fakes


def fixture_on_real_server(settings: Settings) -> bool:
    """Saved Claude answers on a server that launches real shops: the policy check would always say OK."""
    return settings.claude_mode == "fixture" and real_server(settings)


def mailbox_warning(settings: Settings, today: date | None = None) -> str | None:
    """The app's mailbox carries sign-in links, orders and alerts: warn before it lapses."""
    end = settings.mailbox_expires_on
    if end is None:
        return None
    days = (end - (today or date.today())).days
    if days > MAILBOX_WARN_DAYS:
        return None
    return (f"The app's mailbox ({settings.smtp_user}) " + (f"lapses in {days} day(s)" if days >= 0 else "has lapsed")
            + ": sign-in links, orders and alerts all depend on it. Renew it.")


def database_writable(settings: Settings) -> bool:
    url = settings.database_url
    if not url.startswith("sqlite:///") or url.endswith(":memory:"):
        return True
    path = url.removeprefix("sqlite:///")
    folder = os.path.dirname(os.path.abspath(path))
    if not os.access(folder, os.W_OK) or (os.path.exists(path) and not os.access(path, os.W_OK)):
        return False
    try:
        con = sqlite3.connect(path, timeout=5)
        try:
            con.execute("BEGIN IMMEDIATE")  # takes the write lock for a moment, writes nothing
            con.execute("ROLLBACK")
        finally:
            con.close()
        return True
    except sqlite3.Error:
        return False


def warnings(settings: Settings, today: date | None = None) -> list[Warning_]:
    from app.safety.access import admin_token_enabled

    out: list[Warning_] = []
    add = lambda code, text, public=False: out.append(Warning_(code, text, public))  # noqa: E731
    if not settings.admin_email.strip():
        add("admin_email_unset", "ADMIN_EMAIL is not set: nobody can open the team page.")
    if not admin_token_enabled(settings):
        add("admin_token_weak", "ADMIN_TOKEN is the default or shorter than 16 characters, so command-line admin is off.")
    if settings.dev_mode:
        add("dev_mode_on", "DEV_MODE is on: sign-in links are shown on screen. Local development only.")
    if fixture_on_real_server(settings):
        add("claude_fixture_on_real_server", "CLAUDE_MODE=fixture on a real server: every real launch is held "
            "for the team to review (the saved policy answer would always say OK).")
    if not settings.dev_mode and settings.smtp_security != "plain" and not settings.smtp_password.get_secret_value():
        add("smtp_not_configured", "Email isn't set up (no SMTP password): sign-in links and orders can't be sent.", True)
    mail = mailbox_warning(settings, today)
    if mail:
        add("mailbox_expiring", mail, True)
    if not database_writable(settings):
        add("database_not_writable", "The database can't be written: nothing can be saved.", True)
    if real_server(settings) and settings.server_ip.strip() in ("", "127.0.0.1", "0.0.0.0"):
        add("server_ip_missing", "SERVER_IP isn't this server's public address: shop records would point nowhere.")
    if settings.allow_purchase:
        add("purchases_on", f"ALLOW_PURCHASE is on (cap ${settings.max_spend_usd:.0f}). It should stay off: "
            "purchases are made by hand on godaddy.com.")
    return out
