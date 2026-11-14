"""Draw a handwritten-style price list photo (test input for the Reader).

Our own image: italic font with per-letter jitter, blue ink on ruled paper, a
slight tilt, uneven light and noise, saved as a JPEG like a phone photo.
Usage: .venv/bin/python scripts/make_handwritten_pricelist.py <out.jpg>
"""

import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

LINES = [
    "Lakshmi's Kitchen - Rate list",
    "",
    "Idli batter 1 kg ........ Rs 90",
    "Dosa batter 1 kg ....... Rs 90",
    "Ragi dosa batter 1 kg .. Rs 120",
    "Idli podi 200 g .......... Rs 110",
    "Coconut chutney 250 g .. Rs 60",
    "Sambar 500 ml ........... Rs 80",
    "",
    "Order before 7 pm for next day!",
]
FONT = "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf"


def main(out: str) -> None:
    rnd = random.Random(7)
    w, h = 900, 1000
    img = Image.new("RGB", (w, h), (246, 240, 222))
    d = ImageDraw.Draw(img)
    for y in range(140, h, 72):  # ruled lines + margin
        d.line([(0, y), (w, y)], fill=(170, 190, 215), width=2)
    d.line([(90, 0), (90, h)], fill=(220, 150, 150), width=2)
    y = 82
    for line in LINES:
        x = 110 + rnd.randint(-6, 6)
        for ch in line:
            size = rnd.randint(31, 37)
            font = ImageFont.truetype(FONT, size)
            glyph = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
            ImageDraw.Draw(glyph).text((size // 2, size // 3), ch, font=font,
                                       fill=(25 + rnd.randint(0, 20), 40, 120 + rnd.randint(0, 30), 255))
            glyph = glyph.rotate(rnd.uniform(-9, 9), resample=Image.BICUBIC)
            img.paste(glyph, (int(x) - size // 2, y + rnd.randint(-3, 3) - size // 3), glyph)
            x += font.getlength(ch) * rnd.uniform(0.92, 1.08)
        y += 72 + rnd.randint(-3, 3)
    img = img.rotate(-2.5, resample=Image.BICUBIC, expand=False, fillcolor=(90, 80, 70))
    shade = Image.linear_gradient("L").resize((w, h)).point(lambda p: 255 - p // 6)  # uneven light
    img = Image.composite(img, Image.new("RGB", (w, h), (120, 110, 95)), shade)
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    img = Image.blend(img, noise, 0.06).filter(ImageFilter.GaussianBlur(0.6))
    img.save(out, "JPEG", quality=78)


if __name__ == "__main__":
    main(sys.argv[1])
