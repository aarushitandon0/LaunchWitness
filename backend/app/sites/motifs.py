"""S20 Part B: each shop's own signature. A motif (what the little drawings in the hero are) and an arrangement (where
they sit and how they move), chosen by CODE from fixed lists, seeded from the shop's name so it is stable.

Keys only. A seller may pick another key on Review (validated against these lists, audited). Claude is never asked.
The drawings are made here from numbers only: no seller text ever reaches the SVG. They are decoration (aria-hidden),
drawn in the accent colour at low opacity, and moved with transform only (see templates/css/base.css, `.motif`).
"""

import hashlib
import math

from markupsafe import Markup

# Three motifs per theme (the first is only a default for the picker's order; the seed picks the shop's own).
MOTIFS: dict[str, tuple[str, ...]] = {
    "bakery": ("sprinkles", "piping", "cherries"),
    "kitchen": ("leaves", "spices", "steam"),
    "handmade": ("threads", "dots", "brush"),
    "tailor": ("stitches", "buttons", "chalk"),
    "gifts": ("ribbons", "confetti", "stars"),
    "general": ("waves", "grid", "sparks"),
}
LABELS = {"sprinkles": "Sprinkles", "piping": "Piping", "cherries": "Cherries", "leaves": "Leaves", "spices": "Spices",
          "steam": "Steam", "threads": "Threads", "dots": "Dots", "brush": "Brush strokes", "stitches": "Stitches",
          "buttons": "Buttons", "chalk": "Chalk lines", "ribbons": "Ribbons", "confetti": "Confetti", "stars": "Stars",
          "waves": "Waves", "grid": "Grid", "sparks": "Sparks"}
# Arrangements: where the drawings sit in the hero, and the slow movement that goes with it.
ARRANGEMENTS: tuple[str, ...] = ("scatter", "corner", "band")
ARRANGEMENT_LABELS = {"scatter": "Scattered", "corner": "Top corner", "band": "Along the bottom"}
MOTION = {"scatter": "drift", "corner": "sway", "band": "bob"}  # CSS keyframes in base.css (transform only)
ALL_MOTIFS = tuple(m for ms in MOTIFS.values() for m in ms)


def clean_motif(theme_key: str, value: object) -> str:
    """A motif key valid for that theme, or "" (= chosen from the shop's name). Never raises."""
    v = value.strip().lower() if isinstance(value, str) else ""
    if theme_key in MOTIFS:
        return v if v in MOTIFS[theme_key] else ""
    return v if v in ALL_MOTIFS else ""


def clean_arrangement(value: object) -> str:
    v = value.strip().lower() if isinstance(value, str) else ""
    return v if v in ARRANGEMENTS else ""


def seed_of(name: str) -> int:
    return int.from_bytes(hashlib.sha256(name.strip().lower().encode("utf-8")).digest()[:8], "big")


def signature(theme_key: str, name: str, motif: str = "", art: str = "") -> tuple[str, str]:
    """(motif, arrangement): her own valid choice, else picked from the name's seed. Always valid."""
    seed = seed_of(name)
    motifs = MOTIFS.get(theme_key, MOTIFS["general"])
    return (clean_motif(theme_key, motif) or motifs[seed % 3],
            clean_arrangement(art) or ARRANGEMENTS[(seed >> 8) % 3])


class _Rng:
    """A tiny deterministic generator (same name -> same drawing, on every machine and every run)."""

    def __init__(self, seed: int):
        self.s = seed % (2**31 - 1) or 1

    def next(self) -> float:
        self.s = (self.s * 48271) % (2**31 - 1)
        return self.s / (2**31 - 1)

    def between(self, a: float, b: float) -> float:
        return a + (b - a) * self.next()


def _f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _star(points: int, r1: float, r2: float) -> str:
    pts = []
    for i in range(points * 2):
        r = r1 if i % 2 == 0 else r2
        a = math.pi * i / points - math.pi / 2
        pts.append(f"{_f(r * math.cos(a))},{_f(r * math.sin(a))}")
    return "M" + "L".join(pts) + "Z"


