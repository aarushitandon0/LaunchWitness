"""scripts/list_godaddy_domains.py: reads keys without printing them, refuses to call without keys."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "list_godaddy_domains.py"


def _load():
    spec = importlib.util.spec_from_file_location("list_godaddy_domains", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reads_env_file(tmp_path):
    mod = _load()
    env = tmp_path / ".env"
    env.write_text('# c\nGODADDY_API_KEY=abc   # note\nGODADDY_API_SECRET="s#1"\n\nOTHER\n', encoding="utf-8")
    assert mod.read_env_file(env) == {"GODADDY_API_KEY": "abc", "GODADDY_API_SECRET": "s#1"}


def test_missing_keys_exit_without_calling(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod, "ENV_FILE", tmp_path / "none.env")
    for k in mod.KEYS:
        monkeypatch.delenv(k, raising=False)
    called = []
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: called.append(1))
    with pytest.raises(SystemExit) as e:
        mod.main()
    assert "Missing GODADDY_API_KEY, GODADDY_API_SECRET" in str(e.value) and not called


def test_only_get_and_key_never_printed(tmp_path, monkeypatch, capsys):
    import io
    import json

    mod = _load()
    monkeypatch.setenv("GODADDY_API_KEY", "KEY123")
    monkeypatch.setenv("GODADDY_API_SECRET", "SEC456")
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["method"], seen["url"], seen["auth"] = req.get_method(), req.full_url, req.get_header("Authorization")
        r = io.BytesIO(json.dumps([{"domain": "launchwitness.com", "status": "ACTIVE",
                                    "expires": "2027-11-15T00:00:00Z", "renewAuto": True}]).encode())
        r.__enter__ = lambda: r
        return type("R", (), {"__enter__": lambda s: r, "__exit__": lambda s, *a: False})()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(mod.sys, "argv", ["x"])
    assert mod.main() == 0
    out = capsys.readouterr()
    assert seen == {"method": "GET", "url": "https://api.godaddy.com/v1/domains?limit=100",
                    "auth": "sso-key KEY123:SEC456"}
    assert "launchwitness.com" in out.out and "2027-11-15" in out.out
    assert "KEY123" not in out.out + out.err and "SEC456" not in out.out + out.err
