def test_health_ok_and_reports_env(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "env": "ote"}


def test_health_reports_prod_when_set(make_settings, engine):
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    app = create_app(run_lifespan=False)
    app.dependency_overrides[get_settings] = lambda: make_settings(godaddy_env="prod")
    assert TestClient(app).get("/api/health").json()["env"] == "prod"


def test_unknown_api_path_is_404_not_frontend(client):
    assert client.get("/api/nope").status_code == 404


def test_safe_defaults(settings):
    assert settings.godaddy_env == "ote"
    assert settings.claude_mode == "fixture"
    assert settings.allow_purchase is False
    assert settings.max_spend_usd == 15


def test_env_example_lists_every_setting():
    from app.config import REPO_ROOT, Settings

    text = (REPO_ROOT / ".env.example").read_text()
    names = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.lstrip().startswith("#")}
    missing = {f.upper() for f in Settings.model_fields} - names
    assert not missing, f".env.example is missing: {sorted(missing)}"
