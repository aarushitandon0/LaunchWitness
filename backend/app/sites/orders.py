"""Orders placed through a seller site's form: validate, store, email."""

import json
import re
import secrets
from datetime import date, timedelta

from sqlmodel import Session, func, select

from app import audit
from app.agents.reader import Profile
from app.config import Settings
from app.mail.smtp import Mailer
from app.models import Business, Order, utcnow
from app.safety.access import owner_emails, run_by_team
from app.sites import fulfilment as ful

MAX_QTY = 50

# The owner's order status. New → Confirmed → Paid → Done, or Cancelled before it's done. Paid can be
# skipped (cash on pickup). Nothing goes back, and Done / Cancelled are final.
STATUS_STEPS: dict[str, tuple[str, ...]] = {
    "new": ("confirmed", "cancelled"),
    "confirmed": ("paid", "done", "cancelled"),
    "paid": ("done", "cancelled"),
    "done": (),
    "cancelled": (),
}
STATUS_LABELS = {"new": "New", "confirmed": "Confirmed", "paid": "Paid", "done": "Done", "cancelled": "Cancelled"}


def can_move(current: str, to: str) -> bool:
    return to in STATUS_STEPS.get(current, ())


def customer_whatsapp_link(shop_name: str, order: Order) -> str | None:
    """A wa.me link to the CUSTOMER's phone with a ready-typed message from the owner. Nothing is sent by us:
    the owner's own WhatsApp opens with the text, and she presses send."""
    from urllib.parse import quote

    from app.sites.render import format_inr, whatsapp_digits

    number = whatsapp_digits(order.customer_phone)
    if not 11 <= len(number) <= 15:  # 10-digit Indian mobiles were given +91 above
        return None
    first = order.customer_name.split()[0] if order.customer_name.split() else ""
    text = (f"Hi {first}, this is {shop_name}. Got your order {order.ref} for {format_inr(order.total_inr)}. "
            "I'll confirm the details here.")
    return f"https://wa.me/{number}?text={quote(text, safe='')}"


def tel_link(phone: str) -> str:
    from app.sites.render import whatsapp_digits

    digits = whatsapp_digits(phone)
    return f"tel:+{digits}" if digits else ""


class OrderInvalid(ValueError):
    """Message is shown to the customer as-is."""


TEST_ADDRESS = "Automatic test order. No real address."
TEST_PIN = "110001"  # a valid PIN code; for local delivery the test address names a place she serves (see test_defaults)


def test_defaults(profile: Profile) -> dict[str, str]:
    """What the checker's test order fills in for the fields it doesn't know about: pickup when she offers pickup,
    otherwise a delivery INSIDE her area (her first listed PIN, or a test address naming her first locality). The same
    checks a customer's order faces then run on it, so a test order proves the real path in every selling mode."""
    o = ful.offers(profile)
    if o["pickup"]:
        return {"fulfilment": "pickup"}
    if o["local"]:
        a = ful.parse_areas(profile.delivery_areas)
        where = a.localities[0] if a.localities else ""
        return {"fulfilment": "delivery", "delivery_address": f"{TEST_ADDRESS} {where}".strip(),
                "delivery_pin": a.pins[0] if a.pins else TEST_PIN}
    if o["india"]:
        return {"fulfilment": "delivery", "delivery_address": TEST_ADDRESS, "delivery_pin": TEST_PIN}
    return {}


