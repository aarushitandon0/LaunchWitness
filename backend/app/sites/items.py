"""S21: how each item is sold. Sizes / packs with their own prices (options), a unit ("per piece"), a minimum and
maximum quantity, one required pick with no price change (a choice, e.g. a colour), extra notice for one item, and the
owner's "Sold out today" switch.

The Reader may suggest these keys (only from the seller's own words); code validates every one (reader.Product) and
draws them (templates/seller.html). The order form posts `qty_<i>` for a plain item and `qty_<i>_<j>` for option j of
item i; totals always come from the menu (orders.parse_order_form).

`group_sizes` is plain code: items whose names differ only by a size / weight / pack suffix and share a category become
ONE item with options. It runs on every Reader reply (reader.tidy_profile), so it needs no Claude.
"""

import re

MAX_OPTIONS = 8
MAX_CHOICES = 8
OPTION_LABEL_MAX = 40
CHOICE_MAX = 30
CHOICE_LABEL_MAX = 30
MAX_MIN_QTY = 100
MAX_NOTICE_DAYS = 30
DEFAULT_CAP = 50  # orders.MAX_QTY: the most of one line a customer may order when the item sets no maximum

OPTION_KINDS = ("size", "weight", "pack", "count", "other")
KIND_WORDS = {"": "Options", "size": "Size", "weight": "Weight", "pack": "Pack", "count": "How many", "other": "Options"}
UNITS = ("piece", "box", "kg", "g", "dozen", "set", "bunch", "metre")
UNIT_WORDS = {"piece": "per piece", "box": "per box", "kg": "per kg", "g": "per gram", "dozen": "per dozen",
              "set": "per set", "bunch": "per bunch", "metre": "per metre"}


def clean_key(v: object, allowed: tuple[str, ...]) -> str:
    v = v.strip().lower() if isinstance(v, str) else ""
    return v if v in allowed else ""


def int_in(v: object, lo: int, hi: int, default: int) -> int:
    """A whole number inside [lo, hi], else the default (bad values never fail a whole profile)."""
    if isinstance(v, bool):
        return default
    if isinstance(v, str) and re.fullmatch(r"\s*\d{1,6}\s*", v):
        v = int(v)
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return v if isinstance(v, int) and lo <= v <= hi else default


def cap(item) -> int:
    """The most of this item one order may hold (all its options together)."""
    return item.max_qty or max(DEFAULT_CAP, item.min_qty)


def kind_word(item) -> str:
    return KIND_WORDS.get(item.option_kind, "Options")


def unit_word(item) -> str:
    return UNIT_WORDS.get(item.unit, "")


def choice_word(item) -> str:
    return item.choice_label or "Choice"


def notice_words(days: int) -> str:
    return f"Order {days} day{'s' if days != 1 else ''} ahead" if days else ""


def line_label(it: dict) -> str:
    """One order line as people read it: "Chocolate truffle cake · 1 kg · Chocolate"."""
    return " · ".join(x for x in (it.get("name", ""), it.get("option_label", ""), it.get("choice", "")) if x)


# ---------- code-side grouping of sizes (no Claude) ----------

_NUM = r"(?:\d+\s*(?:½|¼|¾)|½|¼|¾|\d+\s+\d/\d|\d+/\d+|\d+(?:\.\d+)?)"
_WEIGHT_UNIT = r"(?:kgs?|kilos?|g|gm|gms|grams?|ml|l|ltr|litres?|liters?)"
_WEIGHT = rf"{_NUM}\s*{_WEIGHT_UNIT}"
_PACK = r"(?:(?:box|pack|set|tin|jar|tray)\s+of\s+\d{1,3}|\d{1,3}\s*(?:pcs|pc|pieces?|nos))"
_SUFFIX = re.compile(rf"^(?P<base>.*?\S)\s*(?:[-–—,:]\s*)?(?:\(\s*(?P<p>{_WEIGHT}|{_PACK})\s*\)|(?P<b>{_WEIGHT}|{_PACK}))\s*$", re.I)
_FRACTION_TEXT = {"1/2": "½", "1/4": "¼", "3/4": "¾"}
_UNIT_NORMAL = {"kg": "kg", "kgs": "kg", "kilo": "kg", "kilos": "kg", "g": "g", "gm": "g", "gms": "g", "gram": "g",
                "grams": "g", "ml": "ml", "l": "litre", "ltr": "litre", "litre": "litre", "litres": "litre",
                "liter": "litre", "liters": "litre"}


