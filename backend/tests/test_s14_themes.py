"""S14: a theme for every kind of home business. Claude picks a key, code renders; the safety layer is the same.

What is proved here (one place, so a reader can see the whole promise):
- every theme x every gallery seller renders cleanly, on all three pages;
- every theme keeps the marker, the order form + token, the basket script (byte for byte), UPI + WhatsApp links,
  "Report this shop", privacy, photos, and works without JS (plain quantity boxes);
- hostile text in every field (testimonials and section_copy too) is escaped in every theme;
- every accent and every base text colour passes WCAG AA; an invalid key falls back; old profiles still render;
- fonts are self-hosted, small, licensed; the page stays small and lazy; no framework, no hotlinking;
- only the seller's own data appears: no invented reviews, ratings or "bestseller".
"""

import json
import re
from pathlib import Path

import pytest

from app.agents.reader import Product, Profile, SectionCopy, plain_text, read_business
from app.agents.reader import Testimonial as Quote
from app.sites import themes
from app.sites.render import render_site
from app.sites.routes import shop_headers
from app.sites.themes import ACCENT_KEYS, THEME_KEYS, THEMES, contrast_ratio
from tests.test_reader import GOOD, ScriptedClaude
from tests.test_s10_xss import EVIL, SHORT, assert_inert, assert_parsed_inert

FIX = Path(__file__).parent / "fixtures"
GALLERY = sorted((FIX / "site_gallery").glob("*.json"))
ROOT = Path(__file__).parents[2]
FONT_DIR = Path(__file__).parents[1] / "app" / "sites" / "fonts"
ORDER = {"customer_name": "Asha", "items": [{"name": "Thing", "qty": 2, "price_inr": 100}], "total_inr": 200, "note": "",
         "ref": "LW-ABCDEFGH"}


def gallery(stem: str) -> Profile:
    return Profile.model_validate(json.loads((FIX / "site_gallery" / f"{stem}.json").read_text(encoding="utf-8")))


def themed(stem: str, key: str) -> Profile:
    return gallery(stem).model_copy(update={"theme": key, "accent": ""})


def script_of(html: str) -> str:
    return SCRIPT.search(html).group(1)


SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
GALLERY_STEMS = [p.stem for p in GALLERY]
FITTING = {"bakery": "cake_studio", "kitchen": "tiffin", "handmade": "candle_maker", "tailor": "tailor_studio",
           "gifts": "gift_hampers", "general": "plant_shop"}


def test_six_themes_with_two_or_three_accents_each():
    assert THEME_KEYS == ("bakery", "kitchen", "handmade", "tailor", "gifts", "general")
    for t in THEMES.values():
        assert 2 <= len(t.accents) <= 3 and t.display and t.body and t.blurb
        assert t.hero in {"split", "board", "centered", "ledger", "festive"}
        assert t.menu in {"list", "cards", "board", "pricelist"}
    assert len({t.hero for t in THEMES.values()} | {t.menu for t in THEMES.values()}) >= 8  # the looks really differ
    assert len({t.art for t in THEMES.values()}) == 6


# ---------- Every theme x every seller ----------

@pytest.mark.parametrize("key", THEME_KEYS)
@pytest.mark.parametrize("stem", GALLERY_STEMS)
def test_every_theme_renders_every_gallery_seller_cleanly(key, stem):
    p = themed(stem, key)
    for page in ("home", "privacy", "thanks"):
        html = render_site(p, page=page, shop="s", order=ORDER)
        body = SCRIPT.sub("", html)
        assert f'class="theme-{key}"' in html
        assert "None" not in body and "verified" not in html.lower() and "{{" not in html and "{%" not in html
        assert "<h1>" in html and "</html>" in html
    html = render_site(p, shop="s")
    for i, item in enumerate(p.products):  # every item once, with its own quantity box (works without JS)
        assert html.count(f'name="qty_{i}"') == 1
    assert html.count("<h1>") == 1
    assert ("WhatsApp" in html) == bool(p.whatsapp or p.phone)
    assert ('id="pay"' in html) == bool(p.upi_id)


# ---------- The safety layer is the same in every theme ----------

