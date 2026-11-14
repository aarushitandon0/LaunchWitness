"""Send mail through the app's one Titan mailbox (SMTP over SSL)."""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.config import Settings


class Mailer(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> str: ...


class SmtpMailer:
    def __init__(self, settings: Settings):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self._password = settings.smtp_password

    def send(self, *, to: str, subject: str, body: str) -> str:
        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain=self.user.split("@")[-1])
        msg.set_content(body)
        with smtplib.SMTP_SSL(self.host, self.port, context=ssl.create_default_context(), timeout=30) as s:
            s.login(self.user, self._password.get_secret_value())
            s.send_message(msg)
        return msg["Message-ID"]


class FakeMailer:
    def __init__(self):
        self.sent: list[dict] = []

    def send(self, *, to: str, subject: str, body: str) -> str:
        message_id = f"<fake-{len(self.sent) + 1}@launchwitness.test>"
        self.sent.append({"to": to, "subject": subject, "body": body, "message_id": message_id})
        return message_id