# Each drawing is made around (0,0), about 24 units across. `k` = a number 0..1 for small variations.
def _shape(motif: str, k: float) -> str:
    if motif == "sprinkles":
        return '<rect x="-9" y="-3" width="18" height="6" rx="3"/>'
    if motif == "piping":
        return '<path d="M-14 6c5-12 9 12 14 0s9 12 14 0" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>'
    if motif == "cherries":
        return ('<circle cx="-6" cy="6" r="6"/><circle cx="7" cy="8" r="6"/>'
                '<path d="M-6 0C-4-10 2-14 8-14M7 2C7-6 8-10 8-14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>')
    if motif == "leaves":
        return '<path d="M0 12C-14 4-12-10 0-14 12-10 14 4 0 12Z"/><path d="M0 12V-8" stroke="#fff" stroke-opacity=".6" stroke-width="1.5" fill="none"/>'
    if motif == "spices":
        return f'<path d="{_star(8, 12, 5)}"/><circle r="2.5" fill="#fff" fill-opacity=".6"/>'
    if motif == "steam":
        return '<path d="M0 14C-8 6 8 2 0-6S8-14 0-20" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round"/>'
    if motif == "threads":
        return '<path d="M-16 8C-6-14 6 14 16-8" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>'
    if motif == "dots":
        r = 3 + 6 * k
        return f'<circle r="{_f(r)}"/>'
    if motif == "brush":
        return '<path d="M-16 4C-8-6 4 8 16-4" fill="none" stroke="currentColor" stroke-width="7" stroke-linecap="round"/>'
    if motif == "stitches":
        return '<path d="M-14 0H14" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-dasharray="6 5"/>'
    if motif == "buttons":
        return ('<path fill-rule="evenodd" d="M0-12a12 12 0 1 1 0 24 12 12 0 1 1 0-24ZM-4-4a1.8 1.8 0 1 0 0 .01ZM4-4a1.8 1.8 0 1 0 0 '
                '.01ZM-4 4a1.8 1.8 0 1 0 0 .01ZM4 4a1.8 1.8 0 1 0 0 .01Z"/>')
    if motif == "chalk":
        return '<path d="M-18 0H18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-dasharray="14 3 4 3"/>'
    if motif == "ribbons":
        return '<path d="M-16 0C-8-12 0 12 8 0S16-8 20 0" fill="none" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>'
    if motif == "confetti":
        return '<rect x="-5" y="-3" width="10" height="6" rx="1"/>' if k < 0.5 else '<path d="M0-7L7 5H-7Z"/>'
    if motif == "stars":
        return f'<path d="{_star(5, 11, 4.6)}"/>'
    if motif == "waves":
        return '<path d="M-18 0c4.5-8 9-8 13.5 0s9 8 13.5 0 9-8 13.5 0" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>'
    if motif == "grid":
        return '<path d="M-8 0H8M0-8V8" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>'
    if motif == "sparks":
        return '<path d="M0-12C1-4 4-1 12 0 4 1 1 4 0 12-1 4-4 1-12 0-4-1-1-4 0-12Z"/>'
    return ""


COLS, ROWS = 6, 4


def _cells(arrangement: str, rng: _Rng) -> list[tuple[int, int]]:
    cells = []
    for r in range(ROWS):
        for c in range(COLS):
            if arrangement == "corner":
                keep = 0.9 if (c >= COLS - 3 and r <= 1) else 0.12
            elif arrangement == "band":
                keep = 0.85 if r == ROWS - 1 else 0.3 if r == ROWS - 2 else 0.05
            else:
                keep = 0.5
            if rng.next() < keep:
                cells.append((c, r))
    return cells or [(COLS // 2, ROWS // 2)]


def svg_for(motif: str, arrangement: str, name: str, *, classes: str = "motif") -> Markup:
    """The hero layer: an aria-hidden SVG of about a dozen small drawings placed on a loose grid. Numbers only."""
    rng = _Rng(seed_of(f"{name}|{motif}|{arrangement}"))
    parts = []
    for c, r in _cells(arrangement, rng):
        x = (c + 0.5) * 400 / COLS + rng.between(-14, 14)
        y = (r + 0.5) * 300 / ROWS + rng.between(-12, 12)
        rot, scale, k = rng.between(-40, 40), rng.between(0.8, 1.5), rng.next()
        op = _f(0.4 + 0.4 * rng.next())  # at most .8: with the layer's opacity the strongest pixel is under 10% accent
        parts.append(f'<g transform="translate({_f(x)} {_f(y)}) rotate({_f(rot)}) scale({_f(scale)})" opacity="{op}">'
                     f'{_shape(motif, k)}</g>')
    return Markup(f'<svg class="{classes}" viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true" '
                  f'focusable="false" fill="currentColor">{"".join(parts)}</svg>')


BAND_ITEMS = 16


def band_svg(motif: str, name: str) -> Markup:
    """S20B: the shop's signature as a decorative strip under the hero, where no text ever sits, so it can be clearly
    visible (see `.motif-band` in css/fx.css). One row of the shop's own drawings, seeded from its name. Numbers only."""
    rng = _Rng(seed_of(f"{name}|{motif}|band-strip"))
    parts = []
    for i in range(BAND_ITEMS):
        x = (i + 0.5) * 960 / BAND_ITEMS + rng.between(-8, 8)
        y = 36 + rng.between(-9, 9)
        rot, scale, k = rng.between(-35, 35), rng.between(1.0, 1.3), rng.next()
        op = _f(0.85 + 0.15 * rng.next())  # with the strip at .3: about .26 to .30 of the accent colour
        parts.append(f'<g transform="translate({_f(x)} {_f(y)}) rotate({_f(rot)}) scale({_f(scale)})" opacity="{op}">'
                     f'{_shape(motif, k)}</g>')
    return Markup('<svg class="band" viewBox="0 0 960 72" preserveAspectRatio="xMidYMid slice" aria-hidden="true" '
                  f'focusable="false" fill="currentColor">{"".join(parts)}</svg>')


def thumbnails(theme_key: str, name: str, arrangement: str) -> list[dict]:
    """For the look picker: each of the theme's motifs drawn small, with this shop's own name as the seed."""
    return [{"key": m, "label": LABELS[m], "svg": str(svg_for(m, arrangement, name, classes="motif-thumb"))}
            for m in MOTIFS.get(theme_key, MOTIFS["general"])]


def arrangement_thumbnails(motif: str, name: str) -> list[dict]:
    return [{"key": a, "label": ARRANGEMENT_LABELS[a], "svg": str(svg_for(motif, a, name, classes="motif-thumb"))}
            for a in ARRANGEMENTS]