def clean_address(text: str) -> str:
    """A multi-line address: each line tidied, blank lines dropped, 300 characters at most."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(x for x in lines if x)[:300]


def delivery_refusal(profile: Profile) -> str:
    where = ful.area_phrase(profile)
    pickup = " You could choose pickup instead." if ful.offers(profile)["pickup"] else ""
    if where:
        return f"{profile.name} delivers only in {where}.{pickup}"
    return f"{profile.name} can't deliver to that address yet.{pickup}"


def orders_on(session: Session, business_id: int, day: str) -> int:
    """Her real orders already wanted on this date (cancelled ones free the day up; test orders never count)."""
    return session.exec(select(func.count()).select_from(Order).where(
        Order.business_id == business_id, Order.is_test == False, Order.wanted_date == day,  # noqa: E712
        Order.status != "cancelled")).one()


def full_days(session: Session | None, business: Business | None, profile: Profile, today: date | None = None) -> list[str]:
    """Dates that reached her daily limit (for the date picker): only dates, never who ordered."""
    if session is None or business is None or not profile.max_orders_per_day:
        return []
    today = today or ful.today_ist()
    rows = session.exec(select(Order.wanted_date, func.count()).where(
        Order.business_id == business.id, Order.is_test == False, Order.status != "cancelled",  # noqa: E712
        Order.wanted_date >= today.isoformat()).group_by(Order.wanted_date)).all()
    return ful.full_dates({d: n for d, n in rows if d}, profile)


def parse_order_form(form: dict[str, str], profile: Profile, *, test: bool = False, session: Session | None = None,
                     business: Business | None = None, today: date | None = None) -> dict:
    """Everything the customer sent, checked against the shop's own rules. Prices, fees and totals come ONLY from the
    profile: a price or fee field in the form is never read. `test` fills the fulfilment fields (see test_defaults) and
    leaves the date out; a customer's order must give them. Raises OrderInvalid with a message fit to show as-is."""
    if form.get("website"):  # honeypot field, hidden from people
        raise OrderInvalid("Sorry, something went wrong. Please try again.")
    today = today or ful.today_ist()
    if test:
        form = {**test_defaults(profile), **{k: v for k, v in form.items() if v}}
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

    # --- how it gets to the customer
    o = ful.offers(profile)
    choices = [c for c, on in (("pickup", o["pickup"]), ("delivery", o["local"] or o["india"])) if on]
    fulfilment, address, pin = "", "", ""
    if choices:
        asked = form.get("fulfilment", "").strip()
        if not asked and len(choices) == 1:
            asked = choices[0]
        if asked not in choices:
            raise OrderInvalid("Please choose " + (" or ".join(c if c == "pickup" else "delivery" for c in choices)) + ".")
        fulfilment = asked
    if fulfilment == "delivery":
        address = clean_address(form.get("delivery_address", ""))
        pin = re.sub(r"\s", "", form.get("delivery_pin", ""))
        if len(address) < 6:
            raise OrderInvalid("Please add the address we should deliver to.")
        if not ful.PIN.fullmatch(pin):
            raise OrderInvalid("Please add your 6-digit PIN code.")
        if o["local"] and not ful.serves(profile, address, pin):
            raise OrderInvalid(delivery_refusal(profile))

    # --- when
    wanted = ""
    raw_date = form.get("wanted_date", "").strip()
    if raw_date:
        day = ful.parse_date(raw_date)
        if day is None:
            raise OrderInvalid("Please pick the date you want your order by.")
        taken = orders_on(session, business.id, day.isoformat()) if session is not None and business is not None else 0
        if problem := ful.date_problem(profile, day, today, taken):
            raise OrderInvalid(problem)
        wanted = day.isoformat()
    elif ful.date_required(profile) and not test:
        raise OrderInvalid("Please pick the date you want your order by.")
    slot = " ".join(form.get("time_slot", "").split())
    if profile.time_slots and slot and slot not in profile.time_slots:
        raise OrderInvalid("Please pick one of the time slots on the list.")
    if not profile.time_slots:
        slot = ""

    # --- the money, worked out here from the menu
    items_sum = ful.items_total(items)
    fee = ful.fee_for(profile, fulfilment, items_sum)
    total = items_sum + fee
    pay_now, pay_later = ful.pay_split(profile, total)
    return {"customer_name": name, "customer_phone": phone, "note": note, "items": items, "total_inr": total,
            "items_inr": items_sum, "fee_inr": fee, "fulfilment": fulfilment, "delivery_address": address,
            "delivery_pin": pin, "wanted_date": wanted, "time_slot": slot, "payment_terms": profile.payment_terms,
            "pay_now_inr": pay_now, "pay_later_inr": pay_later}


