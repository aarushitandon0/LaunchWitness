"""Read the demo inbox (IMAP over SSL) to prove a test order arrived."""

import email
import imaplib
from dataclasses import dataclass
from email.header import decode_header, make_header
from typing import Protocol

from app.config import Settings


@dataclass
class InboxMessage:
    sender: str
    to: str
    subject: str
    body: str


class InboxReader(Protocol):
    def find(self, *, subject_contains: str) -> list[InboxMessage]: ...


class ImapInboxReader:
    def __init__(self, settings: Settings):
        self.host = settings.imap_host
        self.port = settings.imap_port
        self.user = settings.imap_user
        self._password = settings.imap_password

    def find(self, *, subject_contains: str) -> list[InboxMessage]:
        out: list[InboxMessage] = []
        with imaplib.IMAP4_SSL(self.host, self.port, timeout=30) as conn:
            conn.login(self.user, self._password.get_secret_value())
            conn.select("INBOX", readonly=True)
            _, data = conn.search(None, "SUBJECT", f'"{subject_contains}"')
            for num in data[0].split():
                _, parts = conn.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(parts[0][1])
                body_part = msg.get_body(preferencelist=("plain",)) if hasattr(msg, "get_body") else None
                payload = body_part.get_payload(decode=True) if body_part else msg.get_payload(decode=True)
                out.append(
                    InboxMessage(
                        sender=str(msg.get("From", "")),
                        to=str(msg.get("To", "")),
                        subject=str(make_header(decode_header(msg.get("Subject", "")))),
                        body=(payload or b"").decode("utf-8", errors="replace"),
                    )
                )
        return out


class FakeInboxReader:
    """Holds messages in memory; `deliver()` simulates mail arriving."""

    def __init__(self, messages: list[InboxMessage] | None = None):
        self.messages = list(messages or [])

    def deliver(self, *, sender: str, to: str, subject: str, body: str) -> None:
        self.messages.append(InboxMessage(sender=sender, to=to, subject=subject, body=body))

    def find(self, *, subject_contains: str) -> list[InboxMessage]:
        return [m for m in self.messages if subject_contains in m.subject]
