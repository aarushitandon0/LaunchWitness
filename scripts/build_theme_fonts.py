"""Build the shop themes' self-hosted fonts (S14): open-licensed (SIL OFL 1.1) TTFs -> small Latin + ₹ woff2 files.

Not part of the app or the tests: run it only to rebuild `backend/app/sites/fonts/*.woff2`.
Needs `pip install fonttools brotli` (in a scratch venv, not the project's) and a folder with the source TTFs
downloaded from https://github.com/google/fonts/tree/main/ofl (names in SOURCES below, see docs/FONTS.md).

    python scripts/build_theme_fonts.py <folder with the .ttf files> backend/app/sites/fonts

Variable fonts are narrowed (one optical size, the weights the shop pages use), then everything is cut down to
Basic Latin, Latin-1, common punctuation, arrows and the rupee sign (U+20B9). Hinting is dropped.
"""

import io
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D,
            0x2022, 0x2026, 0x2032, 0x2033, 0x20B9, 0x2190, 0x2192, 0x2212, 0x00D7, 0x2715, 0x2713])
# output name -> (source file, axis limits to keep). A number pins the axis; (lo, hi) keeps a range.
SOURCES = {
    "fraunces": ("fraunces.ttf", {"SOFT": 100, "WONK": 1, "opsz": 48, "wght": (500, 800)}),
    "dm-sans": ("dmsans.ttf", {"opsz": 14, "wght": (400, 700)}),
    "bricolage": ("bricolage.ttf", {"opsz": 36, "wdth": 100, "wght": (500, 800)}),
    "figtree": ("figtree.ttf", {"wght": (400, 800)}),
    "instrument-serif": ("instrument.ttf", None),
    "instrument-serif-italic": ("instrument-italic.ttf", None),
    "source-serif": ("sourceserif.ttf", {"opsz": 36, "wght": (400, 700)}),
    "jakarta": ("jakarta.ttf", {"wght": (400, 700)}),
    "playfair": ("playfair.ttf", {"wght": (500, 800)}),
    "newsreader": ("newsreader.ttf", {"opsz": 36, "wght": (400, 700)}),
    "manrope": ("manrope.ttf", {"wght": (400, 700)}),
}


def build(src: Path, limits: dict | None, out: Path) -> int:
    font = TTFont(src)
    if limits:
        font = instancer.instantiateVariableFont(font, limits)
        buf = io.BytesIO()
        font.save(buf)  # reload: the subsetter wants fully-read tables
        buf.seek(0)
        font = TTFont(buf)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "tnum", "lnum", "case", "ccmp", "locl", "mark", "mkmk", "calt"]
    opts.hinting = False
    opts.notdef_outline = True
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]  # keep copyright + licence strings
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(out)
    return out.stat().st_size


def main(args: list[str]) -> int:
    if len(args) != 2:
        print(__doc__)
        return 2
    src_dir, out_dir = Path(args[0]), Path(args[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (file, limits) in SOURCES.items():
        size = build(src_dir / file, limits, out_dir / f"{name}.woff2")
        print(f"{name:26} {size / 1024:6.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
