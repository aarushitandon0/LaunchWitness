"""S19D: the "New" badge on a shop's menu.

An item the seller marks "Show as New" carries a real date, `new_until` = the day it was marked + NEW_BADGE_DAYS
(India time). The badge shows while today <= new_until (so on day 15 after adding it, not on day 16) and then
disappears by itself. The server never stores a date further out than today + NEW_BADGE_DAYS, so the badge can't
be kept up forever, and anything that isn't a plain YYYY-MM-DD date is dropped.
"""

from datetime import date, timedelta

NEW_BADGE_DAYS = 15


def parse(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def clean(value: str, today: date) -> str:
    """What gets saved: "" (not new / expired / not a date) or a date no later than today + NEW_BADGE_DAYS."""
    d = parse(value)
    if d is None or d < today:
        return ""
    return min(d, today + timedelta(days=NEW_BADGE_DAYS)).isoformat()


def is_new(value: str, today: date) -> bool:
    d = parse(value)
    return d is not None and today <= d
