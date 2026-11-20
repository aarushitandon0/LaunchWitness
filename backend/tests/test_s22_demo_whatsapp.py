"""S22: a demo shop shows the WhatsApp button where a real shop has it, but it only opens a plain demo page."""

import re

import pytest

from app.sites.demo import DEMOS, demo_shop
from app.sites.render import render_site


def wa_links(html: str) -> list[str]:
    return re.findall(r'<a class="btn btn-wa[^"]*" href="([^"]+)"', html)


@pytest.mark.parametrize("name", sorted(DEMOS))
def test_demo_whatsapp_button_goes_to_the_demo_page_in_every_look(client, name):
    r = client.get(f"/demo/{name}")
    assert r.status_code == 200
    links = wa_links(r.text)
    assert links, "the demo shop shows the WhatsApp button"
    assert set(links) == {f"/demo/{name}/whatsapp"}
    assert "wa.me" not in r.text and "api.whatsapp.com" not in r.text and "whatsapp://" not in r.text

    page = client.get(f"/demo/{name}/whatsapp")
    assert page.status_code == 200
    assert "This is a demo website. On a real shop, this button opens a WhatsApp chat with the seller." in page.text
    assert f'href="/demo/{name}/"' in page.text and "Back to the shop" in page.text
    assert page.headers["x-robots-tag"] == "noindex"
    assert "wa.me" not in page.text
    # the app host's CSP (Caddy) covers /demo/* unchanged; the page adds no inline script or handler
    # no new script: the plain page has none of the shop's scripts
    assert "<script" not in page.text and " onclick=" not in page.text


def test_demo_whatsapp_page_unknown_demo_is_404(client):
    assert client.get("/demo/nobody/whatsapp").status_code == 404


def test_demo_whatsapp_page_never_on_a_shop_host(client, settings):
    host = f"meera.{settings.app_domain}"
    assert client.get("/demo/meera/whatsapp", headers={"host": host}).status_code == 404


def test_demo_thank_you_whatsapp_button_is_the_demo_page_too(client):
    r = client.post("/demo/meera/order", data={"customer_name": "Asha", "customer_phone": "98765 43210", "qty_0_0": "1",
                                               "fulfilment": "pickup"})
    assert "wa.me" not in r.text
    assert all(h == "/demo/meera/whatsapp" for h in wa_links(r.text))


def test_real_shop_whatsapp_button_unchanged():
    profile = demo_shop("meera").model_copy(update={"whatsapp": "+91 98765 43210"})
    html = render_site(profile, shop="meera")
    links = wa_links(html)
    assert links and all(h.startswith("https://wa.me/919876543210?") for h in links)
    assert 'target="_blank" rel="noopener"' in html
    assert not any(h.endswith("/whatsapp") for h in links)
