"""Send mail through the app's one mailbox (GoDaddy Professional Email, secureserver.net).

Port 465 = implicit SSL (default). Port 587 = STARTTLS. If an SSL connection to 465 can't be
made at all (blocked port, timeout, TLS handshake error), we try 587 STARTTLS once. We never
fall back after login has started, so a message can't be sent twice and a wrong password
isn't retried. Host, port, user and password come only from settings (env vars).
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.config import Settings

log = logging.getLogger(__name__)

STARTTLS_PORT = 587
TIMEOUT_S = 30


class Mailer(Protocol):
    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> str: ...


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self._password = settings.smtp_password
        self.security = settings.smtp_security

    def _connect(self) -> smtplib.SMTP:
        if self.security == "plain":  # local catch-all only (config refuses it for real host names)
            return smtplib.SMTP(self.host, self.port, timeout=TIMEOUT_S)
        context = ssl.create_default_context()
        if self.port != STARTTLS_PORT and self.security == "ssl":
            try:
                return smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=TIMEOUT_S)
            except (ConnectionError, TimeoutError, ssl.SSLError, smtplib.SMTPConnectError,
                    smtplib.SMTPServerDisconnected) as e:
                log.warning("SMTP SSL to %s:%s failed (%s); trying port %s with STARTTLS",
                            self.host, self.port, type(e).__name__, STARTTLS_PORT)
        s = smtplib.SMTP(self.host, STARTTLS_PORT if self.security == "ssl" else self.port, timeout=TIMEOUT_S)
        try:
            s.starttls(context=context)
        except Exception:
            s.close()
            raise
        return s

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> str:
        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.user.split("@")[-1])
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        with self._connect() as s:
            if self.security != "plain" or self._password.get_secret_value():
                s.login(self.user, self._password.get_secret_value())
            s.send_message(msg)
        return msg["Message-ID"]


class FakeMailer:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, *, to: str, subject: str, body: str, html: str | None = None) -> str:
        message_id = f"<fake-{len(self.sent) + 1}@launchwitness.test>"
        self.sent.append({"to": to, "subject": subject, "body": body, "html": html, "message_id": message_id})
        return message_id


def get_mailer() -> Mailer:
    """FastAPI dependency. Tests override this with a FakeMailer."""
    from app.config import get_settings

    return SmtpMailer(get_settings())