@pytest.mark.parametrize("key", THEME_KEYS)
def test_every_theme_keeps_the_marker_the_order_path_the_links_and_the_basket(key):
    p = themed("cake_studio", key).model_copy(update={"instagram": "sugar.crumb"})
    html = render_site(p, shop="asha", photos={"shop": [], "items": {}})
    assert '<meta name="lw-shop" content="asha">' in html
    assert '<form class="layout" method="post" action="/order" id="order-form">' in html
    assert re.search(r'<input type="hidden" name="order_token" value="[\w-]{16,}">', html)
    assert 'name="customer_name" required' in html and 'name="customer_phone" required' in html
    assert 'class="hp" aria-hidden="true"' in html and 'name="website"' in html  # the honeypot
    assert 'href="/report-shop"' in html and 'href="/privacy"' in html
    assert "https://wa.me/919876543210?text=" in html and "upi://pay?pa=sugarcrumb.demo@example" in html
    assert 'aria-label="UPI payment QR code"' in html and "https://www.instagram.com/sugar.crumb/" in html
    assert 'id="basket"' in html and 'id="total"' in html and 'id="bar-order"' in html
    prices = re.findall(r'data-price="(\d+)"', html)  # the basket reads these: they must be the real prices
    assert prices == [str(item.price_inr) for item in p.products]
    assert html.count("<script>") == 1  # exactly the template's own basket script


def test_the_basket_script_and_the_form_are_identical_in_every_theme():
    scripts, forms = set(), set()
    for key in THEME_KEYS:
        html = render_site(themed("cake_studio", key), shop="x")
        scripts.add(script_of(html))
        forms.add(re.sub(r'value="[\w-]{16,}"', "", re.search(r'<aside class="panel".*?</aside>', html, re.S).group(0)))
    assert len(scripts) == 1 and len(forms) == 1


@pytest.mark.parametrize("key", THEME_KEYS)
def test_every_theme_works_without_javascript(key):
    html = render_site(themed("tailor_studio", key))
    assert 'type="number"' in html and 'name="qty_0"' in html  # plain quantity boxes
    assert ".js .qty input" in html  # hidden only once the script has run (the `js` class is added by it)
    assert '<noscript' not in html


@pytest.mark.parametrize("key", THEME_KEYS)
def test_privacy_thanks_and_demo_pages_keep_their_parts(key):
    p = themed("candle_maker", key)
    thanks = render_site(p, page="thanks", order=ORDER, shop="x")
    assert "Thank you, Asha!" in thanks and "LW-ABCDEFGH" in thanks and "Send this order to the shop" in thanks
    assert "Report this shop" in thanks
    assert "How Ember &amp; Clay Candles uses your details" in render_site(p, page="privacy")
    demo = render_site(p, page="home", demo=True, base="/demo/x")
    assert "Demo shop: orders here are not real" in demo and "Report this shop" not in demo
    pre = render_site(p, preview=True)
    assert "Preview: only you can see this page" in pre and 'id="preview-off"' in pre
    assert pre.count("<script>") == 2


@pytest.mark.parametrize("key", THEME_KEYS)
def test_photos_work_in_every_theme(key):
    ph = lambda n: {"small": f"/photos/{n}-480.webp", "large": f"/photos/{n}-1200.webp", "small_w": 480, "small_h": 360,  # noqa: E731
                    "large_w": 1200, "large_h": 900, "alt": f"Photo {n}"}
    photos = {"shop": [ph(f"{i:032x}") for i in range(5)], "items": {"Lavender clay jar": ph("a" * 32)}}
    html = render_site(themed("candle_maker", key), photos=photos)
    for i in range(5):
        assert f"/photos/{i:032x}-" in html  # every shop photo shows (hero + strip)
    assert "/photos/" + "a" * 32 + "-480.webp" in html
    assert html.count('fetchpriority="high"') == 1  # only the first image is eager
    assert html.count('<img') == html.count('loading="lazy"') + 1
    assert all('alt="' in tag for tag in re.findall(r"<img [^>]*>", html))


# ---------- Hostile text, in every theme ----------

