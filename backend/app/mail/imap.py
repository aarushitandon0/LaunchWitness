"""Read the demo inbox (IMAP over SSL) to prove a test order arrived."""

import email
import imaplib
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from typing import Protocol

from app.config import Settings


@dataclass
class InboxMessage:
    sender: str
    to: str
    subject: str
    body: str
    at: datetime | None = None  # when the mail server received it


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def received_at(fetch_head: bytes, msg) -> datetime | None:
    """When the server received the message (INTERNALDATE), else the Date header."""
    t = imaplib.Internaldate2tuple(fetch_head)
    if t is not None:
        return datetime.fromtimestamp(time.mktime(t), UTC)
    try:
        return _aware(parsedate_to_datetime(str(msg.get("Date", ""))))
    except (TypeError, ValueError):
        return None


class InboxReader(Protocol):
    def find(self, *, subject_contains: str, since: datetime | None = None) -> list[InboxMessage]:
        """Messages whose subject contains the text and that arrived at or after `since`."""
        ...


class ImapInboxReader:
    def __init__(self, settings: Settings):
        self.host = settings.imap_host
        self.port = settings.imap_port
        self.user = settings.imap_user
        self._password = settings.imap_password

    def find(self, *, subject_contains: str, since: datetime | None = None) -> list[InboxMessage]:
        out: list[InboxMessage] = []
        criteria = ["SUBJECT", f'"{subject_contains}"']
        if since is not None:  # IMAP SINCE only knows whole days; the exact time is checked below
            day = _aware(since).astimezone(UTC) - timedelta(days=1)
            criteria += ["SINCE", f"{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}"]
        with imaplib.IMAP4_SSL(self.host, self.port, timeout=30) as conn:
            conn.login(self.user, self._password.get_secret_value())
            conn.select("INBOX", readonly=True)
            _, data = conn.search(None, *criteria)
            for num in data[0].split():
                _, parts = conn.fetch(num, "(INTERNALDATE RFC822)")
                msg = email.message_from_bytes(parts[0][1])
                at = received_at(parts[0][0], msg)
                if since is not None and (at is None or at < _aware(since)):
                    continue  # an old email must never pass
                body_part = msg.get_body(preferencelist=("plain",)) if hasattr(msg, "get_body") else None
                payload = body_part.get_payload(decode=True) if body_part else msg.get_payload(decode=True)
                out.append(
                    InboxMessage(
                        sender=str(msg.get("From", "")),
                        to=str(msg.get("To", "")),
                        subject=str(make_header(decode_header(msg.get("Subject", "")))),
                        body=(payload or b"").decode("utf-8", errors="replace"),
                        at=at,
                    )
                )
        return out


class FakeInboxReader:
    """Holds messages in memory; `deliver()` simulates mail arriving."""

    def __init__(self, messages: list[InboxMessage] | None = None):
        self.messages = list(messages or [])

    def deliver(self, *, sender: str, to: str, subject: str, body: str, at: datetime | None = None) -> None:
        self.messages.append(InboxMessage(sender=sender, to=to, subject=subject, body=body,
                                          at=at or datetime.now(UTC)))

    def find(self, *, subject_contains: str, since: datetime | None = None) -> list[InboxMessage]:
        return [m for m in self.messages if subject_contains in m.subject
                and (since is None or (m.at is not None and _aware(m.at) >= _aware(since)))]
