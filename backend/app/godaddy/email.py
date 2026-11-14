"""Business mailbox (Titan via GoDaddy), behind one interface.

Step rules (SPEC §9): create or adopt, poll until ready, retry on failure, never undo.
The real provider is a stub to fill in (see PROGRESS.md: Real integration TODO).
"""

import hashlib
from dataclasses import dataclass
from typing import Protocol

# Titan mail records. TODO(real): confirm exact values for GoDaddy-sold Titan.
TITAN_MX = [(10, "mx1.titan.email"), (20, "mx2.titan.email")]
TITAN_SPF = "v=spf1 include:spf.titan.email ~all"


@dataclass(frozen=True)
class Mailbox:
    address: str
    status: str  # "pending" | "ready"


class MailboxProvider(Protocol):
    def find(self, address: str) -> Mailbox | None: ...
    def create(self, address: str) -> Mailbox: ...
    def status(self, address: str) -> str: ...
    def dkim(self, domain: str) -> tuple[str, str]:
        """(record name, TXT value), available once the mailbox domain is set up."""
        ...


class FakeMailboxProvider:
    def __init__(self, ready_after_polls: int = 1, fail_creates: int = 0, existing: set[str] | None = None):
        self.ready_after_polls = ready_after_polls
        self.fail_creates = fail_creates
        self.boxes: dict[str, int] = {a: 10**6 for a in (existing or ())}  # address -> polls seen
        self.calls: list[tuple] = []

    def find(self, address: str) -> Mailbox | None:
        self.calls.append(("find", address))
        return Mailbox(address, self.status(address)) if address in self.boxes else None

    def create(self, address: str) -> Mailbox:
        self.calls.append(("create", address))
        if self.fail_creates > 0:
            self.fail_creates -= 1
            raise RuntimeError("fake mailbox service busy")
        self.boxes.setdefault(address, 0)
        return Mailbox(address, "pending")

    def status(self, address: str) -> str:
        if address not in self.boxes:
            return "missing"
        self.boxes[address] += 1
        return "ready" if self.boxes[address] > self.ready_after_polls else "pending"

    def dkim(self, domain: str) -> tuple[str, str]:
        return "titan1._domainkey", f"v=DKIM1; k=rsa; p=FAKE{hashlib.sha256(domain.encode()).hexdigest()[:24]}"


class TitanMailboxProvider:
    """TODO(real): GoDaddy Email/Titan API or `gddy` CLI: find, create, poll status, read DKIM."""

    def find(self, address: str) -> Mailbox | None:
        raise NotImplementedError("Real mailbox provider not implemented yet")

    def create(self, address: str) -> Mailbox:
        raise NotImplementedError("Real mailbox provider not implemented yet")

    def status(self, address: str) -> str:
        raise NotImplementedError("Real mailbox provider not implemented yet")

    def dkim(self, domain: str) -> tuple[str, str]:
        raise NotImplementedError("Real mailbox provider not implemented yet")