TEST_SUBJECT = "TEST, not a real order:"  # S19B: every test email's subject starts with this
TEST_BANNER = ("This is a check from LaunchWitness. No customer placed this order. You don't need to do anything "
               "except tap 'Yes, I got it' if asked.")  # its body's first line (a grey banner in the HTML layout)


def order_email(business: Business, profile: Profile, order: Order, items: list[dict],
                confirm_url: str = "", orders_url: str = "") -> tuple[str, str]:
    """A customer's order email, or (S19B) a test email that can't be mistaken for one: the subject starts with
    TEST_SUBJECT and keeps the one-time code (the inbox match needs it), the body opens with TEST_BANNER, and there
    are no buttons to call or WhatsApp a "customer"."""
    from app.sites.render import format_inr

    if order.is_test:
        code = f" [{order.nonce}]" if order.nonce else ""
        subject = f"{TEST_SUBJECT} {profile.name} ({order.ref}){code}"
        lines = [TEST_BANNER, "", f"Test order {order.ref} for {profile.name}, placed through your shop's order form."]
        if order.nonce:
            lines.append(f"Test code: {order.nonce}")
        lines.append("")
    else:
        subject = f"New order for {profile.name} from {order.customer_name} ({order.ref})"
        lines = [f"New order {order.ref} for {profile.name}", "", f"Customer: {order.customer_name}",
                 f"Phone: {order.customer_phone}"]
        if tel := tel_link(order.customer_phone):
            lines.append(f"Call: {tel}")
        if wa := customer_whatsapp_link(profile.name, order):
            lines.append(f"WhatsApp the customer: {wa}")
        lines.append("")
    lines += [f"- {it['qty']} x {it['name']} @ {format_inr(it['price_inr'])} = {format_inr(it['qty'] * it['price_inr'])}"
              for it in items] or ["(no items chosen; see note)"]
    if order.fee_inr:
        what = "Shipping" if ful.offers(profile)["india"] else "Delivery"
        lines.append(f"- {what}: {format_inr(order.fee_inr)}")
    lines += ["", f"Total: {format_inr(order.total_inr)}"]
    if order.payment_terms:  # S15: what the customer was told to pay, and what is left
        lines.append(f"Paid now (asked of the customer): {format_inr(order.pay_now_inr)}" if order.pay_now_inr
                     else "Nothing asked to be paid now.")
        if order.pay_later_inr:
            lines.append(f"Due on {'delivery' if order.fulfilment == 'delivery' else 'pickup'}: {format_inr(order.pay_later_inr)}")
    if order.fulfilment == "pickup" and order.is_test:
        lines += ["", "How: pickup (test)."]
    elif order.fulfilment == "pickup":
        lines += ["", "How: PICKUP. Send the exact address on WhatsApp once you confirm the order."]
    elif order.fulfilment == "delivery":
        lines += ["", "How: " + ("SHIPPING across India" if ful.offers(profile)["india"] else "LOCAL DELIVERY"),
                  "Deliver to:", *order.delivery_address.splitlines(), f"PIN code: {order.delivery_pin}"]
        if ful.offers(profile)["india"] and profile.dispatch_days:
            lines.append(f"Dispatch within {profile.dispatch_days} day{'s' if profile.dispatch_days != 1 else ''}.")
    if order.wanted_date:
        d = ful.parse_date(order.wanted_date)
        lines.append(f"Wanted by: {ful.nice_date(d) if d else order.wanted_date}" + (f", {order.time_slot}" if order.time_slot else ""))
    if (cancel := ful.cancellation_line(profile)) and not order.is_test:
        lines += ["", f"Your cancellation rule shown to the customer: {cancel}"]
    if order.note:
        lines += ["", "Note from customer:", order.note]
    if confirm_url:
        lines += ["", "Did this email reach you? Tap here to say so (it proves your orders reach you):", confirm_url]
    if orders_url and not order.is_test:  # test orders are never on the Orders page
        lines += ["", f"See and update all your orders: {orders_url}"]
    lines += ["", f"Placed: {order.created_at:%Y-%m-%d %H:%M} UTC", "Sent by LaunchWitness"]
    return subject, "\n".join(lines)