def hostile(key: str) -> Profile:
    base = Profile(
        name=EVIL, tagline=EVIL, about=EVIL, area=EVIL[:120], hours=EVIL, phone="+91 98765 43210",
        whatsapp="+91 98765 43210", upi_id="evil@upi", tone=SHORT, selling_point=SHORT, upi_display_name=EVIL[:60],
        fssai_number="12345678901234", pickup_available=True, delivery_available=True, delivery_fee_inr=50,
        allow_item_message=True, delivery_areas=EVIL[:200], instagram="ok.name",
        products=[Product(name=EVIL, price_inr=100, description=EVIL, category=EVIL[:60]),
                  Product(name=EVIL + "x", price_inr=50, description=EVIL, category=EVIL[:60], addon=True)])
    # model_construct skips the sanitiser on purpose: the TEMPLATE must hold even if hostile text got saved.
    return base.model_copy(update={
        "theme": key,
        "section_copy": SectionCopy.model_construct(hero_line=EVIL, about=EVIL, how_ordering=EVIL),
        "testimonials": [Quote.model_construct(name=EVIL, text=EVIL)]})


@pytest.mark.parametrize("key", THEME_KEYS)
def test_hostile_text_in_every_field_is_escaped_in_every_theme(key):
    p = hostile(key)
    for page in ("home", "privacy"):
        assert_inert(render_site(p, page=page, shop=EVIL))
    html = render_site(p, shop="ok")
    assert html.count("<script>") == 1 and "alert(1)</script>" not in html
    assert_parsed_inert(html, scripts=1)
    assert 'id="reviews"' in html  # the hostile testimonial really was rendered (and escaped)
    order = {"code": "LW-1", "items": [{"name": EVIL, "qty": 1, "price_inr": 100}], "total_inr": 100, "customer_name": EVIL,
             "customer_phone": SHORT, "note": EVIL, "item_message": EVIL}
    assert_inert(render_site(p, page="thanks", order=order, shop="ok"))
    assert_inert(render_site(p, form_error=EVIL, form_values={"customer_name": EVIL, "note": EVIL, "qty_0": EVIL}))


def test_hostile_theme_and_accent_keys_never_reach_the_page():
    for bad in (EVIL, "../../etc/passwd", "bakery'; --", "x" * 500, "Bakery ", None, 5):
        p = Profile.model_validate({"name": "Shop", "products": [{"name": "A", "price_inr": 5}], "theme": bad, "accent": bad})
        html = render_site(p)
        assert "alert(" not in html and "passwd" not in html
        assert p.theme in ("", "bakery")  # only a real key survives ("Bakery " is trimmed and lowered)
    # Even a value forced past validation can't pick a file or a colour: resolve only looks up the fixed lists.
    forced = Profile(name="S", products=[Product(name="A", price_inr=5)]).model_copy(
        update={"theme": "../../x", "accent": "red;}</style><script>"})  # model_copy skips validation
    html = render_site(forced)
    assert "</style><script>" not in html and "../../x" not in html


def test_section_copy_is_plain_text_and_capped():
    c = SectionCopy.model_validate({"hero_line": "<b>Hello</b> <script>x</script> there" + "!" * 200, "about": "a" * 900,
                                    "how_ordering": "line\n\nbreak"})
    assert "<" not in c.hero_line and ">" not in c.hero_line and len(c.hero_line) <= 90
    assert len(c.about) <= 400 and c.how_ordering == "line break"
    assert plain_text(5, 10) == "" and plain_text("a<b", 10) == "a b"


# ---------- Contrast (WCAG AA) ----------

@pytest.mark.parametrize("key", THEME_KEYS)
def test_text_colours_pass_aa_on_every_surface(key):
    t = THEMES[key].tokens
    for fg in ("ink", "ink2", "muted"):
        for bg in ("bg", "paper", "soft"):
            assert contrast_ratio(t[fg], t[bg]) >= 4.5, (key, fg, bg)


@pytest.mark.parametrize("key,accent", [(t.key, a.key) for t in THEMES.values() for a in t.accents])
def test_every_accent_passes_aa(key, accent):
    t, a = THEMES[key], THEMES[key].accent(accent)
    assert a.key == accent
    assert contrast_ratio(a.ink, a.color) >= 4.5  # button text
    for bg in (t.tokens["bg"], t.tokens["paper"], t.tokens["soft"], a.tint):  # links, chips, step numbers, eyebrows
        assert contrast_ratio(a.color, bg) >= 4.5, (key, accent, bg)


def test_fixed_colours_pass_aa():
    assert contrast_ratio("#ffffff", "#0b7a3e") >= 4.5  # the WhatsApp button
    assert contrast_ratio("#991b1b", "#fef2f2") >= 4.5  # an error message


def test_contrast_helper_matches_known_values():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert round(contrast_ratio("#777777", "#ffffff"), 2) == 4.48  # the classic just-below-AA grey


