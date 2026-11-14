"""Namer: Claude (cheap model) suggests ~10 domain names; code checks which are
really available and at what price, and returns the best 3."""

import re

from app.agents.claude_client import Claude, ClaudeBadJson
from app.agents.reader import Profile, fixture_for
from app.godaddy.availability import AvailabilityChecker, Quote

DOMAIN = re.compile(r"^(?=.{4,63}$)[a-z0-9]([a-z0-9-]{0,50}[a-z0-9])?\.(in|co\.in|com|shop|store|online)$")
NAMES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["names"],
    "properties": {"names": {"type": "array", "items": {"type": "string"}}},
}
SYSTEM = """Suggest 10 website names (domain names) for a small Indian business.
Rules: short, easy to say and spell over the phone, lowercase letters and digits only (hyphen only if needed),
based on the business name, owner name, area or what they sell. Prefer .in, then .com, .co.in, .shop, .store.
Return ONLY JSON: {"names": ["example.in", ...]}"""


class NamerError(RuntimeError):
    pass


def namer_fixture(description: str) -> str:
    return fixture_for(description).replace("reader_", "namer_", 1)


def clean_names(raw: list) -> list[str]:
    out: list[str] = []
    for n in raw:
        if not isinstance(n, str):
            continue
        d = n.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/.")
        if DOMAIN.match(d) and d not in out:
            out.append(d)
    return out[:10]


def suggest_names(claude: Claude, profile: Profile, *, fixture: str) -> list[str]:
    user = f"Business: {profile.name}\nWhat they sell: {profile.tagline}\nArea: {profile.area}"
    for _ in range(2):  # one retry on bad JSON
        try:
            data = claude.ask_json(fixture=fixture, tier="cheap", system=SYSTEM, user=user, schema=NAMES_SCHEMA,
                                   max_tokens=300)
        except ClaudeBadJson:
            continue
        names = clean_names(data.get("names", []))
        if names:
            return names
    raise NamerError("Sorry, we couldn't come up with names this time. Please try again.")


def rank(quotes: list[Quote], top: int = 3) -> list[Quote]:
    ok = [q for q in quotes if q.available and q.price_usd is not None]
    return sorted(ok, key=lambda q: (q.price_usd, len(q.domain), q.domain))[:top]


def find_names(claude: Claude, availability: AvailabilityChecker, profile: Profile, *, fixture: str) -> list[Quote]:
    names = suggest_names(claude, profile, fixture=fixture)
    return rank(availability.check(names))
