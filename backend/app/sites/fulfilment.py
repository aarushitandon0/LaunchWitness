"""S15: where a shop sells, when, and how the customer pays. One place for every rule, all pure functions of the
Profile (plus a date and, for the daily limit, a count). The order form, the server's order check, the shop page, the
order email, the go-live checklist and the Orders page all ask here, so a rule can't be right in one and wrong in another.

Nothing in here touches the network or the clock by itself: `today` is always passed in (IST by default).
"""

import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# ---------- fixed lists (the Reader / the Review form can only pick from these) ----------

SELLING_MODES = ("pickup", "local", "pickup_local", "india", "pickup_india")
PAYMENT_TERMS = ("upfront", "advance", "on_delivery")
FOOD_MARKS = ("veg", "egg", "nonveg")
FOOD_MARK_WORDS = {"veg": "Veg", "egg": "Contains egg", "nonveg": "Non-veg"}

CANCELLATION_PRESETS = {
    "no_custom": "No cancellations for custom orders.",
    "full_24h": "Cancel up to 24 hours before for a full refund.",
    "advance_kept_48h": "Cancel up to 48 hours before. The advance is not refunded.",
}
CANCELLATION_CHOICES = (*CANCELLATION_PRESETS, "custom")

MAX_DAYS_AHEAD = 120  # a wanted-by date further out than this is refused
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

PIN = re.compile(r"[1-9]\d{5}")
# a locality: letters (any script), digits, spaces and a few marks; 2-40 characters
LOCALITY = re.compile(r"[\w][\w .&'’()/-]{1,39}", re.UNICODE)


def today_ist() -> date:
    return datetime.now(UTC).astimezone(IST).date()


def parse_date(text: str) -> date | None:
    try:
        return date.fromisoformat(text.strip()) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()) else None
    except ValueError:
        return None


def nice_date(d: date) -> str:
    return f"{d.day} {d:%b}"


# ---------- selling mode ----------

def mode_flags(mode: str) -> tuple[bool, bool]:
    """(pickup, delivery-of-either-kind) for a selling mode."""
    return mode.startswith("pickup"), mode.endswith(("local", "india"))


def infer_mode(pickup: bool, delivery: bool) -> str:
    """Older profiles only have the two yes/no boxes: they were local delivery (the only kind there was)."""
    if pickup and delivery:
        return "pickup_local"
    if delivery:
        return "local"
    return "pickup" if pickup else ""


def offers(profile) -> dict[str, bool]:
    mode = profile.selling_mode
    return {"pickup": mode.startswith("pickup"), "local": mode.endswith("local"), "india": mode.endswith("india")}


def mode_words(profile) -> str:
    o = offers(profile)
    parts = ["pickup"] if o["pickup"] else []
    if o["local"]:
        parts.append("local delivery")
    if o["india"]:
        parts.append("shipping across India")
    return " and ".join(parts)


# ---------- delivery areas ----------

@dataclass
class Areas:
    localities: list[str]
    pins: list[str]
    bad: list[str]


def parse_areas(text: str) -> Areas:
    """'Baner, Aundh, 411045' -> localities ['Baner','Aundh'], pins ['411045']. Anything that is neither a 6-digit PIN code
    nor a plain place name (for example a 5-digit number) is returned in `bad`. Lenient: never raises."""
    loc: list[str] = []
    pins: list[str] = []
    bad: list[str] = []
    seen: set[str] = set()
    for tok in re.split(r"[,;\n]+", text or ""):
        tok = " ".join(tok.split())
        if not tok or tok.lower() in seen:
            continue
        seen.add(tok.lower())
        if re.fullmatch(r"\d+", tok):
            (pins if PIN.fullmatch(tok) else bad).append(tok)
        elif LOCALITY.fullmatch(tok) and not re.fullmatch(r"[\d ]+", tok):
            loc.append(tok)
        else:
            bad.append(tok)
    return Areas(loc, pins, bad)


def areas_error(text: str) -> str | None:
    """A plain-English problem with the list she typed, or None. Used when she saves (not when an old profile loads)."""
    a = parse_areas(text)
    if a.bad:
        shown = ", ".join(f"“{b[:20]}”" for b in a.bad[:3])
        return (f"These don't look like a locality or a 6-digit PIN code: {shown}. "
                "Separate places with commas, for example: Baner, Aundh, 411045.")
    if len(a.localities) + len(a.pins) > 40:
        return "Please keep the list to 40 places or fewer."
    return None


