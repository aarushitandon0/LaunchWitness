"""Render a seller's site from the ONE fixed template + their Profile."""

import re
import secrets
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode

import segno
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.agents.reader import Product, Profile
from app.sites import fulfilment as ful
from app.sites import themes

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


def upi_uri(profile: Profile, amount_inr: int | None = None) -> str | None:
    """amount_inr: only for the owner's Rs 1 UPI name test (she pays herself, or cancels at the PIN screen)."""
    if not profile.upi_id:
        return None
    q = {"pa": profile.upi_id, "pn": profile.name, "cu": "INR"}
    if amount_inr is not None:
        q = {"pa": profile.upi_id, "pn": profile.name, "am": f"{amount_inr}.00", "cu": "INR",
             "tn": "LaunchWitness UPI test"}
    return "upi://pay?" + urlencode(q, quote_via=quote, safe="@")


def upi_qr_svg(uri: str) -> Markup:
    svg = segno.make(uri, error="m").svg_inline(scale=1, border=2, omitsize=True, dark="#1f2937")
    return Markup(svg.replace("<svg ", '<svg role="img" aria-label="UPI payment QR code" ', 1))


PLAN_WORDS = re.compile(r"\b(plans?|weekly|monthly|subscriptions?|thali plans?)\b", re.I)


@dataclass
class Category:
    name: str
    items: list[tuple[int, Product]] = field(default_factory=list)  # (index in profile.products, product)

    @property
    def from_inr(self) -> int | None:
        """The lowest price in this group (shown as "from ₹X" on the gifts page's collection tiles)."""
        return min((p.price_inr for _, p in self.items), default=None)

    @property
    def is_plan(self) -> bool:
        return bool(PLAN_WORDS.search(self.name))


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
    o = ful.offers(profile)
    if o["pickup"] and (o["local"] or o["india"]):
        out.append("Pickup or " + ("shipping across India" if o["india"] else "delivery"))
    elif o["pickup"]:
        out.append("Pickup available")
    elif o["india"]:
        out.append("Ships across India")
    elif o["local"]:
        out.append("Delivery available")
    if ful.on_break(profile):
        out.append(ful.break_line(profile))
    return out


def how_steps(profile: Profile) -> list[tuple[str, str]]:
    """"How ordering works": the steps of the real order path, with only the facts the seller gave."""
    first = "Pick what you'd like from the menu."
    if profile.min_notice_days:
        first += f" Please order at least {profile.min_notice_days} day{'s' if profile.min_notice_days != 1 else ''} ahead."
    steps = [("Choose", first), ("Send your order", "Add your name and phone number. Nothing is charged on this page."),
             ("We confirm", "The shop contacts you to confirm the details, timing and the final amount.")]
    o = ful.offers(profile)
    if o["pickup"] and (o["local"] or o["india"]):
        steps.append(("Pickup or delivery", "Collect it yourself or have it " + ("shipped" if o["india"] else "delivered") + ", as you choose on the order form."))
    elif o["pickup"]:
        steps.append(("Pickup", "You collect it. The shop shares the exact address on WhatsApp once your order is confirmed."))
    elif o["local"]:
        steps.append(("Delivery", "The shop delivers it" + (f" in {ful.area_phrase(profile)}" if ful.area_phrase(profile) else "") + "."))
    elif o["india"]:
        steps.append(("Shipping", "It is sent by courier" + (f" within {profile.dispatch_days} day{'s' if profile.dispatch_days != 1 else ''}" if profile.dispatch_days else "") + "."))
    if profile.upi_id or profile.accepts_cash:
        steps.append(("Pay", ful.terms_words(profile)))
    return steps


def lowest_price(categories: list["Category"]) -> int | None:
    prices = [p.price_inr for c in categories for _, p in c.items]
    return min(prices) if prices else None


def monogram(name: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9\u0900-\u097F]+", name) if w.lower() not in {"the", "and", "s"}]
    return "".join(w[0] for w in words[:2]).upper() or "•"


def pay_view(profile: Profile, order: dict) -> dict | None:
    """The thank-you page's money lines: what is paid now (with a UPI link and QR for exactly that amount and the order
    reference in the note) and what is left. None for an order saved before payment terms existed."""
    if not order.get("payment_terms"):
        return None
    now, later = order.get("pay_now_inr", 0), order.get("pay_later_inr", 0)
    uri = ful.upi_order_uri(profile, now, order.get("ref", "")) if now and order.get("ref") else None
    return {"now": now, "later": later, "uri": uri, "qr": upi_qr_svg(uri) if uri else None,
            "when": "delivery" if order.get("fulfilment") == "delivery" else "pickup"}


