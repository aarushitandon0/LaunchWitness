"""S17: LaunchWitness's own icons are real files on the app's host, never on a shop, and the backend's own HTML links them."""

from fastapi.testclient import TestClient

from app.main import BRAND_FILES, create_app
from tests.test_s11d_chain import launched, share_path

ICON = b"\x00\x00\x01\x00fake-ico"


def _app_with_icons(tmp_path, client):
    for name in BRAND_FILES:
        (tmp_path / name).write_bytes(ICON if name.endswith(".ico") else b"x")
    (tmp_path / "index.html").write_text("<html>spa</html>")
    app = create_app(frontend_dist=tmp_path, replay_page=tmp_path / "none.html", run_lifespan=False)
    app.dependency_overrides.update(client.app.dependency_overrides)
    return app


def test_icons_are_files_with_their_types(tmp_path, client):
    with TestClient(_app_with_icons(tmp_path, client)) as c:
        r = c.get("/favicon.ico")
        assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon" and r.content == ICON
        assert c.get("/apple-touch-icon.png").headers["content-type"] == "image/png"
        assert c.get("/site.webmanifest").headers["content-type"].startswith("application/manifest+json")
        assert c.head("/favicon-32.png").status_code == 200
        assert "spa" in c.get("/favicon.png").text  # not on the list: still the app's page, not a file


def test_shops_never_get_launchwitness_icons(tmp_path, client):
    launched(client, "meera")
    with TestClient(_app_with_icons(tmp_path, client)) as c:
        for name in ("favicon.ico", "apple-touch-icon.png", "site.webmanifest", "logo-mark-64.png"):
            r = c.get("/" + name, headers={"host": "meera.localhost"})
            assert r.status_code == 404 and r.content != ICON
        assert "favicon" not in c.get("/", headers={"host": "meera.localhost"}).text


def test_backend_html_links_the_icons(client):
    biz = launched(client, "meera")
    page = client.get(share_path(client, biz)).text
    assert 'href=/favicon.ico' in page and 'href=/apple-touch-icon.png' in page
    assert 'href=/favicon.ico' in client.get("/r/no-such-token").text
