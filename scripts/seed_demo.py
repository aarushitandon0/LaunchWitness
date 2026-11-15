#!/usr/bin/env python3
"""Create Meera's demo business in PRACTICE mode in one command, to rehearse the demo.

Talks to the RUNNING app over HTTP (the practice "fake GoDaddy" lives in the app's memory),
so start the app first. Standard library only.

  python3 scripts/seed_demo.py                       # describe + review (ready to launch)
  python3 scripts/seed_demo.py --launched            # ... and a full practice launch (report green)
  python3 scripts/seed_demo.py --reset               # delete the demo businesses made by this script
  options: --url http://localhost:8000 (default; on the VPS: https://<APP_DOMAIN>)

ADMIN_TOKEN (env, never on the command line) is required: this is a command-line caller, so it
sends no cookies and no Origin, only the emergency admin token (the server allows exactly that).
The shop it makes has no owner (a practice workspace, removed after 24 hours); open its report
in a browser signed in as the team (ADMIN_EMAIL). It refuses to continue if the shop is NOT practice.
State (ids) is kept in ~/.launchwitness-demo.json (not in the repo).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SELLER = REPO / "backend" / "tests" / "fixtures" / "sellers" / "meera_cakes.json"
STATE = Path.home() / ".launchwitness-demo.json"


class Api:
    def __init__(self, url: str, admin: str):
        self.url, self.admin = url.rstrip("/"), admin

    def call(self, method: str, path: str, body=None, form=None):
        headers = {}
        data = None
        if body is not None:
            data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["X-Admin-Token"] = self.admin
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            sys.exit(f"FAIL: {method} {path} -> {e.code}: {detail}")
        except urllib.error.URLError as e:
            sys.exit(f"FAIL: can't reach {self.url} ({e.reason}). Is the app running?")


def load_state() -> list[dict]:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return []


def save_state(rows: list[dict]) -> None:
    STATE.write_text(json.dumps(rows, indent=2))
    STATE.chmod(0o600)


def seed(api: Api, launched: bool) -> None:
    if not api.call("GET", "/api/admin/check").get("admin"):
        sys.exit("FAIL: ADMIN_TOKEN was not accepted.")
    s = json.loads(SELLER.read_text(encoding="utf-8"))
    biz = api.call("POST", "/api/businesses", form={"description": s["description"], "price_list": s["price_list"]})
    rows = load_state()
    rows.append({"id": biz["id"], "url": api.url})
    save_state(rows)
    if not biz.get("practice"):
        sys.exit(f"FAIL: business #{biz['id']} is NOT practice (the server is real and an admin token was used). "
                 "Stopped before changing anything else.")
    used = {r.get("sub") for r in rows}
    sub = "meera" if "meera" not in used else f"meera-{len(rows)}"
    biz = api.call("PUT", f"/api/businesses/{biz['id']}",
                   body={"profile": biz["profile"], "subdomain": sub})
    rows[-1]["sub"] = sub
    save_state(rows)
    print(f"OK: created {biz['profile']['name']} (#{biz['id']}, practice) at {biz['site_url']}")
    if launched:
        names = api.call("GET", f"/api/businesses/{biz['id']}/names")
        if not names:
            sys.exit("FAIL: no free practice names found")
        domain = names[0]["domain"]
        plan = api.call("POST", f"/api/businesses/{biz['id']}/plans", body={"mode": "full", "domain": domain})
        api.call("POST", f"/api/plans/{plan['id']}/approve", body={"approved_by": "Meera (demo seed)"})
        for _ in range(60):
            p = api.call("GET", f"/api/plans/{plan['id']}")
            if p["status"] == "blocked":
                api.call("POST", f"/api/plans/{plan['id']}/practice-buy")
            elif p["status"] == "done":
                break
            elif p["status"] == "failed":
                sys.exit(f"FAIL: practice launch stopped: {[st['message'] for st in p['steps'] if st['message']]}")
            time.sleep(0.5)
        for _ in range(60):
            rep = api.call("GET", f"/api/businesses/{biz['id']}/report")
            if rep["run"] and rep["run"]["status"] == "done":
                break
            time.sleep(0.5)
        print(f"OK: practice launch on {domain}: {rep['headline']}")
    print(f"Report (sign in as the team to open it): {api.url}/#/b/{biz['id']}/report")


def reset(api: Api) -> None:
    rows = [r for r in load_state() if r["url"].rstrip("/") == api.url]
    for r in rows:
        try:
            api.call("DELETE", f"/api/admin/practice-businesses/{r['id']}")
            print(f"OK: deleted demo business #{r['id']}")
        except SystemExit as e:
            print(f"skip #{r['id']}: {e}")
    save_state([r for r in load_state() if r["url"].rstrip("/") != api.url])
    if not rows:
        print("Nothing to reset for", api.url)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--launched", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        sys.exit("FAIL: set ADMIN_TOKEN in the environment (e.g. export it from the server .env).")
    api = Api(a.url, token)
    reset(api) if a.reset else seed(api, a.launched)


if __name__ == "__main__":
    main()
