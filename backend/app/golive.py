"""S10.5 go-live checklist: what a real shop needs before "Launch for real".

Drafts and practice launches are never blocked by this. Only a real launch is (routers/launch.py, at plan time and
again at approval). Each item is plain words for the owner. Owner-confirmed steps are stored with the exact value
that was confirmed, so changing the WhatsApp number or the UPI ID / name quietly undoes the confirmation.
"""

from dataclasses import asdict, dataclass

from sqlmodel import Session

from app.agents.reader import Profile, indian_mobile
from app.models import Business
from app.safety.access import owner_emails


@dataclass
class Item:
    key: str
    label: str  # what is needed, in plain words
    done: bool
    hint: str = ""  # what to do next when it isn't done


def upi_key(profile: Profile) -> str:
    return f"{profile.upi_id}|{profile.upi_display_name.strip()}"


def whatsapp_confirmed(b: Business, profile: Profile) -> bool:
    return bool(profile.whatsapp) and b.wa_confirmed == profile.whatsapp


def upi_confirmed(b: Business, profile: Profile) -> bool:
    return bool(profile.upi_id and profile.upi_display_name.strip()) and b.upi_confirmed == upi_key(profile)


def checklist(session: Session, b: Business) -> list[Item]:
    p = Profile.model_validate_json(b.profile_json)
    priced = [x for x in p.products if not x.addon and x.price_inr > 0]
    has_way = p.pickup_available or p.delivery_available
    way_ok = has_way and (not p.delivery_available or bool(p.delivery_areas.strip())) \
        and (not p.pickup_available or bool(p.area.strip()))
    return [
        Item("email", "A verified sign-in email for orders and alerts", bool(owner_emails(session, b.id)) and not b.guest_hash,
             "Sign in with your email."),
        Item("shop", "Shop name, shop address and at least one item with a price",
             bool(p.name.strip() and b.subdomain and priced), "Add an item with its price."),
        Item("whatsapp", "Your WhatsApp number, checked by you", whatsapp_confirmed(b, p) and indian_mobile(p.whatsapp) is not None,
             "Add your WhatsApp number, tap “Test this number”, then “Yes, that's me”." if p.whatsapp
             else "Add your WhatsApp number."),
        Item("upi", "Your UPI ID and the name your UPI app shows, checked by you", upi_confirmed(b, p),
             "Do the ₹1 UPI test and confirm the name matches." if p.upi_id and p.upi_display_name.strip()
             else "Add your UPI ID and the name your UPI app shows."),
        Item("fulfilment", "How customers get their order: pickup (your area) and/or delivery (areas and fee)", way_ok,
             "Choose pickup or delivery." if not has_way
             else "Add the areas you deliver to." if p.delivery_available and not p.delivery_areas.strip()
             else "Add your area or locality for pickup."),
        Item("rules", "Your working days and hours (and how many days' notice you need)", bool(p.hours.strip()),
             "Add your working days and hours."),
        Item("agreements", "You confirmed you make or sell these yourself, and accepted the Terms",
             b.own_goods_at is not None and b.terms_at is not None, "Tick both boxes and save."),
        Item("preview", "You looked at your shop's preview at least once", b.previewed_at is not None,
             "Tap “Preview my shop”."),
    ]


def missing(session: Session, b: Business) -> list[Item]:
    return [i for i in checklist(session, b) if not i.done]


def refusal(items: list[Item]) -> str:
    return "Before your shop can go live, please finish: " + "; ".join(i.label.lower() for i in items) + "."


def out(session: Session, b: Business) -> dict:
    items = checklist(session, b)
    return {"ready": all(i.done for i in items), "items": [asdict(i) for i in items]}