def order_recipients(session: Session, settings: Settings, business: Business) -> list[str]:
    """Who gets this shop's order emails. ONE place decides it, for customers' orders and for the
    checker's test order alike: the owner's verified sign-in address. That address was proven at
    sign-in and is proven again by the test order. The app's own mailbox is added only for shops
    we run ourselves, and stands in while a guest practice shop has no owner yet."""
    out = owner_emails(session, business.id)
    if not out or run_by_team(session, business.id):
        if settings.smtp_user.lower() not in {a.lower() for a in out}:
            out.append(settings.smtp_user)
    return out


def test_audience(trigger: str) -> str:
    """S19B: who a check run's test email goes to. Monitoring (daily run, its re-check) never emails the seller:
    it goes to LaunchWitness's own check mailbox ("check"). Launch, "Check again" and "Describe the problem" go to
    the shop's order address (""): she asked for the check."""
    return "check" if trigger.startswith("monitor_") else ""


def test_recipients(session: Session, settings: Settings, business: Business, audience: str) -> list[str]:
    if audience == "check" and settings.smtp_user:
        return [settings.smtp_user]
    return order_recipients(session, settings, business)


REF_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no 0/O/1/I


def new_ref() -> str:
    """Public order reference: random, so it reveals no count and can't be guessed."""
    return "LW-" + "".join(secrets.choice(REF_ALPHABET) for _ in range(8))


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
    """What the thank-you page may show. Deliberately NOT the street address: that stays with the owner."""
    return {"customer_name": order.customer_name, "customer_phone": order.customer_phone, "note": order.note,
            "items": json.loads(order.items_json), "total_inr": order.total_inr, "ref": order.ref,
            "fulfilment": order.fulfilment, "delivery_pin": order.delivery_pin, "wanted_date": order.wanted_date,
            "time_slot": order.time_slot, "fee_inr": order.fee_inr, "payment_terms": order.payment_terms,
            "pay_now_inr": order.pay_now_inr, "pay_later_inr": order.pay_later_inr}


def place_order(session: Session, mailer: Mailer, settings: Settings, *, business: Business, profile: Profile,
                data: dict, is_test: bool = False, nonce: str = "", visitor: str = "", token: str = "",
                confirm_url: str = "", channel: str = "smtp", recipients: list[str] | None = None) -> Order:
    """Store the order, then email it to `order_recipients` through the outbox. The launch check's test order and
    a customer's order both come through here, so a passing test order proves the real path.

    S13: the order is saved first and its email queued; the outbox tries it at once and keeps retrying if the
    mail server is slow or down, so a customer's order is never lost. `email_status` follows the outbox row."""
    from app import outbox

    order = Order(business_id=business.id, customer_name=data["customer_name"], customer_phone=data["customer_phone"],
                  items_json=json.dumps(data["items"], ensure_ascii=False), total_inr=data["total_inr"],
                  note=data["note"], is_test=is_test, nonce=nonce, visitor=visitor, ref=new_ref(),
                  client_token=token if TOKEN.match(token) else "", email_status="queued",
                  fulfilment=data.get("fulfilment", ""), delivery_address=data.get("delivery_address", ""),
                  delivery_pin=data.get("delivery_pin", ""), wanted_date=data.get("wanted_date", ""),
                  time_slot=data.get("time_slot", ""), fee_inr=data.get("fee_inr", 0),
                  payment_terms=data.get("payment_terms", ""), pay_now_inr=data.get("pay_now_inr", 0),
                  pay_later_inr=data.get("pay_later_inr", 0))
    session.add(order)
    session.commit()
    session.refresh(order)
    audit.record(session, actor="checker" if is_test else "customer", action="order_placed", target=f"order:{order.id}", result="ok",
                 business_id=business.id,  # never the address, PIN or phone: only counts and the mode
                 detail=f"{len(data['items'])} item(s), total {data['total_inr']}"
                 + (f", {data['fulfilment']}" if data.get("fulfilment") else ""))

    recipients = recipients or order_recipients(session, settings, business)
    orders_url = f"{settings.app_base_url.rstrip('/')}/#/b/{business.id}/orders"
    subject, body = order_email(business, profile, order, data["items"], confirm_url, orders_url)
    kind = "test_order" if is_test else "order"
    outbox.send(session, settings, mailer, kind=kind, key=f"order:{order.id}", to=", ".join(recipients),
                subject=subject, body=body, channel=channel, business_id=business.id, order_id=order.id,
                # a test order that can't go out soon is useless (the next check sends a new one)
                expires_at=utcnow() + timedelta(minutes=30) if is_test else None,
                ref={"audit": {"actor": "system", "action": "order_email", "target": f"order:{order.id}"}})
    session.refresh(order)
    return order


