"""Session 19D (Part 7b): add items after launch, and the honest "New" badge.

- `new_until` is a real date: the day she marks it + NEW_BADGE_DAYS (15). The badge shows on day 15, not on day 16.
- The server keeps only a plain date, never more than 15 days ahead; anything else becomes "".
- Rendered in all six themes with the word "New" (not colour alone), on the AA accent / accent-ink pair, plus a
  "New on the menu" line when anything is new; hostile item text stays escaped.
- An item added to a live shop shows on the public page at once with its badge; another owner can't touch it.
"""

from datetime import date, timedelta

import pytest

from app.agents.reader import Product, Profile
from app.sites import newness
from app.sites.newness import NEW_BADGE_DAYS
from app.sites.render import render_site
from app.sites.themes import THEME_KEYS, THEMES, contrast_ratio
from tests.conftest import sign_in
from tests.test_s10_xss import EVIL, assert_inert, assert_parsed_inert
from tests.test_s19d_live_contact import edit, live_shop, shop

ADDED = date(2026, 11, 19)
MANGO = {"name": "Mango cake ½ kg", "price_inr": 650, "description": "Alphonso mango, eggless", "category": "Cakes"}


def profile(key: str, new_until: str, name: str = "Mango cake ½ kg") -> Profile:
    return Profile(name="Meera's Eggless Bakes", theme=key, whatsapp="+91 98765 43210",
                   products=[Product(name="Chocolate cake", price_inr=500),
                             Product(name=name, price_inr=650, new_until=new_until)])


def test_the_window_is_one_constant_of_15_days():
    assert NEW_BADGE_DAYS == 15
    until = newness.clean((ADDED + timedelta(days=NEW_BADGE_DAYS)).isoformat(), ADDED)
    assert until == "2026-12-04"
    assert newness.is_new(until, ADDED + timedelta(days=15))  # day 15: still shown
    assert not newness.is_new(until, ADDED + timedelta(days=16))  # day 16: gone by itself


@pytest.mark.parametrize("key", THEME_KEYS)
def test_badge_shows_until_day_15_in_every_theme(key):
    until = (ADDED + timedelta(days=NEW_BADGE_DAYS)).isoformat()
    on = render_site(profile(key, until), today=ADDED + timedelta(days=15))
    assert on.count('<span class="new-badge">New</span>') == 2  # on the item + the "New on the menu" line
    assert "New on the menu: Mango cake ½ kg" in on
    off = render_site(profile(key, until), today=ADDED + timedelta(days=16))
    assert "new-badge" not in off.split("</style>")[-1] and "New on the menu" not in off
    assert "new-badge" not in render_site(profile(key, ""), today=ADDED).split("</style>")[-1]


@pytest.mark.parametrize("key", THEME_KEYS)
def test_badge_colours_pass_aa_in_every_theme_and_accent(key):
    t = THEMES[key]
    for a in t.accents:
        assert contrast_ratio(a.color, a.ink) >= 4.5, (key, a.key)  # the badge's own pair
    assert contrast_ratio(t.tokens["ink"], t.tokens["paper"]) >= 4.5  # the "New on the menu" line


@pytest.mark.parametrize("key", THEME_KEYS)
def test_hostile_new_item_is_escaped_in_every_theme(key):
    p = profile(key, (ADDED + timedelta(days=3)).isoformat(), name=EVIL[:120])
    p = p.model_copy(update={"products": [p.products[0], p.products[1].model_copy(update={"description": EVIL[:300],
                                                                                          "category": EVIL[:60]})]})
    html = render_site(p, shop="ok", today=ADDED)
    assert "New on the menu" in html
    assert_inert(html)
    assert_parsed_inert(html, scripts=1)


def test_server_keeps_only_a_real_date_at_most_15_days_ahead(client, engine):
    from app.sites.fulfilment import today_ist

    biz = live_shop(client, engine)
    today = today_ist()
    far, past = (today + timedelta(days=400)).isoformat(), (today - timedelta(days=1)).isoformat()
    products = client.get(f"/api/businesses/{biz['id']}").json()["profile"]["products"]
    out = edit(client, biz, products=[*products, {**MANGO, "new_until": far}, {**MANGO, "name": "B", "new_until": "soon"},
                                      {**MANGO, "name": "C", "new_until": past}])
    by_name = {p["name"]: p["new_until"] for p in out["profile"]["products"]}
    assert by_name["Mango cake ½ kg"] == (today + timedelta(days=NEW_BADGE_DAYS)).isoformat()
    assert by_name["B"] == "" and by_name["C"] == ""


def test_item_added_to_a_live_shop_shows_at_once_with_the_badge(client, engine):
    from app.sites.fulfilment import today_ist

    biz = live_shop(client, engine)
    products = client.get(f"/api/businesses/{biz['id']}").json()["profile"]["products"]
    until = (today_ist() + timedelta(days=NEW_BADGE_DAYS)).isoformat()
    out = edit(client, biz, products=[*products, {**MANGO, "new_until": until}])
    assert out["status"] == "live" and out["public"] is True
    page = shop(client)
    assert "Mango cake ½ kg" in page and '<span class="new-badge">New</span>' in page
    assert 'name="lw-shop"' in page
    # she unticks it: gone at once
    products = out["profile"]["products"]
    edit(client, biz, products=[{**p, "new_until": ""} for p in products])
    assert "new-badge" not in shop(client).split("</style>")[-1]


def test_another_owner_cannot_edit_the_menu(client, new_client, engine):
    biz = live_shop(client, engine)
    other = new_client()
    sign_in(other, "imran@example.org")
    cur = client.get(f"/api/businesses/{biz['id']}").json()
    r = other.put(f"/api/businesses/{biz['id']}", json={"profile": {**cur["profile"], "products": [MANGO]},
                                                       "subdomain": cur["subdomain"]})
    assert r.status_code == 404
    assert "Mango cake" not in shop(client)
