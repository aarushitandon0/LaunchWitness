"""Render every site-gallery profile (backend/tests/fixtures/site_gallery) to static HTML for screenshots.

    .venv/bin/python scripts/render_site_gallery.py <html_dir>
    node scripts/shoot_site_gallery.js <html_dir> docs/screenshots/s8
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.agents.reader import Profile  # noqa: E402
from app.sites.render import render_site  # noqa: E402

GALLERY = ROOT / "backend" / "tests" / "fixtures" / "site_gallery"

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
for path in sorted(GALLERY.glob("*.json")):
    profile = Profile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    (out / f"{path.stem}.html").write_text(render_site(profile), encoding="utf-8")
    print(path.stem)
