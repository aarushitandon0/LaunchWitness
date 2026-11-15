"""Orders placed through a seller site's form: validate, store, email."""

import json
import re
from datetime import timedelta

from sqlmodel import Session, func, select

from app import audit
from app.agents.reader import Profile
from app.config import Settings
from app.mail.smtp import Mailer
from app.models import Business, Order, Plan, utcnow

MAX_QTY = 50


class OrderInvalid(ValueError):
    """Message is shown to the customer as-is."""


def parse_order_form(form: dict[str, str], profile: Profile) -> dict:
    if form.get("website"):  # honeypot field, hidden from people
        raise OrderInvalid("Sorry, something went wrong. Please try again.")
    name = " ".join(form.get("customer_name", "").split())[:80]
    phone = form.get("customer_phone", "").strip()
    note = form.get("note", "").strip()[:1000]
    if profile.allow_item_message:
        message = " ".join(form.get("item_message", "").split())[:200]
        if message:
            note = f"Message on the item: {message}" + (f"\n{note}" if note else "")
    if not name:
        raise OrderInvalid("Please add your name so we know who the order is for.")
    if not re.fullmatch(r"\+?[\d\s-]{10,20}", phone) or len(re.sub(r"\D", "", phone)) < 10:
        raise OrderInvalid("Please add a phone number we can call or WhatsApp (at least 10 digits).")
    items = []
    for i, product in enumerate(profile.products):
        raw = form.get(f"qty_{i}", "0").strip() or "0"
        if not raw.isdigit() or int(raw) > MAX_QTY:
            raise OrderInvalid(f"Please enter a quantity between 0 and {MAX_QTY}.")
        if int(raw) > 0:
            items.append({"name": product.name, "qty": int(raw), "price_inr": product.price_inr,
                          "addon": product.addon})
    if not items and not note:
        raise OrderInvalid("Please choose at least one item, or tell us what you'd like in the note.")
    if items and all(it["addon"] for it in items):
        raise OrderInvalid("Extras go with another item. Please choose an item too.")
    for it in items:
        del it["addon"]
    total = sum(it["qty"] * it["price_inr"] for it in items)
    return {"customer_name": name, "customer_phone": phone, "note": note, "items": items, "total_inr": total}


def order_email(business: Business, profile: Profile, order: Order, items: list[dict]) -> tuple[str, str]:
    from app.sites.render import format_inr

    test = "[TEST] " if order.is_test else ""
    code = f" [{order.nonce}]" if order.nonce else ""
    subject = f"{test}New order for {profile.name} from {order.customer_name} (#{order.id}){code}"
    lines = [f"New order #{order.id} for {profile.name}", "", f"Customer: {order.customer_name}",
             f"Phone: {order.customer_phone}", ""]
    if order.nonce:
        lines[1:1] = ["", "This is an automatic test order from LaunchWitness. No customer is waiting.",
                      f"Test code: {order.nonce}"]
    lines += [f"- {it['qty']} x {it['name']} @ {format_inr(it['price_inr'])} = {format_inr(it['qty'] * it['price_inr'])}"
              for it in items] or ["(no items chosen; see note)"]
    lines += ["", f"Estimated total: {format_inr(order.total_inr)}"]
    if order.note:
        lines += ["", "Note from customer:", order.note]
    lines += ["", f"Placed: {order.created_at:%Y-%m-%d %H:%M} UTC", "Sent by LaunchWitness"]
    return subject, "\n".join(lines)


def order_recipients(session: Session, settings: Settings, business: Business) -> list[str]:
    """Who gets this shop's order emails. ONE place decides it, for customers' orders and for the
    launch check's test order alike: the mailbox of the shop's launch, plus the owner's own email."""
    plan = session.exec(select(Plan).where(Plan.business_id == business.id, Plan.status == "done")
                        .order_by(Plan.id.desc())).first()
    out: list[str] = []
    for address in ((plan.mailbox if plan else "") or settings.smtp_user, business.owner_email):
        address = (address or "").strip()
        if address and address.lower() not in {a.lower() for a in out}:
            out.append(address)
    return out


TOO_MANY = ("This shop has had a lot of orders from here in a short time. Please try again in a few minutes, "
            "or message the shop directly.")


class TooManyOrders(Exception):
    pass


def check_order_limits(session: Session, settings: Settings, business: Business, visitor: str) -> None:
    """Per visitor (hashed IP) per shop per hour, and per shop per day. Test orders don't count."""
    real = (Order.business_id == business.id, Order.is_test == False)  # noqa: E712
    now = utcnow()
    mine = session.exec(select(func.count()).select_from(Order).where(
        *real, Order.visitor == visitor, Order.created_at >= now - timedelta(hours=1))).one()
    shop = session.exec(select(func.count()).select_from(Order).where(
        *real, Order.created_at >= now - timedelta(days=1))).one()
    if mine >= settings.orders_per_visitor_per_hour or shop >= settings.orders_per_shop_per_day:
        audit.record(session, actor="customer", action="order_placed", target=f"business:{business.id}",
                     result="blocked", business_id=business.id,
                     detail="visitor hourly limit" if mine >= settings.orders_per_visitor_per_hour else "shop daily limit")
        raise TooManyOrders


TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def existing_order(session: Session, business: Business, token: str) -> Order | None:
    """The order already made with this form token (a double tap or a re-sent form), if any."""
    if not TOKEN.match(token):
        return None
    return session.exec(select(Order).where(Order.business_id == business.id, Order.client_token == token)).first()


def order_view(order: Order) -> dict:
    return {"customer_name": order.customer_name, "customer_phone": order.customer_phone, "note": order.note,
            "items": json.loads(order.items_json), "total_inr": order.total_inr}


def place_order(session: Session, mailer: Mailer, settings: Settings, *, business: Business, profile: Profile,
                data: dict, is_test: bool = False, nonce: str = "", visitor: str = "", token: str = "") -> Order:
    """Store the order, then email it to `order_recipients`. The launch check's test order and a
    customer's order both come through here, so a passing test order proves the real path."""
    order = Order(business_id=business.id, customer_name=data["customer_name"], customer_phone=data["customer_phone"],
                  items_json=json.dumps(data["items"], ensure_ascii=False), total_inr=data["total_inr"],
                  note=data["note"], is_test=is_test, nonce=nonce, visitor=visitor,
                  client_token=token if TOKEN.match(token) else "")
    session.add(order)
    session.commit()
    session.refresh(order)
    audit.record(session, actor="checker" if is_test else "customer", action="order_placed", target=f"order:{order.id}", result="ok",
                 business_id=business.id, detail=f"{len(data['items'])} item(s), total {data['total_inr']}")

    recipients = order_recipients(session, settings, business)
    subject, body = order_email(business, profile, order, data["items"])
    try:
        order.email_message_id = mailer.send(to=", ".join(recipients), subject=subject, body=body)
        order.email_status = "sent"
        result, detail = "ok", f"to {len(recipients)} address(es), {order.email_message_id}"
    except Exception as e:  # keep the order even if the mail server is down
        order.email_status = "failed"
        result, detail = "failed", type(e).__name__
    session.add(order)
    session.commit()
    session.refresh(order)
    audit.record(session, actor="system", action="order_email", target=f"order:{order.id}", result=result,
                 business_id=business.id, detail=detail)
    return order
