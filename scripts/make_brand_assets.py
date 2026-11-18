"""Build the LaunchWitness logo files from the owner's artwork.

Usage: .venv/Scripts/python scripts/make_brand_assets.py [source.png]
Default source: docs/brand/image.png (lime/cream/peach ribbon "W" on a flat near-black background).

Writes:
  brand/logo-mark.png                 1024 px, transparent master
  frontend/public/favicon.ico         16 + 32 + 48 (mark on an ink rounded square)
  frontend/public/favicon-32.png
  frontend/public/apple-touch-icon.png 180 px on solid ink (iOS ignores transparency)
  frontend/public/icon-192.png, icon-512.png (transparent)
  frontend/public/logo-mark-64.png, logo-mark-128.png (header 1x / 2x)
  frontend/public/site.webmanifest
  scratch previews over white and #111 (only with --preview <dir>)

The background is removed by colour distance from the corner colour with a soft ramp, then each
partly transparent pixel is "decontaminated" (the background colour is taken back out), so the
anti-aliased edges do not keep a dark halo on light pages.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "frontend" / "public"
BRAND = ROOT / "brand"

INK = (0x16, 0x16, 0x14)  # --ink in frontend/src/tokens.css: the dark frame the header sits on
LIME = "#dcf06a"  # --accent
RAMP_LO, RAMP_HI = 22.0, 70.0  # colour distance from background: <= LO fully clear, >= HI fully solid
MARGIN = 0.08  # padding around the content, as a share of the square side
SMALL_MARGIN = 0.02  # tighter crop for 16/32/48 px so the mark isn't mush


def corner_colour(im: Image.Image) -> tuple[float, float, float]:
    w, h = im.size
    px = im.load()
    pts = [(x, y) for x in range(8) for y in range(8)]
    corners = [(x, y) for cx, cy in pts for (x, y) in ((cx, cy), (w - 1 - cx, cy), (cx, h - 1 - cy), (w - 1 - cx, h - 1 - cy))]
    rs = [px[c][:3] for c in corners]
    return tuple(sum(c[i] for c in rs) / len(rs) for i in range(3))  # type: ignore[return-value]


def remove_background(src: Image.Image) -> Image.Image:
    rgb = src.convert("RGB")
    bg = corner_colour(rgb)
    out = Image.new("RGBA", rgb.size)
    sp = rgb.load()
    op = out.load()
    w, h = rgb.size
    for y in range(h):
        for x in range(w):
            r, g, b = sp[x, y]
            d = ((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2) ** 0.5
            a = min(1.0, max(0.0, (d - RAMP_LO) / (RAMP_HI - RAMP_LO)))
            if a <= 0.0:
                op[x, y] = (0, 0, 0, 0)
                continue
            if a < 1.0:  # take the background back out of the edge pixel
                r = (r - (1 - a) * bg[0]) / a
                g = (g - (1 - a) * bg[1]) / a
                b = (b - (1 - a) * bg[2]) / a
            op[x, y] = (_c(r), _c(g), _c(b), round(a * 255))
    return out


def _c(v: float) -> int:
    return max(0, min(255, round(v)))


def square_crop(im: Image.Image, margin: float) -> Image.Image:
    alpha = im.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    box = alpha.getbbox()
    if not box:
        raise SystemExit("no logo content found after removing the background")
    content = im.crop(box)
    side = round(max(content.size) / (1 - 2 * margin))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(content, ((side - content.width) // 2, (side - content.height) // 2))
    return canvas


def resized(im: Image.Image, size: int) -> Image.Image:
    small = im.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 48:
        small = small.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    return small


def on_solid(im: Image.Image, size: int, colour: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGBA", (size, size), colour + (255,))
    base.alpha_composite(resized(im, size))
    return base.convert("RGB")


def tile(im: Image.Image, size: int) -> Image.Image:
    """Tab icon: the mark on an ink rounded square, so the cream ribbon reads on light browser tabs too."""
    scale = 8
    big = size * scale
    base = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=round(big * 0.22), fill=255)
    base.paste(Image.new("RGBA", (big, big), INK + (255,)), (0, 0), mask)
    inset = round(big * 0.10)
    base.alpha_composite(im.resize((big - 2 * inset, big - 2 * inset), Image.Resampling.LANCZOS), (inset, inset))
    return base.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    args = sys.argv[1:]
    preview_dir = None
    if "--preview" in args:
        i = args.index("--preview")
        preview_dir = Path(args[i + 1])
        del args[i : i + 2]
    src_path = Path(args[0]) if args else ROOT / "docs" / "brand" / "image.png"

    clear = remove_background(Image.open(src_path))
    master = square_crop(clear, MARGIN).resize((1024, 1024), Image.Resampling.LANCZOS)
    tight = square_crop(clear, SMALL_MARGIN).resize((1024, 1024), Image.Resampling.LANCZOS)

    BRAND.mkdir(exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    master.save(BRAND / "logo-mark.png", optimize=True)

    ico_sizes = [16, 32, 48]
    tile(tight, 48).save(PUBLIC / "favicon.ico", sizes=[(s, s) for s in ico_sizes],
                         append_images=[tile(tight, s) for s in ico_sizes[:-1]])
    tile(tight, 32).save(PUBLIC / "favicon-32.png", optimize=True)
    on_solid(master, 180, INK).save(PUBLIC / "apple-touch-icon.png", optimize=True)
    for s in (192, 512):
        resized(master, s).save(PUBLIC / f"icon-{s}.png", optimize=True)
    for s in (64, 128):
        resized(tight, s).save(PUBLIC / f"logo-mark-{s}.png", optimize=True)

    manifest = {
        "name": "LaunchWitness",
        "short_name": "LaunchWitness",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#161614",
        "background_color": "#161614",
        "display": "browser",
        "start_url": "/",
    }
    (PUBLIC / "site.webmanifest").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)
        for name, colour in (("white", (255, 255, 255)), ("dark", (0x11, 0x11, 0x11)), ("cream", (0xF5, 0xEF, 0xE4))):
            on_solid(master, 512, colour).save(preview_dir / f"master-on-{name}.png")
            for s in (16, 32):
                bg = Image.new("RGBA", (s, s), colour + (255,))
                bg.alpha_composite(tile(tight, s))
                big = bg.resize((s * 8, s * 8), Image.Resampling.NEAREST)
                big.save(preview_dir / f"fav{s}-on-{name}-x8.png")
    print("brand assets written:", BRAND / "logo-mark.png", "and", PUBLIC)


if __name__ == "__main__":
    main()
