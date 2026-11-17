"""One contact sheet of all six themes (S14): each cell is the laptop view next to the phone view (above the fold).

    .venv/bin/python scripts/theme_contact_sheet.py docs/screenshots/s14
Reads <theme>-1440-top.png and <theme>-375-top.png (from scripts/shoot_themes.js), writes contact-sheet.png.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

THEMES = [("bakery", "Bakery & desserts"), ("kitchen", "Home kitchen, tiffin & pickles"), ("handmade", "Handmade & crafts"),
          ("tailor", "Tailoring & custom work"), ("gifts", "Gifts & hampers"), ("general", "General")]
CELL_H, DESK_W, GAP, LABEL_H = 400, 640, 14, 44


def main(folder: Path) -> None:
    font = ImageFont.load_default(size=22)
    cells = []
    for key, label in THEMES:
        desk = Image.open(folder / f"{key}-1440-top.png").convert("RGB")
        phone = Image.open(folder / f"{key}-375-top.png").convert("RGB")
        desk = desk.resize((DESK_W, round(desk.height * DESK_W / desk.width)))
        phone = phone.resize((round(phone.width * CELL_H / phone.height), CELL_H))
        w = DESK_W + GAP + phone.width
        cell = Image.new("RGB", (w, CELL_H + LABEL_H), "#ffffff")
        cell.paste(desk, (0, 0))
        cell.paste(phone, (DESK_W + GAP, 0))
        ImageDraw.Draw(cell).text((4, CELL_H + 10), label, fill="#111111", font=font)
        cells.append(cell)
    cw, ch = max(c.width for c in cells), cells[0].height
    pad = 24
    sheet = Image.new("RGB", (3 * cw + 4 * pad, 2 * ch + 3 * pad), "#e9e7e2")
    for i, c in enumerate(cells):
        sheet.paste(c, (pad + (i % 3) * (cw + pad), pad + (i // 3) * (ch + pad)))
    sheet.save(folder / "contact-sheet.png", optimize=True)
    print(sheet.size)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