def accept_order_form(session: Session, settings: Settings, mailer: Mailer, *, business: Business, profile: Profile,
                      form: dict[str, str], visitor: str, channel: str = "smtp") -> tuple[int, str]:
    """What the shop's order form does with a POST: (HTTP status, page HTML). The public route and the
    checker's practice test order both come through here, so the test order exercises the real path.

    A POST carrying `lw_test=<nonce>` of an OPEN test ticket for this shop becomes a hidden test order
    (not counted in limits, not in the seller's list). Any other value is ignored."""
    from app import proof
    from app.sites.render import render_site

    token = form.get("order_token", "")
    again = existing_order(session, business, token)
    if again is not None:  # double tap / form sent twice: show the same thank-you, make nothing new
        return 200, render_site(profile, page="thanks", order=order_view(again))
    ticket = proof.open_ticket(session, business, form.get("lw_test", ""))  # the checker's own test order, or None
    shown = {"session": session, "business": business}
    if ticket is None and ful.on_break(profile):  # S15: refused politely here, not only in the page; the checker's test order is not
        audit.record(session, actor="customer", action="order_placed", target=f"business:{business.id}", result="blocked",
                     business_id=business.id, detail="shop is taking a break")
        return 409, render_site(profile, form_error=ful.break_refusal(profile), form_values=form,
                                full_dates=full_days(session, business, profile))
    try:
        data = parse_order_form(form, profile, test=ticket is not None, session=session, business=business)
    except OrderInvalid as e:
        return 422, render_site(profile, form_error=str(e), form_values=form, full_dates=full_days(**shown, profile=profile))
    if ticket is None:
        try:
            check_order_limits(session, settings, business, visitor)
        except TooManyOrders:
            return 429, render_site(profile, form_error=TOO_MANY, form_values=form,
                                    full_dates=full_days(**shown, profile=profile))
        order = place_order(session, mailer, settings, business=business, profile=profile, data=data, visitor=visitor,
                            token=token, channel=channel)
    else:
        # S19B: a monitoring test goes to our check mailbox and has no "Yes, I got it" link (a tap there would
        # claim her inbox got it when it didn't)
        confirm_url = "" if ticket.audience == "check" else proof.issue_confirm_link(session, settings, ticket)
        order = place_order(session, mailer, settings, business=business, profile=profile, data=data, is_test=True,
                            nonce=ticket.nonce, visitor="", token=token, confirm_url=confirm_url, channel=channel,
                            recipients=test_recipients(session, settings, business, ticket.audience))
        proof.ticket_used(session, ticket, order)
    return 200, render_site(profile, page="thanks", order=order_view(order))

