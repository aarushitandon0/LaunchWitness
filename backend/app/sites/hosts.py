"""Map a request's Host header to a seller business (or to the app itself)."""

import re
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.config import Settings
from app.models import Business

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$")  # 3-30 characters
RESERVED_SUBDOMAINS = {"www", "app", "api", "admin", "mail", "email", "hello", "support", "help", "status", "login",
                       "auth", "static", "cdn", "assets", "docs", "blog", "godaddy", "airo", "launchwitness", "test",
                       "demo", "internal", "smtp", "imap", "ftp", "build", "ns1", "ns2", "autodiscover", "webmail",
                       "pay", "payment", "payments", "secure", "account", "accounts", "billing", "preview", "report"}
# Names that could pass a shop off as a well-known brand, bank or payment app.
BRAND_DENYLIST = {"godaddy", "airo", "paytm", "phonepe", "gpay", "googlepay", "google", "amazon", "flipkart",
                  "whatsapp", "instagram", "facebook", "meta", "razorpay", "upi", "bhim", "npci", "sbi", "hdfc",
                  "icici", "axis", "kotak", "paypal", "apple", "microsoft", "netflix", "swiggy", "zomato", "meesho"}


def slug_problem(slug: str) -> str | None:
    """None when `slug` may be a shop name; else one plain sentence saying why not."""
    if slug.startswith(("_", "xn--")) or not SLUG.match(slug):
        return ("A shop address needs 3 to 30 characters: small letters, numbers and dashes, "
                "starting and ending with a letter or number.")
    if slug in RESERVED_SUBDOMAINS:
        return "That shop address is reserved. Please pick another."
    parts = set(slug.split("-"))
    if parts & BRAND_DENYLIST or any(slug.startswith(b) for b in BRAND_DENYLIST if len(b) >= 6):
        return "That shop address looks like a well-known brand's name. Please pick one that is clearly yours."
    return None


def normalize_host(host: str) -> str:
    """'Meera.LocalHost:8000.' -> 'meera.localhost'"""
    h = host.strip().lower()
    if h.startswith("["):  # IPv6 literal
        return h
    return h.split(":", 1)[0].rstrip(".")


def subdomain_label(host: str, settings: Settings) -> str | None:
    """The single label under APP_DOMAIN, e.g. 'meera' for meera.localhost; else None."""
    suffix = "." + settings.app_domain.lower().rstrip(".")
    if host.endswith(suffix):
        label = host[: -len(suffix)]
        if label and "." not in label:
            return label
    return None


def is_public(b: Business) -> bool:
    """A shop is on the public internet only when it is launched for real. Drafts and practice
    shops are seen only by their owner, through the preview route."""
    return b.status == "live" and not b.practice


def business_for_host(host: str, settings: Settings, session: Session) -> Business | None:
    """The PUBLIC shop for this Host (live, not practice), paused or not. None for anything else,
    so a draft, a practice shop and a name nobody took all look the same from outside."""
    h = normalize_host(host)
    if not HOSTNAME.match(h) or h == settings.app_domain.lower().rstrip("."):
        return None
    label = subdomain_label(h, settings)
    q = select(Business).where(Business.status == "live", Business.practice == False)  # noqa: E712
    q = q.where(Business.subdomain == label) if label is not None else q.where(Business.domain == h)
    return session.exec(q).first()


def site_url(subdomain: str, settings: Settings) -> str:
    """Public URL of a seller's sandbox site, using APP_BASE_URL's scheme and port."""
    base = urlsplit(settings.app_base_url)
    port = f":{base.port}" if base.port else ""
    return f"{base.scheme or 'http'}://{subdomain}.{settings.app_domain}{port}/"
