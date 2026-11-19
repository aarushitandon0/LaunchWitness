"""Session 20 Part B: each shop's own signature (motif + arrangement, chosen by code from keys) and the gentle interactions.

Keys only; every motif/arrangement/theme/accent combination renders, keeps the strict CSP, stays readable (WCAG AA), and
hostile text stays escaped. The effects script only enhances: nothing is hidden or moved by the server.
"""

import gzip
import re
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.agents.reader import Profile
from app.models import AuditEvent
from app.sites import motifs
from app.sites.render import render_site
from app.sites.routes import shop_headers
from app.sites.themes import THEMES, contrast_ratio
from tests.test_s20_payments import live_shop

TPL = Path(__file__).resolve().parents[1] / "app" / "sites" / "templates"
EVIL = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
COMBOS = [(t, m, a) for t, ms in motifs.MOTIFS.items() for m in ms for a in motifs.ARRANGEMENTS]


def handlers(html: str) -> list[str]:
    from html.parser import HTMLParser

    found: list[str] = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            found.extend(f"{tag}:{k}" for k, _ in attrs if k.lower().startswith("on"))

    P().feed(html)
    return found


def profile(theme="bakery", motif="", art="", name="Meera's Eggless Bakes", accent="") -> Profile:
    return Profile(name=name, tagline="Cakes", products=[{"name": "Cake", "price_inr": 500, "description": "Soft",
                                                             "category": "Cakes"}, {"name": "Tart", "price_inr": 300, "category": "Pies"}],
                   theme=theme, accent=accent, motif=motif, art=art, whatsapp="98765 43210")


# ---------- the lists and the seed ----------

def test_lists_are_fixed_and_complete():
    assert set(motifs.MOTIFS) == set(THEMES) and all(len(v) == 3 for v in motifs.MOTIFS.values())
    assert len(set(motifs.ALL_MOTIFS)) == 18 and set(motifs.MOTION) == set(motifs.ARRANGEMENTS)
    assert set(motifs.LABELS) == set(motifs.ALL_MOTIFS)


def test_signature_is_stable_valid_and_varies_by_name():
    names = [f"Shop number {i}" for i in range(60)]
    seen = set()
    for n in names:
        a = motifs.signature("bakery", n)
        assert a == motifs.signature("bakery", n) and a[0] in motifs.MOTIFS["bakery"] and a[1] in motifs.ARRANGEMENTS
        seen.add(a)
    assert len(seen) >= 6  # same theme, different shops: different signatures
    assert motifs.signature("bakery", "x", "leaves", "zzz")[0] in motifs.MOTIFS["bakery"]  # a foreign motif is ignored
    assert motifs.signature("kitchen", "x", "leaves", "corner") == ("leaves", "corner")


def test_two_shops_in_one_theme_draw_differently():
    a = str(motifs.svg_for("sprinkles", "scatter", "Aarti's Bakes"))
    b = str(motifs.svg_for("sprinkles", "scatter", "Brownie House"))
    assert a != b and a == str(motifs.svg_for("sprinkles", "scatter", "Aarti's Bakes"))


@pytest.mark.parametrize("theme,motif,art", COMBOS)
def test_svg_is_numbers_only_and_safe(theme, motif, art):
    svg = str(motifs.svg_for(motif, art, EVIL))  # even a hostile NAME only seeds the numbers
    assert svg.startswith("<svg") and 'aria-hidden="true"' in svg and "<script" not in svg.lower() and "onerror" not in svg
    assert "http" not in svg and "href" not in svg and "alert" not in svg and len(svg) < 6000
    assert len(re.findall(r"<g transform", svg)) >= 4
    assert max(float(x) for x in re.findall(r'opacity="([\d.]+)"', svg)) <= 0.8


# ---------- every theme x motif x arrangement renders cleanly ----------

@pytest.mark.parametrize("theme,motif,art", COMBOS)
def test_every_combination_renders_with_the_strict_csp(theme, motif, art):
    p = profile(theme=theme, motif=motif, art=art, name=EVIL[:60])
    html = render_site(p, shop="s")
    assert f'data-motif="{motif}"' in html and f'data-art="{art}"' in html and f"motion-{motifs.MOTION[art]}" in html
    assert 'class="motif-wrap' in html and html.count("<script>") == 2
    assert "<script>alert(1)" not in html and "<img src=x" not in html
    assert not handlers(html)  # no inline event handlers on any real tag
    csp = shop_headers(html)["Content-Security-Policy"]
    assert csp.count("sha256-") == 2 and "unsafe-inline'" in csp.split("style-src")[1].split(";")[0] and "script-src 'unsafe" not in csp
    assert "default-src 'none'" in csp and "'unsafe-eval'" not in csp
    # progressive: the server hides and moves nothing
    assert 'class="pre' not in html and ' pre"' not in html and 'class="qv' not in html
    assert 'method="post" action="/order" id="order-form"' in html and 'name="order_token"' in html