def split_size(name: str) -> tuple[str, str, str] | None:
    """("Chocolate truffle cake", "½ kg", "weight") from "Chocolate truffle cake 1/2 kg"; None without a size suffix.
    The base must keep at least one real word, so "1 kg" alone is not split."""
    m = _SUFFIX.match(name.strip())
    if not m:
        return None
    base = m.group("base").strip(" -–—,:(")
    raw = (m.group("p") or m.group("b") or "").strip()
    if not re.search(r"[A-Za-zऀ-ॿ]{2,}", base):
        return None
    w = re.fullmatch(rf"({_NUM})\s*({_WEIGHT_UNIT})", raw, re.I)
    if w:
        num = " ".join(w.group(1).split())
        num = re.sub(r"^(\d+)\s+(\d/\d)$", lambda x: x.group(1) + _FRACTION_TEXT.get(x.group(2), " " + x.group(2)), num)
        num = _FRACTION_TEXT.get(num, num).replace(" ", "")
        return base, f"{num} {_UNIT_NORMAL[w.group(2).lower()]}", "weight"
    label = " ".join(raw.split())
    label = re.sub(r"^(\d{1,3})\s*(pcs|pc|nos)$", r"\1 pcs", label, flags=re.I)
    return base, label[:1].upper() + label[1:].lower(), "pack"


def group_sizes(products: list) -> list:
    """Merge "X ½ kg" + "X 1 kg" (same category) into one item "X" with options ½ kg / 1 kg. Only when at least two
    items share the base name; never when it would mix different things (another category, a "from" price, an extra,
    another food mark, an item that already has options, or two sizes with the same label). The merged item takes the
    place of the first one; the others keep their order."""
    groups: dict[tuple[str, str], list[int]] = {}
    split: dict[int, tuple[str, str, str]] = {}
    for i, p in enumerate(products):
        if p.addon or p.options or p.price_from or p.price_inr <= 0:
            continue
        s = split_size(p.name)
        if s is None:
            continue
        split[i] = s
        groups.setdefault((" ".join(s[0].lower().split()), p.category.strip().lower()), []).append(i)
    merged_into: dict[int, object] = {}
    dropped: set[int] = set()
    for members in groups.values():
        if not 2 <= len(members) <= MAX_OPTIONS:
            continue
        items = [products[i] for i in members]
        labels = [split[i][1] for i in members]
        if len({x.lower() for x in labels}) != len(labels) or len({x.food_mark for x in items}) != 1:
            continue
        first = items[0]
        kinds = {split[i][2] for i in members}
        merged_into[members[0]] = type(first).model_validate({
            **first.model_dump(),
            "name": split[members[0]][0],
            "options": [{"label": lab, "price_inr": it.price_inr} for lab, it in zip(labels, items, strict=True)],
            "option_kind": kinds.pop() if len(kinds) == 1 else "size",
            "price_inr": min(it.price_inr for it in items),
            "description": first.description,
        })
        dropped.update(members[1:])
    if not merged_into:
        return list(products)
    out = []
    for i, p in enumerate(products):
        if i in dropped:
            continue
        out.append(merged_into.get(i, p))
    return out


def notes(item, shop_notice: int = 0) -> list[str]:
    """Short facts under an item's name, only from its own fields: "Min 5", "Max 10", "Order 7 days ahead" (only when
    it needs more notice than the shop's own, which the page already says)."""
    out = []
    if item.min_qty > 1:
        out.append(f"Min {item.min_qty}")
    if item.max_qty:
        out.append(f"Max {item.max_qty}")
    if item.notice_days > shop_notice:
        out.append(notice_words(item.notice_days))
    return out


def longest_notice(products, shop_notice: int = 0) -> int:
    """The most notice any item that can be ordered today needs beyond the shop's own (0 = none)."""
    days = max((p.notice_days for p in products if not p.sold_out), default=0)
    return days if days > shop_notice else 0
