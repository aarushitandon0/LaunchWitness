"""Orders placed through a seller site's form: validate, store, email."""

import json
import re

from sqlmodel import Session

from app import audit
from app.agents.reader import Profile
from app.mail.smtp import Mailer
from app.models import Business, Order

MAX_QTY = 50


class OrderInvalid(ValueError):
    """Message is shown to the customer as-is."""


def parse_order_form(form: dict[str, str], profile: Profile) -> dict:
    if form.get("website"):  # honeypot field, hidden from people
        raise OrderInvalid("Sorry, something went wrong. Please try again.")
    name = " ".join(form.get("customer_name", "").split())[:80]
    phone = form.get("customer_phone", "").strip()
    note = form.get("note", "").strip()[:1000]
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
            items.append({"name": product.name, "qty": int(raw), "price_inr": product.price_inr})
    if not items and not note:
        raise OrderInvalid("Please choose at least one item, or tell us what you'd like in the note.")
    total = sum(it["qty"] * it["price_inr"] for it in items)
    return {"customer_name": name, "customer_phone": phone, "note": note, "items": items, "total_inr": total}


def order_email(business: Business, profile: Profile, order: Order, items: list[dict]) -> tuple[str, str]:
    from app.sites.render import format_inr

    test = "[TEST] " if order.is_test else ""
    subject = f"{test}New order for {profile.name} from {order.customer_name} (#{order.id})"
    lines = [f"New order #{order.id} for {profile.name}", "", f"Customer: {order.customer_name}",
             f"Phone: {order.customer_phone}", ""]
    lines += [f"- {it['qty']} x {it['name']} @ {format_inr(it['price_inr'])} = {format_inr(it['qty'] * it['price_inr'])}"
              for it in items] or ["(no items chosen; see note)"]
    lines += ["", f"Estimated total: {format_inr(order.total_inr)}"]
    if order.note:
        lines += ["", "Note from customer:", order.note]
    lines += ["", f"Placed: {order.created_at:%Y-%m-%d %H:%M} UTC", "Sent by LaunchWitness"]
    return subject, "\n".join(lines)


def place_order(session: Session, mailer: Mailer, *, business: Business, profile: Profile, data: dict,
                mail_to: str, is_test: bool = False) -> Order:
    order = Order(business_id=business.id, customer_name=data["customer_name"], customer_phone=data["customer_phone"],
                  items_json=json.dumps(data["items"], ensure_ascii=False), total_inr=data["total_inr"],
                  note=data["note"], is_test=is_test)
    session.add(order)
    session.commit()
    session.refresh(order)
    audit.record(session, actor="checker" if is_test else "customer", action="order_placed", target=f"order:{order.id}", result="ok",
                 business_id=business.id, detail=f"{len(data['items'])} item(s), total {data['total_inr']}")

    subject, body = order_email(business, profile, order, data["items"])
    try:
        order.email_message_id = mailer.send(to=mail_to, subject=subject, body=body)
        order.email_status = "sent"
        result, detail = "ok", f"to app mailbox, {order.email_message_id}"
    except Exception as e:  # keep the order even if the mail server is down
        order.email_status = "failed"
        result, detail = "failed", type(e).__name__
    session.add(order)
    session.commit()
    session.refresh(order)
    audit.record(session, actor="system", action="order_email", target=f"order:{order.id}", result=result,
                 business_id=business.id, detail=detail)
    return order