def test_shop_with_no_choice_gets_a_signature_from_its_name():
    html = render_site(profile(theme="gifts"), shop="s")
    m = re.search(r'data-motif="(\w+)" data-art="(\w+)"', html)
    assert m.group(1) in motifs.MOTIFS["gifts"] and m.group(2) in motifs.ARRANGEMENTS


# ---------- readable: AA for every motif/accent/background combination ----------

def blend(fg: str, bg: str, alpha: float) -> str:
    f, b = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (fg, bg)]
    return "#" + "".join(f"{round(alpha * x + (1 - alpha) * y):02x}" for x, y in zip(f, b, strict=True))


@pytest.mark.parametrize("theme", list(THEMES))
def test_text_stays_aa_over_the_motif_layer(theme):
    css = (TPL / "css" / "fx.css").read_text()
    alpha = float(re.search(r"\.motif-wrap \{[^}]*opacity: (\.\d+)", css).group(1))
    t = THEMES[theme]
    assert alpha <= 0.2
    for accent in t.accents:
        for bg in ("bg", "soft", "paper"):
            worst = blend(accent.color, t.tokens[bg], alpha * 0.8)  # the strongest a drawing can get (shapes are at most 80%)
            for ink in ("ink", "ink2", "muted"):
                assert contrast_ratio(t.tokens[ink], worst) >= 4.5, (theme, accent.key, bg, ink)
            assert contrast_ratio(accent.color, worst) >= 3  # links in the accent colour over a drawing stay legible (large/UI)


# ---------- the fixed effects script ----------

def test_effects_use_transform_and_opacity_only_and_no_unsafe_apis():
    css = (TPL / "css" / "fx.css").read_text()
    js = (TPL / "js" / "fx.js").read_text()
    for kf in re.findall(r"@keyframes [\w-]+ \{(.*?)\n  \}?\n?", css, re.S):
        assert not re.search(r"filter|blur|box-shadow|border-radius|width|height|top|left", kf)
    assert "animation: lw-" in css and "<animate" not in css and "<animate" not in js  # no SMIL
    for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write", "XMLHttpRequest", "fetch(",
                "http://", "https://", "localStorage", "requestAnimationFrame"):
        assert bad not in js, bad
    assert "prefers-reduced-motion: no-preference" in css and "prefers-reduced-motion: reduce" in js
    assert not re.search(r"\.js \.pre \{[^}]*(filter|box-shadow)", css)


def test_extra_weight_is_small():
    size = len(gzip.compress(((TPL / "js" / "fx.js").read_text() + (TPL / "css" / "fx.css").read_text()).encode()))
    svg = len(gzip.compress(str(motifs.svg_for("sprinkles", "scatter", "Meera")).encode()))
    assert size + svg < 25 * 1024, size + svg


def test_quick_view_and_basket_hooks_exist_in_the_page():
    html = render_site(profile(), shop="s")
    for hook in ('id="bar-order"', 'id="order-h"', 'class="chips"', 'class="item', 'btn-sm add"', 'class="plus"', 'class="minus"'):
        assert hook in html


# ---------- the owner's choice ----------

def test_owner_changes_signature_audited_and_validated(client, engine):
    biz = live_shop(client, engine)
    cur = client.get(f"/api/businesses/{biz['id']}").json()["theme"]
    assert cur["motif"] in motifs.ALL_MOTIFS and len(cur["motifs"]) == 3 and len(cur["arts"]) == 3
    assert all(o["svg"].startswith("<svg") for o in cur["motifs"] + cur["arts"])
    other = next(m for m in motifs.MOTIFS[cur["key"]] if m != cur["motif"])
    r = client.put(f"/api/businesses/{biz['id']}/signature", json={"motif": other, "art": "band"})
    assert r.status_code == 200 and r.json()["theme"]["motif"] == other and r.json()["theme"]["art"] == "band"
    assert r.json()["theme"]["motif_chosen"] and r.json()["theme"]["art_chosen"]
    assert client.put(f"/api/businesses/{biz['id']}/signature", json={"motif": "<script>"}).status_code == 422
    assert client.put(f"/api/businesses/{biz['id']}/signature", json={"art": "nope"}).status_code == 422
    foreign = next(m for k, ms in motifs.MOTIFS.items() if k != cur["key"] for m in ms)
    assert client.put(f"/api/businesses/{biz['id']}/signature", json={"motif": foreign}).status_code == 422
    html = client.get("/", headers={"host": "meera.localhost"}).text
    assert f'data-motif="{other}"' in html and 'data-art="band"' in html
    with Session(engine) as s:
        rows = s.exec(select(AuditEvent).where(AuditEvent.action == "signature_changed")).all()
    assert len(rows) == 1 and other in rows[0].detail and "/" in rows[0].detail
    # a theme change drops a motif that doesn't belong to the new theme
    new = "kitchen" if cur["key"] != "kitchen" else "tailor"
    out = client.put(f"/api/businesses/{biz['id']}/theme", json={"theme": new, "accent": ""}).json()["theme"]
    assert out["motif"] in motifs.MOTIFS[new] and not out["motif_chosen"]
