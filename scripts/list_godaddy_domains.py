"""List the domains in your GoDaddy account (read-only, production API).

One GET to https://api.godaddy.com/v1/domains with
`Authorization: sso-key <GODADDY_API_KEY>:<GODADDY_API_SECRET>`.
It never buys, changes or deletes anything, and never prints the key or secret.

Keys come from the environment, or from the repo's `.env` (git-ignored) if not set there.

Usage (from the repo root):
    python scripts/list_godaddy_domains.py           # table
    python scripts/list_godaddy_domains.py --json    # raw JSON
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://api.godaddy.com/v1/domains?limit=100"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
KEYS = ("GODADDY_API_KEY", "GODADDY_API_SECRET")


def read_env_file(path: Path) -> dict[str, str]:
    """Minimal .env reader: KEY=value, ignores comments and blank lines, strips quotes and inline comments."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        out[key.strip()] = value
    return out


def credentials() -> tuple[str, str]:
    file_env = read_env_file(ENV_FILE)
    values = [os.environ.get(k) or file_env.get(k, "") for k in KEYS]
    missing = [k for k, v in zip(KEYS, values) if not v]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} (set them in .env or the environment). Nothing was sent.")
    return values[0], values[1]


def main() -> int:
    raw = "--json" in sys.argv[1:]
    key, secret = credentials()
    req = urllib.request.Request(URL, method="GET", headers={
        "Authorization": f"sso-key {key}:{secret}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            domains = json.load(r)
    except urllib.error.HTTPError as e:
        # The body is GoDaddy's error JSON (code + message); it never contains our key.
        body = e.read().decode("utf-8", "replace")[:500]
        print(f"GoDaddy answered HTTP {e.code}: {body}", file=sys.stderr)
        if e.code in (401, 403):
            print("Check that these are PRODUCTION keys (not OTE) and that the account may use the API.",
                  file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Could not reach api.godaddy.com: {e.reason}", file=sys.stderr)
        return 1

    if raw:
        print(json.dumps(domains, indent=2))
        return 0
    if not domains:
        print("No domains in this account.")
        return 0
    print(f"{'DOMAIN':<32} {'STATUS':<12} {'EXPIRES':<12} AUTO-RENEW")
    for d in domains:
        print(f"{d.get('domain', '?'):<32} {d.get('status', '?'):<12} "
              f"{str(d.get('expires', '?'))[:10]:<12} {d.get('renewAuto', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
