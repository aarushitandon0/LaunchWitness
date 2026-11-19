"""S19D: customers only ever see a live shop's last CONFIRMED WhatsApp number and UPI ID/name.

When the owner of a real, live shop changes her WhatsApp number or UPI details, her confirmation is reset (as before)
and the old, confirmed values are kept here. Every customer-facing page (shop, order form, thank-you and status
pages, UPI links and QR) is drawn from `public_profile`, so the new values reach customers only once she confirms
them. Removing a value (making it empty) takes effect at once: there is nothing to confirm, and nobody is sent to it.
"""

import json

from app.agents.reader import Profile
from app.models import Business

WA = "whatsapp"
UPI = "upi"


def held(b: Business) -> dict:
    try:
        data = json.loads(b.live_contact_json or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def is_real_live(b: Business) -> bool:
    return b.status == "live" and not b.practice


def keep_confirmed(b: Business, old: Profile, new: Profile) -> list[str]:
    """Before an edit is saved: keep the confirmed values the edit replaces. Returns what now waits for her ("whatsapp",
    "upi"). Call BEFORE `reset_confirmations` (which clears the confirmed copies)."""
    from app import golive

    data = held(b)
    if is_real_live(b):
        if WA not in data and b.wa_confirmed and b.wa_confirmed == old.whatsapp and new.whatsapp and new.whatsapp != old.whatsapp:
            data[WA] = {"whatsapp": old.whatsapp}
        if (UPI not in data and b.upi_confirmed and b.upi_confirmed == golive.upi_key(old) and new.upi_id
                and new.upi_display_name.strip() and golive.upi_key(new) != golive.upi_key(old)):
            data[UPI] = {"upi_id": old.upi_id, "upi_display_name": old.upi_display_name}
    if not new.whatsapp:
        data.pop(WA, None)  # removed: takes effect at once
    if not (new.upi_id and new.upi_display_name.strip()):
        data.pop(UPI, None)
    b.live_contact_json = json.dumps(data, sort_keys=True)
    return sorted(data)


def confirmed(b: Business, what: str) -> None:
    """She confirmed the new value: customers see it from now on."""
    data = held(b)
    if data.pop(what, None) is not None:
        b.live_contact_json = json.dumps(data, sort_keys=True)


def waiting(b: Business) -> list[str]:
    """What the owner still has to confirm before customers see it ("whatsapp", "upi")."""
    return sorted(k for k in held(b) if k in (WA, UPI)) if is_real_live(b) else []


def public_profile(b: Business) -> Profile:
    """The profile customers see: her saved profile with any not-yet-confirmed WhatsApp / UPI swapped for the last
    confirmed ones."""
    p = Profile.model_validate_json(b.profile_json)
    data = held(b) if is_real_live(b) else {}
    if isinstance(data.get(WA), dict):
        p.whatsapp = str(data[WA].get("whatsapp", p.whatsapp))
    if isinstance(data.get(UPI), dict):
        p.upi_id = str(data[UPI].get("upi_id", p.upi_id))
        p.upi_display_name = str(data[UPI].get("upi_display_name", p.upi_display_name))
    return p
