"""Renewals (S10, feature 18): what runs out, when, and who renews it. It NEVER renews or pays by itself:
money always needs a person. One set of alert thresholds for things a person renews; the certificate is
renewed by Caddy on its own (about 30 days before the end), so its first warning comes later."""

from datetime import date

from app.config import Settings

THRESHOLDS = (30, 7, 1)  # domain names and the team mailbox: a person has to renew (and pay)
CERT_THRESHOLDS = (7, 1)  # Caddy renews ~30 days ahead; a warning before 7 days left would be noise


def state(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "lapsed"
    if days <= 7:
        return "urgent"
    if days <= 30:
        return "soon"
    return "ok"


def mailbox_days(settings: Settings, today: date | None = None) -> int | None:
    end = settings.mailbox_expires_on
    return None if end is None else (end - (today or date.today())).days


def item(what: str, label: str, days: int | None, who: str, plain: str) -> dict:
    return {"what": what, "label": label, "days_left": days, "state": state(days), "who": who, "plain": plain}


def card(settings: Settings, mode: str, zone: str, info: dict, today: date | None = None) -> list[dict]:
    """The Renewals card on a live shop's report. `info` is the latest check run's info_json."""
    out = [item("certificate", "Security certificate (the padlock)", info.get("cert_days_left"), "automatic",
                "Renews by itself, for free. We check it every day and tell you if it doesn't.")]
    if mode == "full":
        out.append(item("domain", f"Your website name ({zone})", info.get("domain_days_left"), "you",
                        "Renewing costs money, so we never do it for you. We'll remind you 30, 7 and 1 days before."))
    else:
        out.append(item("domain", f"{settings.app_domain} (your shop's address lives under it)",
                        info.get("app_domain_days_left"), "team",
                        "Our team renews it. You don't need to do anything."))
    out.append(item("mailbox", f"Our mailbox that sends your order emails ({settings.smtp_user})",
                    mailbox_days(settings, today), "team", "Our team renews it. You don't need to do anything."))
    return out


def nearest(items: list[dict]) -> dict | None:
    """The renewal that needs attention soonest (for "My shops"), or None when all are fine/unknown."""
    due = [i for i in items if i["state"] in ("soon", "urgent", "lapsed")]
    return min(due, key=lambda i: i["days_left"]) if due else None


def crossed(days: int | None, thresholds: tuple[int, ...]) -> list[int]:
    return [] if days is None else [t for t in thresholds if days <= t]
