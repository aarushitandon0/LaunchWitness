"""Read the demo inbox (IMAP over SSL) to prove a test order arrived."""

import email
import email.policy
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
        """Search, AND (S17) read the subjects of the newest RECENT_SCAN messages: the mail server's search index
        can lag behind new mail by tens of seconds, so either way of finding it counts."""
        out: list[InboxMessage] = []
        criteria = ["SUBJECT", f'"{subject_contains}"']
        if since is not None:  # IMAP SINCE only knows whole days; the exact time is checked below
            day = _aware(since).astimezone(UTC) - timedelta(days=1)
            criteria += ["SINCE", f"{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}"]
        with imaplib.IMAP4_SSL(self.host, self.port, timeout=30) as conn:
            conn.login(self.user, self._password.get_secret_value())
            _, count = conn.select("INBOX", readonly=True)  # read-only: nothing is marked as read
            _, data = conn.search(None, *criteria)
            nums = list(dict.fromkeys(data[0].split() + recent_matches(conn, count, subject_contains)))
            for num in nums:
                _, parts = conn.fetch(num, "(INTERNALDATE RFC822)")
                msg = email.message_from_bytes(parts[0][1], policy=email.policy.default)  # S17: get_body() for multipart mail
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


RECENT_SCAN = 20  # newest messages whose subjects are read directly on every look


def recent_matches(conn, count, text: str) -> list[bytes]:
    """Sequence numbers among the newest RECENT_SCAN messages whose (unfolded, decoded) subject contains `text`."""
    try:
        total = int((count or [b"0"])[0] or 0)
    except (TypeError, ValueError):
        return []
    if total <= 0:
        return []
    first = max(1, total - RECENT_SCAN + 1)
    _, parts = conn.fetch(f"{first}:{total}".encode(), "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
    found = []
    for part in parts or []:
        if not isinstance(part, tuple) or len(part) < 2:
            continue
        subject = str(email.message_from_bytes(part[1], policy=email.policy.default).get("Subject", ""))
        if text in subject:
            found.append(part[0].split()[0])
    return found


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
