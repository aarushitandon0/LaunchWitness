"""Map a request's Host header to a seller business (or to the app itself)."""

import re
from urllib.parse import urlsplit

from sqlmodel import Session, select

from app.config import Settings
from app.models import Business

HOSTNAME = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")
SUBDOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,40}[a-z0-9])?$")
RESERVED_SUBDOMAINS = {"www", "api", "app", "admin", "internal", "mail", "email", "smtp", "imap", "ftp", "build",
                       "status", "help", "support", "static", "assets"}


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


def business_for_host(host: str, settings: Settings, session: Session) -> Business | None:
    h = normalize_host(host)
    if not HOSTNAME.match(h) or h == settings.app_domain.lower().rstrip("."):
        return None
    label = subdomain_label(h, settings)
    if label is not None:
        return session.exec(select(Business).where(Business.subdomain == label)).first()
    return session.exec(select(Business).where(Business.domain == h)).first()


def site_url(subdomain: str, settings: Settings) -> str:
    """Public URL of a seller's sandbox site, using APP_BASE_URL's scheme and port."""
    base = urlsplit(settings.app_base_url)
    port = f":{base.port}" if base.port else ""
    return f"{base.scheme or 'http'}://{subdomain}.{settings.app_domain}{port}/"