def area_phrase(profile) -> str:
    a = parse_areas(profile.delivery_areas)
    items = [*a.localities, *a.pins]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def serves(profile, address: str, pin: str) -> bool:
    """Local delivery: is this PIN, or this address, somewhere she delivers? A listed PIN matches the PIN. A listed
    locality matches when the address names it (whole word, any case). With nothing listed nobody is served."""
    a = parse_areas(profile.delivery_areas)
    if pin in a.pins:
        return True
    low = address.lower()
    return any(re.search(rf"(?<!\w){re.escape(loc.lower())}(?!\w)", low) for loc in a.localities)


# ---------- money ----------

def items_total(items: list[dict]) -> int:
    return sum(int(it["qty"]) * int(it["price_inr"]) for it in items)


def fee_for(profile, fulfilment: str, items_sum: int) -> int:
    """The delivery or shipping charge, from the profile only (never from anything the browser sent)."""
    if fulfilment != "delivery" or items_sum <= 0:
        return 0
    o = offers(profile)
    if o["india"]:
        return profile.shipping_fee_inr
    if o["local"]:
        if profile.free_delivery_above_inr and items_sum >= profile.free_delivery_above_inr:
            return 0
        return profile.delivery_fee_inr
    return 0


def fee_words(profile) -> str:
    """The charge as the customer reads it on the shop."""
    o = offers(profile)
    if o["india"]:
        return f"Shipping {_inr(profile.shipping_fee_inr)}" if profile.shipping_fee_inr else "Free shipping"
    base = f"Delivery {_inr(profile.delivery_fee_inr)}" if profile.delivery_fee_inr else "Free delivery"
    if profile.free_delivery_above_inr and profile.delivery_fee_inr:
        base += f", free above {_inr(profile.free_delivery_above_inr)}"
    return base


def _inr(n: int) -> str:
    from app.sites.render import format_inr

    return format_inr(n)


def pay_split(profile, total: int) -> tuple[int, int]:
    """(pay now, pay later) in whole rupees, from the SERVER's total. Upfront: all now. Advance: N% rounded UP to a
    whole rupee (never 0 for a real total, never more than the total). On delivery / pickup: nothing now."""
    if total <= 0:
        return 0, 0
    if profile.payment_terms == "upfront":
        return total, 0
    if profile.payment_terms == "advance":
        now = min(total, max(1, math.ceil(total * profile.advance_percent / 100)))
        return now, total - now
    return 0, total


def terms_words(profile) -> str:
    """One plain line saying how she is paid, for the shop and the email."""
    if not (profile.upi_id or profile.accepts_cash):
        return ""  # nothing to say about payment until she gives a way to pay
    cash = " Cash is welcome." if profile.accepts_cash else ""
    t = profile.payment_terms
    if t == "upfront":
        return "Please pay the full amount by UPI after you order." + cash
    if t == "advance":
        return f"Please pay {profile.advance_percent}% now by UPI to confirm your order. You pay the rest when you collect or receive it." + cash
    how = "cash or UPI" if profile.accepts_cash and profile.upi_id else "cash" if profile.accepts_cash else "UPI"
    return f"Nothing to pay now. You pay when you collect or receive your order, by {how}."


def payment_label(profile_terms: str, status: str, pay_now: int, pay_later: int, total: int) -> str:
    """What the owner reads next to an order: where the money stands. Derived from the saved terms and her status."""
    if status == "cancelled":
        return "Cancelled"
    if total <= 0 or not profile_terms:  # no terms saved: an order from before S15
        return ""
    if profile_terms == "upfront":
        return "Fully paid" if status in ("paid", "done") else f"Waiting for full payment ({_inr(total)})"
    if profile_terms == "advance":
        if status == "done":
            return "Fully paid"
        if status == "paid":
            return f"Advance paid · {_inr(pay_later)} due on delivery"
        return f"Waiting for the advance ({_inr(pay_now)})"
    return "Paid" if status in ("paid", "done") else f"Due on delivery ({_inr(total)})"


