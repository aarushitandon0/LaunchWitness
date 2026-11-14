"""scripts/transcript_scrub.py: redact values, keep the rest, refuse if anything real remains.

Fake secrets are assembled at runtime so no key-shaped string lives in the repo.
"""

import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "transcript_scrub.py"
spec = importlib.util.spec_from_file_location("transcript_scrub", SCRIPT)
ts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ts)

ANT = "sk-" + "ant-" + "api03" + "Q" * 30
AWS = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
GH = "gh" + "p_" + "a1" * 18
EMAIL = "someone.private" + "@" + "gmail.com"


def line(*texts, image_data=None) -> str:
    content = [{"type": "text", "text": t} for t in texts]
    if image_data is not None:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}})
    return json.dumps({"type": "user", "message": {"content": content}}) + "\n"


def scrub(text: str, emails=()) -> tuple[str, Counter]:
    hits: Counter = Counter()
    return ts.scrub_string(text, list(emails), hits), hits


@pytest.mark.parametrize("code", [
    'smtp_password: SecretStr = SecretStr("")',
    "self._password = settings.smtp_password",
    'password = os.environ["SMTP_PASSWORD"]',
    "imap_password: str | None = None",
    "SMTP_PASSWORD=\nIMAP_HOST=imap.secureserver.net",
])
def test_code_annotations_are_not_secrets(code):
    out, hits = scrub(code)
    assert out == code and not hits


@pytest.mark.parametrize("text,secret,kind", [
    (f"export ANTHROPIC_API_KEY={ANT} now", ANT, "anthropic_key"),
    (f"aws id {AWS} here", AWS, "aws_key_id"),
    (f"token {GH}", GH, "github_token"),
    ('password="hunter2hunter2" in config', "hunter2hunter2", "password"),
    ("api_secret=abcdef0123456789xyz", "abcdef0123456789xyz", "api_secret"),
])
def test_real_values_are_replaced_and_rest_kept(text, secret, kind):
    out, hits = scrub(text)
    assert hits[kind] == 1
    assert out == text.replace(secret, "[REDACTED]")  # only the value goes; the rest survives
    assert not ts.leftovers(json.dumps({"t": out}), [])


def test_emails_redacted():
    out, _ = scrub(f"mail {EMAIL} or boss@company.in", emails=["boss@company.in"])
    assert out == "mail [redacted-email] or [redacted-email]"


def test_base64_image_data_is_not_scanned_but_text_is(tmp_path):
    src, dest = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    image = "iVBORw0KGgo" + AWS + "xyz=="  # random image bytes that happen to look like a key
    src.write_text(line(f"key {ANT}", image_data=image) + "not json password=hunter2hunter2\n")
    code, msg = ts.scrub_file(str(src), str(dest), [])
    assert code == 0 and "anthropic_key×1" in msg and "password×1" in msg
    out = dest.read_text().splitlines()
    rec = json.loads(out[0])
    assert rec["message"]["content"][0]["text"] == "key [REDACTED]"
    assert rec["message"]["content"][1]["source"]["data"] == image  # untouched
    assert out[1] == "not json password=[REDACTED]"
    assert ANT not in dest.read_text()


def test_refuses_to_save_if_anything_real_remains(tmp_path, monkeypatch):
    src, dest = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    src.write_text(line(f"key {ANT}", f"mail {EMAIL}"))
    monkeypatch.setattr(ts, "scrub_line", lambda raw, emails, hits: raw)  # simulate a redaction miss
    code, msg = ts.scrub_file(str(src), str(dest), [])
    assert code == 1 and not dest.exists()
    assert "anthropic_key" in msg and "email" in msg
    assert ANT not in msg and EMAIL not in msg  # values are never printed


def test_main_never_prints_values(tmp_path, capsys):
    src, dest = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    src.write_text(line(f"{ANT} {GH} {EMAIL}"))
    assert ts.main(["x", str(src), str(dest), ""]) == 0
    printed = capsys.readouterr()
    for v in (ANT, GH, EMAIL):
        assert v not in printed.out + printed.err and v not in dest.read_text()


def test_clean_transcript_is_saved_unchanged_in_content(tmp_path):
    src, dest = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    src.write_text(line("hello", "just code: smtp_password: SecretStr"))
    assert ts.scrub_file(str(src), str(dest), [])[0] == 0
    assert json.loads(dest.read_text()) == json.loads(src.read_text())


def test_check_mode_scans_without_changing(tmp_path, capsys):
    html = tmp_path / "build.html"
    html.write_text("<html><script>var d = {\"t\": \"key " + ANT + "\"};</script>\n<p>mail meera@gmail.com</p></html>\n")
    before = html.read_text()
    assert ts.main(["x", "--check", str(html)]) == 1
    err = capsys.readouterr().err
    assert "anthropic_key" in err and "email" in err and ANT not in err
    assert html.read_text() == before  # never modified


def test_check_mode_clean_and_skips_base64_blobs(tmp_path):
    page = tmp_path / "build.html"
    blob = ("A" * 10 + "KIA" + "ABCDEFGHIJKLMNOP") * 30  # key-shaped bytes inside a long base64 run
    page.write_text(f"<html><img src=\"data:image/png;base64,{blob}\"><p>password: SecretStr</p></html>\n")
    assert ts.main(["x", "--check", str(page)]) == 0


def test_check_mode_custom_email(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text(json.dumps({"message": {"content": "write to owner@company.example"}}) + "\n")
    assert ts.main(["x", "--check", str(f)]) == 0
    assert ts.main(["x", "--check", str(f), "owner@company.example"]) == 1
