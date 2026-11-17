"""Render one fitting seller per theme (and optionally any seller x any theme) to static HTML for screenshots (S14).

    .venv/bin/python scripts/render_theme_shots.py <html_dir>                 # the six fitting sellers
    .venv/bin/python scripts/render_theme_shots.py <html_dir> --all-themes    # every gallery seller x every theme
    node scripts/shoot_themes.js <html_dir> docs/screenshots/s14
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.reader import Profile  # noqa: E402
from app.sites.render import render_site  # noqa: E402
from app.sites.themes import THEMES  # noqa: E402

GALLERY = ROOT / "backend" / "tests" / "fixtures" / "site_gallery"
FITTING = {"bakery": "cake_studio", "kitchen": "tiffin", "handmade": "candle_maker", "tailor": "tailor_studio",
           "gifts": "gift_hampers", "general": "plant_shop"}


def load(name: str) -> Profile:
    return Profile.model_validate(json.loads((GALLERY / f"{name}.json").read_text(encoding="utf-8")))


def main(args: list[str]) -> None:
    out = Path(args[0])
    out.mkdir(parents=True, exist_ok=True)
    if "--all-themes" in args:
        for path in sorted(GALLERY.glob("*.json")):
            for key in THEMES:
                p = load(path.stem).model_copy(update={"theme": key, "accent": ""})
                (out / f"{path.stem}__{key}.html").write_text(render_site(p, shop="x"), encoding="utf-8")
        return
    for key, seller in FITTING.items():
        own = load(seller)
        p = own.model_copy(update={"theme": key, "accent": own.accent if own.theme == key else ""})
        (out / f"{key}.html").write_text(render_site(p, shop="x"), encoding="utf-8")
        print(key, "<-", seller)


if __name__ == "__main__":
    main(sys.argv[1:])
