"""Shop themes (S14): a look for each kind of home business. Plain data, no model involved.

One rendering engine (`render.py` + `templates/seller.html`) and one safety layer serve every theme. A theme only
chooses: design tokens (colours with roles, radius), a font pairing, layout variants (hero, menu), the order of the
page's sections and its decorative placeholder art. It can't touch the order form, the basket, the `lw-shop` marker,
the payment / WhatsApp links or the "Report this shop" link: those live outside anything a theme defines (a test
renders every theme and checks they are all still there).

Claude only ever *chooses* a theme key and one of that theme's accent keys (Reader, `theme` / `accent`); the lists
below are the only values accepted. Anything else is replaced by `rule_choice`, a plain keyword rule over the
profile (so it also works when Claude is down and for shops saved before themes existed).

Every accent keeps WCAG AA contrast (4.5:1) for its button text and for use as text on the theme's surfaces;
`tests/test_s14_themes.py` checks every accent and every base text colour.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # no import cycle: the Profile model imports only the key lists from here
    from app.agents.reader import Profile


@dataclass(frozen=True)
class Accent:
    key: str
    label: str
    color: str      # buttons, links, headings accents (text on this colour is `ink`)
    ink: str = "#ffffff"
    tint: str = ""  # soft background that goes with the accent (chips, highlights); text on it is `color`


@dataclass(frozen=True)
class Font:
    family: str            # CSS family name ("LW Fraunces")
    file: str              # woff2 file in app/sites/fonts/
    weight: str = "400"    # "400" or a range "500 800" for variable fonts
    style: str = "normal"


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    blurb: str                 # one plain line for the picker
    for_whom: str              # e.g. "Cakes, cupcakes, brownies, desserts"
    tokens: dict[str, str]     # colour roles + radius (CSS custom properties without the leading --)
    display: tuple[Font, ...]  # headings
    body: Font                 # everything else
    accents: tuple[Accent, ...]
    hero: str                  # layout variant of the top of the page: split | board | centered | ledger | festive
    menu: str                  # list | cards | board | pricelist
    before: tuple[str, ...]    # sections between the hero and the menu: how | occasions
    after: tuple[str, ...]     # sections after the menu: about | testimonials | info
    art: str                   # placeholder art key (templates/seller.html "art" macro)
    display_fallback: str = "Georgia, 'Times New Roman', serif"
    body_fallback: str = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', 'Helvetica Neue', sans-serif"

    @property
    def fonts(self) -> tuple[Font, ...]:
        return (*self.display, self.body)

    def accent(self, key: str = "") -> Accent:
        return next((a for a in self.accents if a.key == key), self.accents[0])


# Text colours are chosen so ink, ink2 and muted pass AA on bg, paper and soft (tested).
BAKERY = Theme(
    key="bakery", label="Bakery & desserts", for_whom="Cakes, cupcakes, brownies, cookies and other sweet things",
    blurb="Warm and soft: cream, blush and cocoa with a playful serif.",
    tokens={"bg": "#fff8f0", "paper": "#ffffff", "ink": "#3a2216", "ink2": "#5e4535", "muted": "#74594a",
            "line": "#f1e2d3", "line2": "#e4cdb8", "soft": "#fde9e3", "radius": "30px", "radius-sm": "16px",
            "art-a": "#f6c9c3", "art-b": "#f3e0c4", "art-c": "#d9976f"},
    display=(Font("LW Fraunces", "fraunces.woff2", "500 800"),), body=Font("LW DM Sans", "dm-sans.woff2", "400 700"),
    accents=(Accent("raspberry", "Raspberry", "#a81f4a", tint="#fbe0e6"),
             Accent("caramel", "Caramel", "#8f4710", tint="#f9e6cf"),
             Accent("pistachio", "Pistachio", "#3d6a2a", tint="#e4f0d8")),
    hero="split", menu="cards", before=(), after=("about", "testimonials", "info"), art="sprinkles",
)

KITCHEN = Theme(
    key="kitchen", label="Home kitchen, tiffin & pickles", for_whom="Tiffin plans, home-cooked meals, snacks, pickles",
    blurb="Homely and bold: turmeric, chilli and leaf green, laid out like a menu board.",
    tokens={"bg": "#fdf4de", "paper": "#fffcf3", "ink": "#2a2016", "ink2": "#4f4132", "muted": "#675645",
            "line": "#ecdcb4", "line2": "#d9c389", "soft": "#f8e3a6", "radius": "16px", "radius-sm": "10px",
            "art-a": "#f1b83a", "art-b": "#d9482b", "art-c": "#4b8a3a"},
    display=(Font("LW Bricolage", "bricolage.woff2", "500 800"),), body=Font("LW Figtree", "figtree.woff2", "400 800"),
    accents=(Accent("turmeric", "Turmeric", "#8f4f00", tint="#fbe7b3"),
             Accent("chilli", "Chilli", "#b0261c", tint="#fbdcd5"),
             Accent("leaf", "Leaf", "#2d6a2f", tint="#dcefd5")),
    hero="board", menu="board", before=(), after=("how", "about", "testimonials", "info"), art="thali",
    display_fallback="'Arial Black', 'Helvetica Neue', Arial, sans-serif",
)

HANDMADE = Theme(
    key="handmade", label="Handmade & crafts", for_whom="Candles, resin, jewellery, home decor and other handmade things",
    blurb="An airy gallery: photo-first, lots of white space, a refined serif.",
    tokens={"bg": "#fbfaf6", "paper": "#ffffff", "ink": "#211e1a", "ink2": "#4a453f", "muted": "#675f56",
            "line": "#ebe6dc", "line2": "#d9d2c4", "soft": "#f1ece2", "radius": "26px", "radius-sm": "14px",
            "art-a": "#e8dccb", "art-b": "#d5c4ab", "art-c": "#b98f6b"},
    display=(Font("LW Instrument Serif", "instrument-serif.woff2"),
             Font("LW Instrument Serif", "instrument-serif-italic.woff2", style="italic")),
    body=Font("LW Manrope", "manrope.woff2", "400 700"),
    accents=(Accent("clay", "Clay", "#8e4527", tint="#f6e3d8"),
             Accent("sage", "Sage", "#3f6150", tint="#e1ece5"),
             Accent("plum", "Plum", "#6c3459", tint="#f0e0ea")),
    hero="centered", menu="cards", before=(), after=("about", "testimonials", "info"), art="wax",
)

TAILOR = Theme(
    key="tailor", label="Tailoring, embroidery & custom work", for_whom="Stitching, alterations, embroidery, made-to-measure",
    blurb="Crafted and precise: linen and navy, prices and the ordering steps up front.",
    tokens={"bg": "#f6f3ec", "paper": "#fffefb", "ink": "#1a2030", "ink2": "#3e4658", "muted": "#566074",
            "line": "#e3ddd0", "line2": "#cdc5b3", "soft": "#ebe6d9", "radius": "10px", "radius-sm": "6px",
            "art-a": "#c9d0e0", "art-b": "#e5decb", "art-c": "#8d98b5"},
    display=(Font("LW Source Serif", "source-serif.woff2", "400 700"),), body=Font("LW Jakarta", "jakarta.woff2", "400 700"),
    accents=(Accent("navy", "Navy", "#243a78", tint="#dde3f4"),
             Accent("thread", "Red thread", "#a1262b", tint="#f6dcdc"),
             Accent("olive", "Olive", "#4f5d1e", tint="#e6ebcf")),
    hero="ledger", menu="pricelist", before=("how",), after=("about", "testimonials", "info"), art="stitch",
)

GIFTS = Theme(
    key="gifts", label="Gifts & hampers", for_whom="Hampers, festive gifts, return gifts, gift boxes",
    blurb="Festive but tasteful: ruby, emerald and a touch of gold, led by occasions.",
    tokens={"bg": "#fff8f3", "paper": "#ffffff", "ink": "#2b1620", "ink2": "#553844", "muted": "#6e4f5b",
            "line": "#f2e1dc", "line2": "#e5c9c1", "soft": "#fbe6e4", "radius": "22px", "radius-sm": "12px",
            "art-a": "#e9b9b6", "art-b": "#e8cf92", "art-c": "#a42a45"},
    display=(Font("LW Playfair", "playfair.woff2", "500 800"),), body=Font("LW Figtree", "figtree.woff2", "400 800"),
    accents=(Accent("ruby", "Ruby", "#9a1b3a", tint="#f8dfe5"),
             Accent("emerald", "Emerald", "#1b6552", tint="#d9eee7"),
             Accent("gold", "Antique gold", "#7d5400", tint="#f6e8c3")),
    hero="festive", menu="cards", before=("occasions",), after=("about", "testimonials", "info"), art="ribbon",
)

GENERAL = Theme(
    key="general", label="General", for_whom="Anything else a home business sells",
    blurb="Clean and calm: a neutral look that suits any shop.",
    tokens={"bg": "#f8f7f4", "paper": "#ffffff", "ink": "#1c1d1f", "ink2": "#46484d", "muted": "#5f6269",
            "line": "#e8e6e0", "line2": "#d6d3ca", "soft": "#eeece6", "radius": "22px", "radius-sm": "12px",
            "art-a": "#dcd9cf", "art-b": "#e9e6dd", "art-c": "#a7a395"},
    display=(Font("LW Newsreader", "newsreader.woff2", "400 700"),), body=Font("LW Manrope", "manrope.woff2", "400 700"),
    accents=(Accent("indigo", "Indigo", "#2f4aa6", tint="#e0e6f7"),
             Accent("forest", "Forest", "#1f6444", tint="#d9eee3"),
             Accent("ink", "Ink", "#2b2f3a", tint="#e4e5ea")),
    hero="split", menu="list", before=(), after=("about", "testimonials", "info"), art="soft",
)

THEMES: dict[str, Theme] = {t.key: t for t in (BAKERY, KITCHEN, HANDMADE, TAILOR, GIFTS, GENERAL)}
THEME_KEYS: tuple[str, ...] = tuple(THEMES)
ACCENT_KEYS: tuple[str, ...] = tuple(dict.fromkeys(a.key for t in THEMES.values() for a in t.accents))
FALLBACK = "general"


def clean_theme_key(value: object) -> str:
    """A key from the allowed list, or "" (= "use the rule-based choice"). Never raises."""
    v = value.strip().lower() if isinstance(value, str) else ""
    return v if v in THEMES else ""


def clean_accent_key(theme_key: str, value: object) -> str:
    """An accent key valid for that theme, or "" (= the theme's first accent)."""
    v = value.strip().lower() if isinstance(value, str) else ""
    theme = THEMES.get(theme_key)
    return v if theme and any(a.key == v for a in theme.accents) else ""


# ---------- The rule-based choice (no model) ----------

# Word starts, matched at word boundaries. Order matters only for ties (see `rule_choice`).
KEYWORDS: dict[str, tuple[str, ...]] = {
    "bakery": ("cake", "bake", "baker", "cupcake", "brownie", "cookie", "dessert", "pastry", "pastries", "macaron",
               "muffin", "donut", "doughnut", "bread", "pie", "tart", "cheesecake", "chocolate", "fondant", "eggless",
               "sweet", "mithai", "ice cream", "bakes"),
    "kitchen": ("tiffin", "thali", "meal", "lunch", "dinner", "pickle", "achar", "snack", "namkeen", "chaat", "curry",
                "roti", "paratha", "dabba", "home-cooked", "home cooked", "homemade food", "masala", "chutney", "sabzi",
                "khichdi", "biryani", "samosa", "chai", "papad", "ladoo", "laddu", "kitchen", "cook", "catering", "monthly plan", "weekly plan"),
    "handmade": ("candle", "resin", "jewel", "earring", "necklace", "bracelet", "crochet", "macrame", "pottery",
                 "ceramic", "decor", "soap", "wax", "handmade", "handcrafted", "hand-poured", "hand poured", "painting",
                 "planter", "art ", "craft", "knit", "terracotta", "diya", "hand-painted", "hand painted"),
    "tailor": ("tailor", "stitch", "blouse", "embroider", "alteration", "fall and pico", "kurta", "lehenga", "sewing",
               "hemming", "boutique", "made-to-measure", "made to measure", "custom", "saree", "salwar", "dress",
               "garment", "zari", "aari", "applique"),
    "gifts": ("hamper", "gift", "bouquet", "return gift", "festive", "diwali", "rakhi", "wedding favour", "gifting",
              "box", "celebration"),
}
NICHE_DEFAULT = {"food": "kitchen", "handmade": "handmade", "custom": "tailor"}
TIE_ORDER = ("bakery", "kitchen", "handmade", "tailor", "gifts")


def _score(text: str, words: tuple[str, ...]) -> int:
    t = text.lower()
    return sum(1 for w in words if re.search(r"(?<![a-z])" + re.escape(w), t))


def rule_choice(profile: "Profile") -> str:
    """Plain-code theme from what the seller told us: the Reader's niche plus a keyword count over the name, tagline,
    category names and item names (weighted) and the about text. Always returns a valid theme key."""
    heavy = f"{profile.name} {profile.tagline} {profile.selling_point}"
    cats = " ".join(p.category for p in profile.products)
    items = " ".join(p.name for p in profile.products)
    scores = {}
    for key in TIE_ORDER:
        words = KEYWORDS[key]
        scores[key] = 3 * _score(heavy, words) + 2 * _score(cats, words) + _score(items, words) + _score(profile.about, words)
    best = max(TIE_ORDER, key=lambda k: (scores[k], -TIE_ORDER.index(k)))
    if scores[best] > 0:
        return best
    return NICHE_DEFAULT.get(profile.niche, FALLBACK)


def resolve(profile: "Profile") -> tuple[Theme, Accent]:
    """The theme and accent a shop is drawn with: the profile's own valid choice, else the rule-based one."""
    theme = THEMES.get(clean_theme_key(profile.theme)) or THEMES[rule_choice(profile)]
    return theme, theme.accent(clean_accent_key(theme.key, profile.accent))


# ---------- Contrast (WCAG 2.x), used by the tests and the picker ----------

def _lin(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@dataclass
class ThemeCss:
    """What `render.py` puts in the page for a theme: custom properties and @font-face rules."""

    root: str = ""
    faces: str = field(default="")


def css_for(theme: Theme, accent: Accent, font_base: str = "/shop-assets/fonts/") -> ThemeCss:
    t = theme.tokens
    pairs = {**t, "accent": accent.color, "accent-ink": accent.ink, "accent-tint": accent.tint or t["soft"],
             "display": ", ".join([*{f"'{f.family}'" for f in theme.display}, theme.display_fallback]),
             "sans": f"'{theme.body.family}', {theme.body_fallback}"}
    root = ":root{" + ";".join(f"--{k}:{v}" for k, v in pairs.items()) + "}"
    faces = "".join(
        f"@font-face{{font-family:'{f.family}';src:url({font_base}{f.file}) format('woff2');font-weight:{f.weight};"
        f"font-style:{f.style};font-display:swap}}" for f in theme.fonts)
    return ThemeCss(root=root, faces=faces)


def catalog() -> list[dict]:
    """Everything the review page's picker needs (public: it is the same data the shop pages already carry)."""
    return [{"key": t.key, "label": t.label, "blurb": t.blurb, "for_whom": t.for_whom, "hero": t.hero, "menu": t.menu,
             "tokens": {k: t.tokens[k] for k in ("bg", "paper", "ink", "ink2", "soft", "line", "radius")},
             "display": t.display[0].family, "body": t.body.family, "art": t.art,
             "accents": [{"key": a.key, "label": a.label, "color": a.color, "ink": a.ink, "tint": a.tint or t.tokens["soft"]}
                         for a in t.accents]} for t in THEMES.values()]