# ---------- Choosing: rule-based fallback, invalid keys, old profiles ----------

@pytest.mark.parametrize("stem,expected", [("cake_studio", "bakery"), ("bakery", "bakery"), ("candle_maker", "handmade"),
                                           ("candles", "handmade"), ("tailor_studio", "tailor"), ("tailor", "tailor"),
                                           ("tiffin", "kitchen"), ("gift_hampers", "gifts"), ("plant_shop", "general")])
def test_rule_based_choice_fits_the_gallery_sellers(stem, expected):
    p = gallery(stem).model_copy(update={"theme": "", "accent": ""})
    assert themes.rule_choice(p) == expected
    assert themes.resolve(p)[0].key == expected


def test_rule_choice_uses_the_niche_when_the_words_say_nothing():
    base = {"name": "Zed", "products": [{"name": "Item", "price_inr": 10}]}
    for niche, expected in (("food", "kitchen"), ("handmade", "handmade"), ("custom", "tailor"), ("", "general")):
        assert themes.rule_choice(Profile.model_validate({**base, "niche": niche})) == expected


def test_a_valid_choice_wins_over_the_rules_and_an_invalid_one_falls_back():
    own = gallery("cake_studio").model_copy(update={"theme": "tailor", "accent": "thread"})
    assert (themes.resolve(own)[0].key, themes.resolve(own)[1].key) == ("tailor", "thread")
    bad = Profile.model_validate({**gallery("cake_studio").model_dump(), "theme": "neon", "accent": "chilli"})
    assert bad.theme == "" and themes.resolve(bad)[0].key == "bakery" and themes.resolve(bad)[1].key == "raspberry"
    mismatched = Profile.model_validate({**gallery("cake_studio").model_dump(), "theme": "bakery", "accent": "chilli"})
    assert mismatched.accent == "" and themes.resolve(mismatched)[1].key == "raspberry"


def test_old_saved_profiles_still_render():
    """A profile saved before themes existed has none of the new keys."""
    old = {"name": "Old Shop", "tagline": "Cakes", "products": [{"name": "A", "price_inr": 5, "description": "", "category": "X"}]}
    p = Profile.model_validate(old)
    assert p.theme == "" and p.accent == "" and p.section_copy == SectionCopy() and p.testimonials == []
    html = render_site(p, shop="old")
    assert 'class="theme-bakery"' in html and "Old Shop" in html and 'name="qty_0"' in html
    # ... including a stored JSON that has an unknown extra key and a half-filled section_copy
    p2 = Profile.model_validate({**old, "section_copy": {"hero_line": "Hi"}, "colour": "red"})
    assert p2.section_copy.hero_line == "Hi" and "Hi" in render_site(p2)


def test_reader_replies_with_a_bad_theme_get_the_rule_based_one():
    reply = {**GOOD, "name": "Cake House", "tagline": "Fresh cakes", "theme": "pink-unicorn", "accent": "sparkle",
             "section_copy": {"hero_line": "<i>Cakes</i>", "about": "", "how_ordering": ""},
             "products": [{"name": "Chocolate cake", "price_inr": 500, "description": "", "category": "Cakes"}]}
    p = read_business(ScriptedClaude(reply), description="we bake cakes")
    assert p.theme == "bakery" and p.accent == "" and p.section_copy.hero_line == "Cakes"
    good = read_business(ScriptedClaude({**reply, "theme": "gifts", "accent": "emerald"}), description="x")
    assert (good.theme, good.accent) == ("gifts", "emerald")  # a valid key is kept even when the words say bakery
    wrong = read_business(ScriptedClaude({**reply, "theme": "gifts", "accent": "chilli"}), description="x")
    assert (wrong.theme, wrong.accent) == ("gifts", "")  # the accent isn't one of that theme's


def test_reader_schema_only_offers_keys_and_plain_text():
    from app.agents.reader import PROFILE_SCHEMA, SYSTEM

    props = PROFILE_SCHEMA["properties"]
    assert props["theme"]["enum"] == list(THEME_KEYS) and props["accent"]["enum"] == list(ACCENT_KEYS)
    assert set(props["section_copy"]["properties"]) == {"hero_line", "about", "how_ordering"}
    assert "never write HTML, CSS, colours or fonts" in SYSTEM and "Never invent reviews" in SYSTEM
    assert "testimonials" not in PROFILE_SCHEMA["required"]  # owner-only


