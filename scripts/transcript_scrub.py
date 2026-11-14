"""Redact a Claude Code transcript (.jsonl) before it is committed.

    python3 scripts/transcript_scrub.py SRC DEST [email,email,...]
    python3 scripts/transcript_scrub.py --check FILE [email,...]   # scan only (.jsonl or any text, e.g. build.html)

- Personal emails: every address passed in, plus any webmail address -> [redacted-email].
- Secrets: every match of the strict patterns below -> [REDACTED] (only the value;
  the rest of the line is kept).
- Not scanned: base64 image data (screenshots), whose random bytes produce false hits.
- Not treated as a secret: `password`/`secret` followed by code, e.g. `password: SecretStr`,
  `_password = settings.smtp_password` (the value is a type, an attribute or an env lookup).
- After redaction the result is scanned again; if anything real-looking remains, DEST is
  not written and the exit code is 1. Values are never printed, only line numbers + kinds.
"""

import json
import re
import sys
from collections import Counter

REDACTED = "[REDACTED]"
WEBMAIL = re.compile(
    r"[A-Za-z0-9._%+-]+@(gmail|googlemail|yahoo|outlook|hotmail|live|icloud|me|proton|protonmail|rediffmail)\.[a-z.]{2,6}",
    re.IGNORECASE,
)

# Key-shaped secrets: the whole match is the secret.
KEY_PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "aws_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
}
# Assignment-shaped secrets: group "v" is the secret value.
ASSIGN_PATTERNS = {
    "api_secret": re.compile(r"api[_-]?secret[\"' :=]+(?P<v>[A-Za-z0-9]{12,})", re.IGNORECASE),
    "password": re.compile(r"password[\"' :=]+(?P<v>[^\s\"'$<{,;)\]]{6,})", re.IGNORECASE),
}
# A value that is really code, not a secret.
CODE_VALUE = re.compile(
    r"^(SecretStr\b|str\b|bool\b|int\b|None\b|Optional\b|Field\(|settings\.|self\.|os\.environ|os\.getenv|getenv\(|"
    r"env\(|get_secret_value|\[REDACTED)"
)


def _is_image_source(obj: dict) -> bool:
    return obj.get("type") == "base64" and str(obj.get("media_type", "")).startswith("image/")


def scrub_string(s: str, emails: list[str], hits: Counter) -> str:
    for e in emails:
        s, n = re.subn(re.escape(e), "[redacted-email]", s, flags=re.IGNORECASE)
        if n:
            hits["email"] += n
    s, n = WEBMAIL.subn("[redacted-email]", s)
    if n:
        hits["email"] += n
    for kind, pat in KEY_PATTERNS.items():
        s, n = pat.subn(REDACTED, s)
        if n:
            hits[kind] += n
    for kind, pat in ASSIGN_PATTERNS.items():
        def repl(m: re.Match) -> str:
            value = m.group("v")
            if CODE_VALUE.match(value):
                return m.group(0)
            hits[kind] += 1
            return m.group(0)[: m.start("v") - m.start()] + REDACTED

        s = pat.sub(repl, s)
    return s


def walk(obj, emails: list[str], hits: Counter):
    """Scrub every string in a parsed JSON value, skipping base64 image data."""
    if isinstance(obj, str):
        return scrub_string(obj, emails, hits)
    if isinstance(obj, list):
        return [walk(v, emails, hits) for v in obj]
    if isinstance(obj, dict):
        image = _is_image_source(obj)
        return {k: (v if image and k == "data" else walk(v, emails, hits)) for k, v in obj.items()}
    return obj


def scrub_line(line: str, emails: list[str], hits: Counter) -> str:
    stripped = line.rstrip("\n")
    if not stripped.strip():
        return line
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return scrub_string(stripped, emails, hits) + "\n"
    return json.dumps(walk(obj, emails, hits), ensure_ascii=False, separators=(",", ":")) + "\n"


def leftovers(line: str, emails: list[str]) -> list[str]:
    """Kinds of real-looking secrets/emails still present (image data excluded).

    Independent of `scrub_line`: re-parses the line and runs the patterns on every
    string again, so a redaction bug can't hide a leftover."""
    hits: Counter = Counter()
    try:
        walk(json.loads(line), emails, hits)
    except json.JSONDecodeError:
        scrub_string(line, emails, hits)
    return [k for k, n in hits.items() if n]


def scrub_file(src: str, dest: str, emails: list[str]) -> tuple[int, str]:
    hits: Counter = Counter()
    redacted_lines: list[int] = []
    out: list[str] = []
    with open(src, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            before = sum(hits.values())
            out.append(scrub_line(line, emails, hits))
            if sum(hits.values()) != before:
                redacted_lines.append(n)
    remaining = [(n, k) for n, line in enumerate(out, 1) for k in leftovers(line, emails)]
    if remaining:
        report = "; ".join(f"line {n}: {k}" for n, k in remaining[:20])
        return 1, f"SECRET SCAN: real-looking values remain after redaction — NOT saved ({report})"
    with open(dest, "w", encoding="utf-8") as f:
        f.writelines(out)
    summary = ", ".join(f"{k}×{v}" for k, v in sorted(hits.items()) if v) or "none"
    lines = ", ".join(map(str, redacted_lines[:30])) + (" …" if len(redacted_lines) > 30 else "")
    return 0, f"Redacted secrets: {summary}" + (f" (lines {lines})" if redacted_lines else "")


# Long base64 runs (embedded images, compressed data) are skipped in text mode: their random
# bytes produce false hits, and they are not readable text anyway.
BLOB = re.compile(r"[A-Za-z0-9+/=]{400,}")


def check_file(path: str, emails: list[str]) -> list[tuple[int, str]]:
    """Scan WITHOUT changing anything: (line number, kind) of every real-looking secret/email.
    JSON lines are checked string by string (image data skipped); other lines as text with
    long base64 runs masked."""
    found: list[tuple[int, str]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f, 1):
            try:
                kinds = leftovers(json.dumps(json.loads(line)), emails) if line.strip() else []
            except json.JSONDecodeError:
                hits: Counter = Counter()
                scrub_string(BLOB.sub(" ", line), emails, hits)
                kinds = [k for k, v in hits.items() if v]
            found += [(n, k) for k in kinds]
    return found


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--check":
        emails = [e.strip() for e in (argv[3] if len(argv) > 3 else "").split(",") if e.strip()]
        found = check_file(argv[2], emails)
        if found:
            print("SECRET SCAN: found " + "; ".join(f"line {n}: {k}" for n, k in found[:20]), file=sys.stderr)
            return 1
        print(f"SECRET SCAN: clean ({argv[2]})")
        return 0
    if len(argv) < 3:
        print(__doc__)
        return 2
    emails = [e.strip() for e in (argv[3] if len(argv) > 3 else "").split(",") if e.strip()]
    code, message = scrub_file(argv[1], argv[2], emails)
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
