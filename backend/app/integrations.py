"""All outside services the launch engine uses, bundled so they can be swapped.

USE_FAKES=true (default): one shared in-memory "fake world" per process
(GoDaddy zones, availability, mailbox, authoritative DNS answering from the
fake zones, HTTP probe). Nothing real changes. USE_FAKES=false: real clients;
the parts not built yet raise NotImplementedError (see PROGRESS.md).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from app.checks.dns_resolver import DnsResolver, ZoneBackedResolver
from app.checks.http_probe import FakeHttpProbe, HttpProbe, RealHttpProbe
from app.config import Settings, get_settings
from app.godaddy.availability import AvailabilityChecker, FakeAvailabilityChecker, GoDaddyAvailabilityChecker
from app.godaddy.client import FakeGoDaddyClient, GoDaddy, GoDaddyClient
from app.godaddy.email import FakeMailboxProvider, MailboxProvider, TitanMailboxProvider
from app.mail.imap import FakeInboxReader, ImapInboxReader, InboxReader
from app.mail.smtp import FakeMailer, Mailer, SmtpMailer


class DeliveringFakeMailer(FakeMailer):
    """Practice mode: 'sent' mail lands in the fake inbox, like a working mailbox would."""

    def __init__(self, inbox: FakeInboxReader, sender: str):
        super().__init__()
        self.inbox, self.sender, self.drop = inbox, sender, False

    def send(self, *, to: str, subject: str, body: str) -> str:
        message_id = super().send(to=to, subject=subject, body=body)
        if not self.drop:
            self.inbox.deliver(sender=self.sender, to=to, subject=subject, body=body)
        return message_id


@dataclass
class Integrations:
    godaddy: GoDaddy
    availability: AvailabilityChecker
    mailbox: MailboxProvider
    dns: DnsResolver  # must ask GoDaddy's AUTHORITATIVE nameservers, not a cache
    http: HttpProbe
    mailer: Mailer  # used by the launch check's test order
    inbox: InboxReader  # demo mailbox, to prove the test order arrived
    sleep: Callable[[float], None] = field(default=time.sleep)
    fake: bool = False


def fake_integrations(settings: Settings, sleep: Callable[[float], None] | None = None) -> Integrations:
    gd = FakeGoDaddyClient(owned={settings.app_domain})
    inbox = FakeInboxReader()
    return Integrations(
        godaddy=gd,
        availability=FakeAvailabilityChecker(),
        mailbox=FakeMailboxProvider(existing={settings.smtp_user}),
        dns=ZoneBackedResolver(gd),
        http=FakeHttpProbe(settings),
        mailer=DeliveringFakeMailer(inbox, settings.smtp_user),
        inbox=inbox,
        sleep=sleep or (lambda _s: None),
        fake=True,
    )


def real_integrations(settings: Settings) -> Integrations:
    from app.checks.dns_resolver import RealDnsResolver

    return Integrations(
        godaddy=GoDaddyClient(settings),
        availability=GoDaddyAvailabilityChecker(),
        mailbox=TitanMailboxProvider(),
        # TODO(real): pass GoDaddy's authoritative nameserver IPs (ns*.domaincontrol.com) for the zone.
        dns=RealDnsResolver(),
        http=RealHttpProbe(),
        mailer=SmtpMailer(settings),
        inbox=ImapInboxReader(settings),
    )


@lru_cache
def _shared_fakes() -> Integrations:
    return fake_integrations(get_settings())


def get_integrations() -> Integrations:
    """FastAPI dependency. Tests override this."""
    settings = get_settings()
    return _shared_fakes() if settings.use_fakes else real_integrations(settings)
