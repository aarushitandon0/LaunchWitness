"""Render a seller's site from the ONE fixed template + their Profile."""

import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlencode

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.agents.reader import Product, Profile

TEMPLATES = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))


def format_inr(amount: int) -> str:
    """Indian digit grouping: 1200 -> '₹1,200', 150000 -> '₹1,50,000'."""
    s = str(abs(int(amount)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return ("-" if amount < 0 else "") + "₹" + s


_env.filters["inr"] = format_inr


def whatsapp_digits(number: str) -> str:
    digits = re.sub(r"\D", "", number)
    if len(digits) == 10:  # Indian mobile without country code
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits


def order_whatsapp_link(profile: Profile, order: dict | None) -> str | None:
    """Thank-you page: the customer sends the order (ref + items) to the shop's WhatsApp in one tap."""
    number = whatsapp_digits(profile.whatsapp or profile.phone)
    if len(number) < 11 or not order or not order.get("ref"):
        return None
    items = ", ".join(f"{it['qty']} x {it['name']}" for it in order.get("items", []))[:600]
    text = f"Hi {profile.name}, this is my order {order['ref']}" + (f": {items}" if items else "") + "."
    return f"https://wa.me/{number}?{urlencode({'text': text}, quote_via=quote)}"


def whatsapp_link(profile: Profile) -> str | None:
    number = whatsapp_digits(profile.whatsapp or profile.phone)
    if len(number) < 11:
        return None
    text = f"Hi {profile.name}, I'd like to place an order."
    return f"https://wa.me/{number}?{urlencode({'text': text}, quote_via=quote)}"


def upi_uri(profile: Profile) -> str | None:
    if not profile.upi_id:
        return None
    return "upi://pay?" + urlencode({"pa": profile.upi_id, "pn": profile.name, "cu": "INR"}, quote_via=quote, safe="@")


def upi_qr_svg(uri: str) -> Markup:
    svg = segno.make(uri, error="m").svg_inline(scale=1, border=2, omitsize=True, dark="#1f2937")
    return Markup(svg.replace("<svg ", '<svg role="img" aria-label="UPI payment QR code" ', 1))


@dataclass
class Category:
    name: str
    items: list[tuple[int, Product]] = field(default_factory=list)  # (index in profile.products, product)


def group_products(products: list[Product]) -> list[Category]:
    """Main items by category, in first-seen order; items keep their order inside each. Extras are left out."""
    groups: dict[str, Category] = {}
    for i, p in enumerate(products):
        if p.addon:
            continue
        key = p.category.strip() or "Menu"
        groups.setdefault(key.lower(), Category(name=key)).items.append((i, p))
    return list(groups.values())


def extras(products: list[Product]) -> list[tuple[int, Product]]:
    return [(i, p) for i, p in enumerate(products) if p.addon]


def badges(profile: Profile) -> list[str]:
    """Short facts for the top of the page, only from profile data. A missing field = no badge."""
    out = []
    if profile.selling_point.strip():
        out.append(profile.selling_point.strip())
    if profile.min_notice_days == 1:
        out.append("Order 1 day ahead")
    elif profile.min_notice_days > 1:
        out.append(f"Order {profile.min_notice_days} days ahead")
    if profile.pickup_available and profile.delivery_available:
        out.append("Pickup or delivery")
    elif profile.pickup_available:
        out.append("Pickup available")
    elif profile.delivery_available:
        out.append("Delivery available")
    return out


def monogram(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9\u0900-\u097F]+", name) if w.lower() not in {"the", "and", "s"}]
    return "".join(w[0] for w in words[:2]).upper() or "•"


def area_is_repeated(profile: Profile) -> bool:
    return bool(profile.area.strip()) and profile.area.strip().lower() in profile.tagline.lower()


def render_site(profile: Profile, *, page: str = "home", order: dict | None = None, form_error: str = "",
                form_values: dict | None = None, preview: bool = False, shop: str = "") -> str:
    """page: 'home' | 'privacy' | 'thanks'. preview=True: the owner's private look at a shop that
    isn't public (banner on top, the order button is off)."""
    uri = upi_uri(profile)
    return _env.get_template("seller.html").render(
        p=profile,
        page=page,
        categories=group_products(profile.products),
        extras=extras(profile.products),
        badges=badges(profile),
        monogram=monogram(profile.name),
        show_area=bool(profile.area.strip()) and not area_is_repeated(profile),
        whatsapp_url=whatsapp_link(profile),
        order_whatsapp_url=order_whatsapp_link(profile, order) if page == "thanks" else None,
        upi=uri,
        upi_qr=upi_qr_svg(uri) if uri else None,
        order=order,
        form_error=form_error,
        form=form_values or {},
        order_token=(form_values or {}).get("order_token") or secrets.token_urlsafe(16),
        preview=preview,
        shop=shop,  # printed as <meta name="lw-shop">: the HTTPS check looks for it
    )
