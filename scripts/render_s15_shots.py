"""S15: render three themed shops with every new field filled in, for the order-form and info-section screenshots.

    .venv/bin/python scripts/render_s15_shots.py <html_dir>
    node scripts/shoot_s15.js <html_dir> docs/screenshots/s15
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.reader import Profile  # noqa: E402
from app.sites.render import render_site  # noqa: E402

GALLERY = ROOT / "backend" / "tests" / "fixtures" / "site_gallery"
SHOPS = {"bakery": "cake_studio", "handmade": "candle_maker", "tailor": "tailor_studio"}

NEW = {
    "bakery": {"selling_mode": "pickup_local", "city": "Pune", "area": "Baner", "delivery_areas": "Baner, Aundh, 411045",
               "delivery_fee_inr": 80, "free_delivery_above_inr": 1500, "payment_terms": "advance", "advance_percent": 30,
               "accepts_cash": True, "cancellation_preset": "advance_kept_48h", "allergens": "Contains nuts, gluten and dairy",
               "days_off": [0], "time_slots": ["10am-1pm", "4pm-7pm"], "max_orders_per_day": 4, "min_notice_days": 2},
    "handmade": {"selling_mode": "pickup_india", "city": "Jaipur", "area": "Malviya Nagar", "shipping_fee_inr": 70,
                 "dispatch_days": 3, "shipping_note": "Ships via courier, tracking on WhatsApp", "payment_terms": "upfront",
                 "cancellation_preset": "no_custom", "min_notice_days": 1, "days_off": [5, 6]},
    "tailor": {"selling_mode": "local", "city": "Indore", "area": "Vijay Nagar", "delivery_areas": "Vijay Nagar, 452010",
               "delivery_fee_inr": 0, "payment_terms": "on_delivery", "accepts_cash": True, "cancellation_preset": "custom",
               "cancellation_text": "Alterations can be cancelled before cutting starts.", "on_break": True, "back_on": "2099-12-05",
               "min_notice_days": 5},
}


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for theme, seller in SHOPS.items():
        raw = json.loads((GALLERY / f"{seller}.json").read_text(encoding="utf-8"))
        raw.update({"theme": theme, "accent": "", "upi_id": "shop.demo@okaxis", "upi_display_name": "Demo Shop", **NEW[theme]})
        if theme == "bakery":
            for i, item in enumerate(raw["products"][:4]):
                item["food_mark"] = ["veg", "veg", "egg", "veg"][i]
        p = Profile.model_validate(raw)
        (out / f"{theme}.html").write_text(render_site(p, shop="x", full_dates=["2099-12-01"]), encoding="utf-8")
        print(theme, "<-", seller)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
