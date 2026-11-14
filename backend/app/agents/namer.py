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
SYSTEM = """Suggest website names (domain names) for a small Indian business.
Give 5 different names, each one twice: once ending in .in and once in .com (10 in total, best first).
Each name: 4-15 letters before the ending, easy to say and spell over the phone, lowercase letters only
(no hyphens, no digits, no doubled letters across a word join), clearly about this business: its name,
the owner's name, the area or what they sell. No made-up spellings.
Return ONLY JSON: {"names": ["example.in", "example.com", ...]}"""


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


def namer_user(profile: Profile) -> str:
    return f"Business: {profile.name}\nWhat they sell: {profile.tagline}\nArea: {profile.area}"


def suggest_names(claude: Claude, profile: Profile, *, fixture: str) -> list[str]:
    user = namer_user(profile)
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
    """Cheapest, then shortest. The shortlist always shows a .in and a .com when one of each is available."""
    ok = sorted((q for q in quotes if q.available and q.price_usd is not None),
                key=lambda q: (q.price_usd, len(q.domain), q.domain))
    picked = ok[:top]
    for ending in (".in", ".com"):
        if top >= 2 and not any(q.domain.endswith(ending) for q in picked):
            best = next((q for q in ok if q.domain.endswith(ending)), None)
            if best is not None:
                keep = [q for q in picked if not q.domain.endswith(".in" if ending == ".com" else ".com")]
                drop = (keep or picked)[-1]
                picked = [q for q in picked if q is not drop] + [best]
    return sorted(picked, key=lambda q: (q.price_usd, len(q.domain), q.domain))


def find_names(claude: Claude, availability: AvailabilityChecker, profile: Profile, *, fixture: str) -> list[Quote]:
    names = suggest_names(claude, profile, fixture=fixture)
    return rank(availability.check(names))