def test_theme_fixtures_for_the_readers_are_marked_as_placeholders():
    """Hand-written theme values in the saved Reader replies carry `_note` until captured live (see PR description)."""
    for path in sorted((FIX / "claude").glob("reader_*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["theme"] in THEME_KEYS and raw["accent"] in ACCENT_KEYS, path.name
        assert raw["section_copy"]["hero_line"], path.name
        assert Profile.model_validate(raw).theme == raw["theme"]
        if "_theme_placeholder" in raw:  # still hand-written: must say so
            assert "_note" in raw, path.name


# ---------- Honest content ----------

@pytest.mark.parametrize("key", THEME_KEYS)
def test_nothing_is_invented(key):
    html = SCRIPT.sub("", render_site(themed("cake_studio", key), shop="x"))
    assert 'id="reviews"' not in html  # no testimonials unless the seller pasted some
    text = re.sub(r"<style>.*?</style>", "", html, flags=re.S).lower()
    for word in ("★", "★", "rated", "rating", "bestseller", "best seller", "testimonial", "customers love", "5 star", "award"):
        assert word not in text, word


def test_testimonials_show_only_when_given_and_say_who_shared_them():
    p = themed("candle_maker", "handmade")
    html = render_site(p)
    assert 'id="reviews"' in html and html.count("· shared by the seller") == 2
    assert "The sandalwood one filled my whole living room" in html and "<b>Anika</b>" in html
    assert 'id="reviews"' not in render_site(p.model_copy(update={"testimonials": []}))


def test_the_ledger_price_is_the_lowest_real_price_and_missing_data_shows_nothing():
    html = render_site(themed("tailor_studio", "tailor"))
    assert 'Prices start at</small><b>₹120</b>' in html  # the cheapest item the seller listed (Saree fall and pico)
    bare = Profile(name="Bare", products=[Product(name="Thing", price_inr=100)], theme="tailor")
    html = render_site(bare)
    assert "Kind words" not in html and 'class="badges"' not in html and 'class="meta"' not in html
    assert "Pickup" not in html and "UPI" not in html  # no pay / pickup claims without data


def test_how_ordering_steps_only_state_what_the_seller_gave():
    from app.sites.render import how_steps

    bare = how_steps(Profile(name="B", products=[Product(name="T", price_inr=1)]))
    assert [t for t, _ in bare] == ["Choose", "Send your order", "We confirm"]
    full = how_steps(gallery("cake_studio"))
    assert "Pickup or delivery" in [t for t, _ in full] and "Pay" in [t for t, _ in full]
    assert "at least 2 days ahead" in full[0][1]


# ---------- Fonts, speed, strict page policy ----------

FONT_LINK = re.compile(r"/shop-assets/fonts/([\w-]+\.woff2)")


@pytest.mark.parametrize("key", THEME_KEYS)
def test_fonts_are_self_hosted_small_and_licensed(key):
    t = THEMES[key]
    total = sum((FONT_DIR / f.file).stat().st_size for f in dict.fromkeys(t.fonts))
    assert total <= 120 * 1024, (key, total)
    licences = (ROOT / "docs" / "FONTS.md").read_text(encoding="utf-8")
    for f in t.fonts:
        assert (FONT_DIR / f.file).read_bytes()[:4] == b"wOF2", f.file
        assert f.file in licences and "SIL Open Font License" in licences
    html = render_site(themed("cake_studio", key))
    assert set(FONT_LINK.findall(html)) == {f.file for f in t.fonts}
    assert not re.search(r"googleapis|gstatic|fonts\.com|cdn|typekit|@import", html)
    assert "format('woff2')" in html and "font-display:swap" in html


def test_every_font_has_the_rupee_sign_and_the_licence_file():
    TTFont = pytest.importorskip("fontTools.ttLib").TTFont

    for f in sorted(FONT_DIR.glob("*.woff2")):
        if f.name.startswith("instrument-serif"):  # headlines only: see docs/FONTS.md
            continue
        assert 0x20B9 in TTFont(f).getBestCmap(), f.name
    for t in THEMES.values():  # whatever sets a price must carry the glyph
        setters = [t.body] + ([*t.display] if t.hero == "ledger" or t.menu == "pricelist" else [])
        assert all(0x20B9 in TTFont(FONT_DIR / x.file).getBestCmap() for x in setters), t.key
    assert len(list((ROOT / "docs" / "fonts").glob("OFL-*.txt"))) == 10


@pytest.mark.parametrize("key", THEME_KEYS)
def test_page_budget_no_frameworks_lazy_images(key):
    for stem in ("big_menu", "cake_studio"):
        html = render_site(themed(stem, key))
        limit = 130 if stem == "big_menu" else 75  # KB of HTML (CSS + the one small script are inline)
        assert len(html.encode()) <= limit * 1024, (key, stem, len(html.encode()))
    html = render_site(themed("cake_studio", key))
    assert "<script src" not in html and not re.search(r'<link[^>]+rel="stylesheet"', html)
    assert html.count("<script>") == 1
    css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    assert len(css.encode()) <= 40 * 1024
    assert 'rel="preload"' in html and html.count('rel="preload"') == 1  # one font: the headline's


def test_font_route_serves_only_font_files_with_cors_for_the_sandboxed_preview(client):
    r = client.get("/shop-assets/fonts/fraunces.woff2")
    assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"
    assert r.headers["access-control-allow-origin"] == "*" and "max-age" in r.headers["cache-control"]
    for bad in ("fraunces.ttf", "nope.woff2", "FRAUNCES.woff2", "a.woff2.py"):
        assert client.get(f"/shop-assets/fonts/{bad}").status_code == 404, bad
    for sneaky in ("%2e%2e%2fconfig.py", "..%2fmain.py", "..%5cmain.py"):  # decoded into another path: never a file
        r = client.get(f"/shop-assets/fonts/{sneaky}")
        assert not r.headers.get("content-type", "").startswith("font/")
        assert "pydantic" not in r.text and "FastAPI(" not in r.text


def test_fonts_are_served_on_a_shop_host_too(client):
    assert client.get("/shop-assets/fonts/dm-sans.woff2", headers={"host": "meera.localhost"}).status_code == 200


def test_shop_pages_carry_a_strict_content_security_policy():
    html = render_site(themed("cake_studio", "bakery"), shop="x")
    h = shop_headers(html)
    csp = h["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "font-src 'self'" in csp and "img-src 'self'" in csp
    assert "form-action 'self'" in csp and "base-uri 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-eval" not in csp and "script-src 'sha256-" in csp and "http" not in csp
    import base64
    import hashlib

    digest = base64.b64encode(hashlib.sha256(script_of(html).encode()).digest()).decode()
    assert f"'sha256-{digest}'" in csp  # the basket script runs because its hash is listed; nothing else may
    assert "script-src 'none'" in shop_headers("<p>no script</p>")["Content-Security-Policy"]


def test_the_live_shop_sends_the_policy_and_themes_its_page(client, engine):
    from tests.test_m2_site import MEERA, create, save

    save(client, create(client), whatsapp="98765 43210")
    r = client.get("/", headers={"host": MEERA})
    assert r.status_code == 200 and "script-src 'sha256-" in r.headers["content-security-policy"]
    assert 'class="theme-bakery"' in r.text and '<meta name="lw-shop"' in r.text
    assert "script-src" in client.get("/privacy", headers={"host": MEERA}).headers["content-security-policy"]


# ---------- Owner: picker data, saving, audit, preview, demo shops ----------

def test_theme_catalog_is_public_and_complete(client):
    data = client.get("/api/themes").json()
    assert [t["key"] for t in data] == list(THEME_KEYS)
    assert all(2 <= len(t["accents"]) <= 3 and t["tokens"]["bg"].startswith("#") for t in data)


def test_owner_picks_a_look_saved_audited_and_the_preview_follows(client, engine):
    from sqlmodel import Session, select

    from app.models import AuditEvent
    from tests.test_m2_site import create

    biz = create(client)
    assert biz["theme"]["key"] == "bakery" and biz["profile"]["theme"] == "bakery"
    r = client.put(f"/api/businesses/{biz['id']}/theme", json={"theme": "gifts", "accent": "emerald"})
    assert r.status_code == 200 and r.json()["theme"] == {"key": "gifts", "accent": "emerald", "suggested": "bakery",
                                                         "chosen": True}
    assert r.json()["profile"]["theme"] == "gifts" and r.json()["profile"]["products"] == biz["profile"]["products"]
    assert 'class="theme-gifts"' in client.get(f"/api/businesses/{biz['id']}/preview").text
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(AuditEvent.action == "theme_changed")).all()
    assert len(ev) == 1 and ev[0].detail == "bakery/raspberry -> gifts/emerald" and ev[0].actor == "owner"


def test_owner_cannot_pick_a_made_up_look_or_colour(client):
    from tests.test_m2_site import create

    biz = create(client)
    url = f"/api/businesses/{biz['id']}/theme"
    assert client.put(url, json={"theme": "<script>"}).status_code == 422
    assert client.put(url, json={"theme": "bakery", "accent": "#ff0000"}).status_code == 422
    assert client.put(url, json={"theme": "bakery", "accent": "chilli"}).status_code == 422  # another theme's colour
    assert client.put(url, json={"theme": "bakery"}).status_code == 200  # no accent = the theme's first
    assert client.get(f"/api/businesses/{biz['id']}").json()["theme"]["accent"] == "raspberry"


def test_saving_the_review_form_with_a_new_look_is_audited_and_unrelated_saves_are_not(client, engine):
    from sqlmodel import Session, select

    from app.models import AuditEvent
    from tests.test_m2_site import create

    biz = create(client)

    def put(**kw):
        r = client.put(f"/api/businesses/{biz['id']}", json={"profile": {**biz["profile"], **kw}, "subdomain": biz["subdomain"]})
        assert r.status_code == 200, r.text
        return r.json()

    put(tagline="New tagline")  # no look change: no event
    first = put(theme="tailor", accent="olive", section_copy={"hero_line": "Cut to fit", "about": "", "how_ordering": ""},
                testimonials=[{"name": "Dev", "text": "Great fit."}])
    biz["profile"] = first["profile"]
    out = put()  # saving again with the same look writes no second event
    assert out["theme"]["key"] == "tailor" and out["profile"]["section_copy"]["hero_line"] == "Cut to fit"
    assert out["profile"]["testimonials"] == [{"name": "Dev", "text": "Great fit."}]
    with Session(engine) as s:
        ev = s.exec(select(AuditEvent).where(AuditEvent.action == "theme_changed")).all()
    assert [e.detail for e in ev] == ["bakery/raspberry -> tailor/olive"]


def test_another_owner_cannot_change_the_look(client, new_client):
    from tests.test_m2_site import create

    biz = create(client)
    other = new_client()
    assert other.put(f"/api/businesses/{biz['id']}/theme", json={"theme": "tailor"}).status_code in (401, 403, 404)


@pytest.mark.parametrize("demo,key", [("meera", "bakery"), ("imran", "tailor"), ("sunita", "kitchen")])
def test_demo_shops_use_their_fitting_themes(client, demo, key):
    r = client.get(f"/demo/{demo}")
    assert r.status_code == 200 and f'class="theme-{key}"' in r.text and "Demo shop: orders here are not real" in r.text
    assert "Report this shop" not in r.text


# ---------- The proof checks work on a themed shop ----------

@pytest.mark.parametrize("key", THEME_KEYS)
def test_the_https_marker_check_sees_every_themed_shop(key):
    from app.proof import shop_tag  # noqa: F401  (the checker looks for this exact meta tag)

    html = render_site(themed("candle_maker", key), shop="candles")
    assert len(re.findall(r'<meta name="lw-shop" content="candles">', html)) == 1


def test_her_about_text_wins_and_the_readers_short_paragraph_fills_in_when_empty():
    p = themed("cake_studio", "bakery").model_copy(update={"about": "Her own words.", "section_copy": SectionCopy(about="Reader words.")})
    assert "Her own words." in render_site(p) and "Reader words." not in render_site(p)
    empty = p.model_copy(update={"about": ""})
    assert "Reader words." in render_site(empty)
    assert 'id="about"' not in render_site(empty.model_copy(update={"section_copy": SectionCopy()}))


def test_the_pickers_inline_preview_does_not_tick_the_go_live_preview_box(client, engine):
    from sqlmodel import Session

    from app.models import Business
    from tests.test_m2_site import create

    biz = create(client)
    assert client.get(f"/api/businesses/{biz['id']}/preview?inline=1").status_code == 200
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).previewed_at is None  # she hasn't opened her real preview yet
    assert client.get(f"/api/businesses/{biz['id']}/preview").status_code == 200
    with Session(engine) as s:
        assert s.get(Business, biz["id"]).previewed_at is not None
