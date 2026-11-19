"""S21: a printable poster for a live shop (owner only, app host): the shop's name, one line, a QR code of its address
and "Order online". Plain HTML + inline CSS, no script, no outside files, print-friendly. Every word is escaped."""

import segno
from markupsafe import Markup

from app.agents.reader import Profile
from app.sites import themes
from app.sites.render import _env

POSTER = _env.from_string("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Poster · {{ p.name }}</title>
<style>
  @page { size: A4; margin: 14mm; }
  * { box-sizing: border-box; }
  html, body { margin: 0; background: #fff; color: #111; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  .sheet { max-width: 720px; margin: 24px auto; padding: 40px 32px; border: 3px solid {{ accent }}; border-radius: 22px; text-align: center; }
  h1 { font-size: 44px; line-height: 1.1; margin: 0 0 12px; overflow-wrap: anywhere; }
  .line { font-size: 22px; margin: 0 0 28px; color: #333; overflow-wrap: anywhere; }
  .qr { width: min(340px, 80vw); margin: 0 auto; }
  .qr svg { display: block; width: 100%; height: auto; }
  .cta { display: inline-block; margin: 26px 0 8px; padding: 12px 30px; border-radius: 999px; background: {{ accent }}; color: {{ accent_ink }};
    font-size: 26px; font-weight: 800; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .url { font-size: 18px; font-weight: 600; overflow-wrap: anywhere; margin: 6px 0 0; }
  .hint { font-size: 14px; color: #555; margin: 0 0 24px; }
  .note { max-width: 720px; margin: 0 auto 32px; padding: 0 16px; font-size: 14px; color: #444; }
  @media print { .note { display: none; } .sheet { margin: 0 auto; border-width: 2px; } }
</style>
</head>
<body>
<p class="note">Print this page (Ctrl+P, or Share → Print on a phone) and put it up where customers will see it.</p>
<main class="sheet">
  <h1>{{ p.name }}</h1>
  {% if line %}<p class="line">{{ line }}</p>{% endif %}
  <p class="hint">Scan with your phone camera</p>
  <div class="qr">{{ qr }}</div>
  <div class="cta">Order online</div>
  <p class="url">{{ shown_url }}</p>
</main>
</body>
</html>
""")


def poster_html(profile: Profile, url: str) -> str:
    _theme, accent = themes.resolve(profile)
    svg = segno.make(url, error="m").svg_inline(scale=1, border=2, omitsize=True, dark="#111111")
    qr = Markup(svg.replace("<svg ", f'<svg role="img" aria-label="QR code for {Markup.escape(url)}" ', 1))
    return POSTER.render(p=profile, line=(profile.section_copy.hero_line or profile.tagline).strip(), qr=qr,
                         shown_url=url.removeprefix("https://").removeprefix("http://").rstrip("/"),
                         accent=accent.color, accent_ink=accent.ink)  # the theme's AA-tested pair (themes.py)
