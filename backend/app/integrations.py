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

from app.checks.dns_resolver import PUBLIC_RESOLVERS, DnsResolver, ZoneBackedResolver
from app.checks.http_probe import FakeHttpProbe, HttpProbe, RealHttpProbe
from app.config import Settings, get_settings
from app.godaddy.availability import AvailabilityChecker, FakeAvailabilityChecker, GoDaddyAvailabilityChecker
from app.godaddy.client import FakeGoDaddyClient, GoDaddy, GoDaddyClient
from app.godaddy.email import FakeMailboxProvider, MailboxProvider, TitanMailboxProvider
from app.mail.imap import FakeInboxReader, ImapInboxReader, InboxReader
from app.mail.providers import planned_dkim_name, provider_for
from app.mail.smtp import FakeMailer, Mailer, SmtpMailer


class DeliveringFakeMailer(FakeMailer):
    """Practice mode: 'sent' mail lands in the fake inbox, like a working mailbox would."""

    def __init__(self, inbox: FakeInboxReader, sender: str):
        super().__init__()
        self.inbox, self.sender, self.drop = inbox, sender, False

    def send(self, *, to: str, subject: str, body: str, html: str | None = None, message_id: str | None = None,
             timeout: float | None = None) -> str:
        message_id = super().send(to=to, subject=subject, body=body, html=html)
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
    shop_web: Callable | None = None  # tests: how the checker reaches the shop (default: see checker.shop_web)
    # S13b: the public resolvers the daily run also asks (8.8.8.8, 1.1.1.1, 9.9.9.9): [(label, resolver)].
    # Information only: what customers' phones are likely to see. None = skip the look.
    public_dns: Callable[[], list[tuple[str, DnsResolver]]] | None = None


def fake_integrations(settings: Settings, sleep: Callable[[float], None] | None = None) -> Integrations:
    gd = FakeGoDaddyClient(owned={settings.app_domain}, app_domain=settings.app_domain)
    provider = provider_for(settings)
    # The pretend world starts like the real one: the domain the app's mailbox is on already has
    # working mail settings (GoDaddy set them when the mailbox was bought). Checks only read them.
    mail_zone = settings.smtp_user.rsplit("@", 1)[-1].lower()
    gd.zones.setdefault(mail_zone, []).extend(
        [{"type": "MX", "name": "@", "data": host, "priority": prio, "ttl": 3600} for prio, host in provider.mx]
        + [{"type": "TXT", "name": "@", "data": provider.spf, "ttl": 3600},
           {"type": "TXT", "name": planned_dkim_name(provider), "data": "v=DKIM1; k=rsa; p=PRETENDKEY", "ttl": 3600},
           {"type": "TXT", "name": "_dmarc", "data": "v=DMARC1; p=quarantine", "ttl": 3600}])
    inbox = FakeInboxReader()
    return Integrations(
        godaddy=gd,
        availability=FakeAvailabilityChecker(),
        mailbox=FakeMailboxProvider(existing={settings.smtp_user}, dkim_name=planned_dkim_name(provider)),
        dns=ZoneBackedResolver(gd),
        http=FakeHttpProbe(settings),
        mailer=DeliveringFakeMailer(inbox, settings.smtp_user),
        inbox=inbox,
        sleep=sleep or (lambda _s: None),
        fake=True,
        shop_web=_in_process,
        public_dns=lambda: [(f"pretend {label}", ZoneBackedResolver(gd)) for label in public_labels()],
    )


def _in_process(ctx):
    from app.proof import in_process

    return in_process(ctx)


def real_integrations(settings: Settings) -> Integrations:
    from app.checks.dns_resolver import AuthoritativeResolver

    return Integrations(
        godaddy=GoDaddyClient(settings),
        availability=GoDaddyAvailabilityChecker(),
        mailbox=TitanMailboxProvider(),
        dns=AuthoritativeResolver(),  # the zone's own nameservers (ns*.domaincontrol.com); unproven until the VPS
        http=RealHttpProbe(),
        mailer=SmtpMailer(settings),
        inbox=ImapInboxReader(settings),
        public_dns=_public_resolvers,
    )


def public_labels() -> list[str]:
    return [f"{name} {ip}" for name, ip in PUBLIC_RESOLVERS]


def _public_resolvers() -> list[tuple[str, DnsResolver]]:
    from app.checks.dns_resolver import RealDnsResolver

    return [(f"{name} {ip}", RealDnsResolver(nameservers=[ip], timeout=3.0)) for name, ip in PUBLIC_RESOLVERS]


@lru_cache
def _shared_fakes() -> Integrations:
    return fake_integrations(get_settings())


def get_integrations() -> Integrations:
    """FastAPI dependency: the server's own integrations (real when USE_FAKES=false). Tests override this."""
    settings = get_settings()
    return _shared_fakes() if settings.use_fakes else real_integrations(settings)


def get_practice_integrations() -> Integrations:
    """FastAPI dependency: the shared fake world, used for practice businesses. Tests override this."""
    return _shared_fakes()


def for_business(business, server: Integrations, practice: Integrations) -> Integrations:
    """Practice businesses NEVER get real integrations, whatever the server mode."""
    return practice if business.practice or server.fake else server