def paid_action_label(profile_terms: str) -> str:
    return {"advance": "Advance received", "upfront": "Payment received"}.get(profile_terms, "Mark paid")


# ---------- UPI link and QR with the right amount ----------

def upi_order_uri(profile, amount: int, ref: str) -> str | None:
    """upi://pay link for an order: the exact whole-rupee amount, and the order ref as the note. None when she has no UPI ID
    or there is nothing to pay now."""
    from urllib.parse import quote, urlencode

    if not profile.upi_id or amount <= 0:
        return None
    q = {"pa": profile.upi_id, "pn": profile.name, "am": f"{int(amount)}.00", "cu": "INR", "tn": f"Order {ref}"}
    return "upi://pay?" + urlencode(q, quote_via=quote, safe="@")


# ---------- taking a break ----------

def on_break(profile, today: date | None = None) -> bool:
    """On a break while the switch is on, unless she gave a return date that is today or already past."""
    if not profile.on_break:
        return False
    back = parse_date(profile.back_on)
    return not (back and back <= (today or today_ist()))


def break_line(profile) -> str:
    back = parse_date(profile.back_on)
    return f"Taking a break, back on {nice_date(back)}" if back else "Taking a break"


def break_refusal(profile) -> str:
    back = parse_date(profile.back_on)
    when = f" We're back on {nice_date(back)}." if back else " Please check back later."
    return f"{profile.name} is taking a break and isn't taking orders right now.{when}"


# ---------- the date rules ----------

def earliest(profile, today: date) -> date:
    return today + timedelta(days=profile.min_notice_days)


def latest(today: date) -> date:
    return today + timedelta(days=MAX_DAYS_AHEAD)


def days_off_words(profile) -> str:
    return ", ".join(WEEKDAYS[d] for d in profile.days_off)


def date_required(profile) -> bool:
    return bool(profile.min_notice_days or profile.days_off or profile.max_orders_per_day)


def date_problem(profile, wanted: date, today: date, taken: int) -> str | None:
    """Why this wanted-by date can't be used, in plain words, or None. `taken` = her orders already on that date."""
    first = earliest(profile, today)
    if wanted < first:
        if profile.min_notice_days:
            n = profile.min_notice_days
            return (f"{profile.name} needs at least {n} day{'s' if n != 1 else ''} to prepare an order. "
                    f"The earliest date you can pick is {nice_date(first)}.")
        return "Please pick today or a later date."
    if wanted > latest(today):
        return f"Please pick a date within the next {MAX_DAYS_AHEAD // 30} months."
    if wanted.weekday() in profile.days_off:
        return f"{profile.name} doesn't deliver or hand over orders on {WEEKDAYS[wanted.weekday()]}s. Please pick another day."
    if profile.max_orders_per_day and taken >= profile.max_orders_per_day:
        return f"{profile.name} is fully booked on {nice_date(wanted)}. Please pick another date."
    return None


def full_dates(counts: dict[str, int], profile) -> list[str]:
    """Dates (ISO) already at her daily limit, for the date picker. No names, no numbers: just which days are full."""
    if not profile.max_orders_per_day:
        return []
    return sorted(d for d, n in counts.items() if n >= profile.max_orders_per_day)


# ---------- cancellation ----------

def cancellation_line(profile) -> str:
    if profile.cancellation_preset == "custom":
        return profile.cancellation_text.strip()
    return CANCELLATION_PRESETS.get(profile.cancellation_preset, "")


# ---------- go-live ----------

def selling_problem(profile) -> str:
    """'' when the selling mode and everything it needs are filled in; else the next thing to do, in plain words."""
    if profile.selling_mode not in SELLING_MODES:
        return "Choose how customers get their order: pickup, local delivery or shipping across India."
    if not profile.city.strip():
        return "Add your city."
    if not profile.area.strip():
        return "Add your area or locality (not your full address)."
    o = offers(profile)
    if o["local"]:
        a = parse_areas(profile.delivery_areas)
        if not (a.localities or a.pins):
            return "Add the localities or PIN codes you deliver to."
        if areas_error(profile.delivery_areas):
            return areas_error(profile.delivery_areas) or ""
    if o["india"] and profile.dispatch_days < 1:
        return "Add how many days you take to dispatch an order."
    return ""
