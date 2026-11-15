"""Mail settings per email service: ONE table, read by the planner, the checker and the Doctor.

`secureserver` = GoDaddy Professional Email (what hello@launchwitness.com runs on; the default).
`titan` = Titan mail sold through GoDaddy (kept for sellers on that product).

The checker reads the live zone and compares it with the row for `MAIL_PROVIDER`. Nothing here
is ever written to the app's own domain (the GoDaddy client refuses that), and a launch never
replaces another service's working mail settings (see `executor.mail_write_decision`).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MailProvider:
    key: str
    label: str
    mx: tuple[tuple[int, str], ...]  # (priority, host)
    spf_include: str  # the include: that must be in the SPF line
    spf: str  # the full line we would write on a fresh domain
    # Signing (DKIM) record names differ per account. They are read from the live zone; this
    # is only the name planned for a brand-new domain in practice mode.
    dkim_selectors: tuple[str, ...] = ()


PROVIDERS: dict[str, MailProvider] = {
    "secureserver": MailProvider(
        key="secureserver", label="GoDaddy Professional Email",
        mx=((0, "smtp.secureserver.net"), (10, "mailstore1.secureserver.net")),
        spf_include="include:secureserver.net", spf="v=spf1 include:secureserver.net -all",
    ),
    "titan": MailProvider(
        key="titan", label="Titan (via GoDaddy)",
        mx=((10, "mx1.titan.email"), (20, "mx2.titan.email")),
        spf_include="include:spf.titan.email", spf="v=spf1 include:spf.titan.email ~all",
        dkim_selectors=("titan1",),
    ),
}


def provider_for(settings) -> MailProvider:
    return PROVIDERS[settings.mail_provider]


def planned_dkim_name(provider: MailProvider) -> str:
    """Record name planned for the signing key on a fresh domain."""
    return f"{provider.dkim_selectors[0] if provider.dkim_selectors else 'mail'}._domainkey"


def mx_hosts(records: list[dict]) -> set[str]:
    return {str(r.get("data", "")).rstrip(".").lower() for r in records if r.get("type", "MX") == "MX"}
