"""S10.5 §4: links in the owner's preview and on the public shop."""

import re

from app.agents.reader import Profile
from app.sites.render import render_site
from tests.conftest import sign_in
from tests.test_m3_launch import meera

HREF = re.compile(r'(?:href|action)="([^"]*)"')


def profile() -> Profile:
    return Profile(name="Asha's Kitchen", whatsapp="9876543210", phone="9876543210", upi_id="asha@okaxis",
                   products=[{"name": "Thali", "price_inr": 120, "category": "Meals"}])


def test_preview_carries_the_link_script_and_an_enabled_button():
    html = render_site(profile(), preview=True)
    assert "window.parent.postMessage({ lwPreview" in html
    assert "Preview: orders are turned off until your shop is live" in html
    assert re.search(r'<button class="btn btn-primary btn-block" type="submit">Send order', html)


def test_public_shop_has_no_preview_script():
    html = render_site(profile(), shop="asha")
    assert "lwPreview" not in html and "preview-off" not in html


def test_public_shop_links_stay_on_the_shop_host_or_go_outside():
    """On its own host a shop's links are: in-page anchors, its own pages, or outside (WhatsApp, phone, UPI)."""
    for page in ("home", "privacy", "thanks"):
        html = render_site(profile(), page=page, shop="asha",
                           order={"customer_name": "R", "items": [], "total_inr": 0, "note": "", "ref": "LW-ABCDEFGH"})
        for href in HREF.findall(html):
            ok = (href.startswith("#") or href in ("/", "/privacy", "/report-shop", "/order") or href.startswith("/shop-assets/fonts/")
                  or href.startswith(("https://wa.me/", "tel:", "upi://", "https://www.instagram.com/")))
            assert ok, (page, href)


def test_preview_route_serves_privacy_by_name_only(client):
    sign_in(client, "owner@example.org")
    biz = meera(client)
    home = client.get(f"/api/businesses/{biz['id']}/preview").text
    privacy = client.get(f"/api/businesses/{biz['id']}/preview?page=privacy").text
    odd = client.get(f"/api/businesses/{biz['id']}/preview?page=../../etc").text
    assert 'id="menu"' in home and "How " in privacy and 'id="menu"' in odd