def public_place(profile: Profile) -> str:
    """'Baner, Pune': the locality and the city, never a street address. The city is left out when the locality already has it."""
    area, city = profile.area.strip(), profile.city.strip()
    if city and city.lower() not in area.lower():
        return f"{area}, {city}" if area else city
    return area


def area_is_repeated(profile: Profile) -> bool:
    return bool(profile.area.strip()) and profile.area.strip().lower() in profile.tagline.lower()


def delivery_refusal(profile: Profile) -> str:
    from app.sites.orders import delivery_refusal as _refusal

    return _refusal(profile)


def render_site(profile: Profile, *, page: str = "home", order: dict | None = None, form_error: str = "",
                form_values: dict | None = None, preview: bool = False, shop: str = "", demo: bool = False,
                base: str = "", photos: dict | None = None, full_dates: list[str] | None = None,
                today: "date | None" = None) -> str:
    """page: 'home' | 'privacy' | 'thanks'. preview=True: the owner's private look at a shop that
    isn't public (banner on top, the order button is off). demo=True: a sample shop served by the app at
    `base` (e.g. /demo/meera), labelled as a demo; its form places no order."""
    uri = upi_uri(profile)
    theme, accent = themes.resolve(profile)
    cats = group_products(profile.products)
    sc = profile.section_copy
    tagline = profile.tagline.strip()
    headline = sc.hero_line or profile.name
    lede = tagline if tagline and tagline.lower() != headline.lower() else ""
    ph = photos or {"shop": [], "items": {}}
    day = today or ful.today_ist()
    o = ful.offers(profile)
    shipped = bool(o["india"])
    marks = {x.food_mark for x in profile.products if x.food_mark}
    from app.sites.newness import is_new

    new_idx = [i for i, x in enumerate(profile.products) if is_new(x.new_until, day)]  # S19D: "New" badge
    take = 3 if theme.hero == "centered" else 1  # photos shown in the hero; the rest go to the strip below it
    return _env.get_template("seller.html").render(
        theme=theme,
        accent=accent,
        css=themes.css_for(theme, accent),
        font_base="/shop-assets/fonts/",
        headline=headline,
        lede=lede,
        eyebrow=profile.name if headline.strip().lower() != profile.name.strip().lower() else "",
        about_text=profile.about or sc.about,  # her own About text wins; the Reader's short paragraph fills in when empty
        hero_photos=ph["shop"][:take],
        rest_photos=ph["shop"][take:],
        steps=how_steps(profile),
        min_price=lowest_price(cats),
        p=profile,
        page=page,
        categories=cats,
        extras=extras(profile.products),
        new_idx=new_idx,
        new_names=[profile.products[i].name for i in new_idx],
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
        demo=demo,
        base=base,  # prefix for the shop's own links ("" on a shop host)
        photos=ph,  # S12 (app/photos.py for_site); none = the placeholders stay
        # S15: where she sells, when, how she is paid. All the rules live in app/sites/fulfilment.py.
        offers=o,
        choices=[c for c, on in (("pickup", o["pickup"]), ("delivery", o["local"] or o["india"])) if on],
        delivery_word="Shipping" if shipped else "Delivery",
        fee_text=ful.fee_words(profile) if (o["local"] or o["india"]) else "",
        area_text=ful.area_phrase(profile),
        area_pins=",".join(ful.parse_areas(profile.delivery_areas).pins),
        area_places="|".join(x.lower() for x in ful.parse_areas(profile.delivery_areas).localities),
        refusal_text=delivery_refusal(profile) if o["local"] else "",
        place=public_place(profile),
        terms_text=ful.terms_words(profile),
        cancel_text=ful.cancellation_line(profile),
        is_break=ful.on_break(profile, day),
        break_text=ful.break_line(profile),
        date_min=ful.earliest(profile, day).isoformat(),
        date_max=ful.latest(day).isoformat(),
        days_off=",".join(str(d) for d in profile.days_off),
        days_off_text=ful.days_off_words(profile),
        full_dates=",".join(full_dates or []),
        mark_words=ful.FOOD_MARK_WORDS,
        marks_used=sorted(marks),
        pay=pay_view(profile, order) if page == "thanks" and order else None,
        pickup_text="You collect it. The shop shares the exact address on WhatsApp once your order is confirmed.",
    )
