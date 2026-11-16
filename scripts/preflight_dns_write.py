"""S11c pre-flight: ONE real DNS write through the app's own guarded GoDaddyClient, then undo it.

    cd backend && ../.venv/Scripts/python ../scripts/preflight_dns_write.py --yes-owner-approved [--domain launchwitness.com]

Steps (the HTTP status of every GoDaddy call is printed; keys and record values never are):
  1. GET the whole zone and save it (replay/raw/dns_preflight_<time>.json, git-ignored). This is the backup.
  2. PUT  A lw-preflight -> 192.0.2.1 (an address reserved for documentation: it leads nowhere).
  3. Ask every nameserver of the zone until all of them answer 192.0.2.1.
  4. DELETE A lw-preflight, and ask every nameserver until none answers.
  5. GET the zone again and compare it with the backup, byte for byte.
A 401/403 on any call stops the run there (nothing further is tried): then Wednesday uses DNS_MODE=wildcard.
Nothing else in the zone is touched: the client itself refuses anything but an A record for one shop-shaped name.
This is the owner-approved exception to "no DNS writes outside a launch"; it needs the flag above every time.
"""

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

from app.checks.dns_resolver import AuthoritativeResolver  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.godaddy.client import GoDaddyClient  # noqa: E402

NAME, IP, TTL = "lw-preflight", "192.0.2.1", 600
WAIT_SECONDS, POLL = 180, 10


def main(args: list[str]) -> int:
    if "--yes-owner-approved" not in args:
        print("This writes one real DNS record and removes it. Pass --yes-owner-approved to run.")
        return 2
    domain = args[args.index("--domain") + 1] if "--domain" in args else "launchwitness.com"
    settings = get_settings().model_copy(update={"godaddy_env": "prod", "app_domain": domain})
    if not settings.godaddy_api_key.get_secret_value() or not settings.godaddy_api_secret.get_secret_value():
        print("GODADDY_API_KEY / GODADDY_API_SECRET are empty in .env: nothing was called.")
        return 2
    client = GoDaddyClient(settings)
    calls: list[tuple[str, str, int]] = []
    bodies: list[bytes] = []

    def seen(response: httpx.Response) -> None:
        response.read()
        calls.append((response.request.method, response.request.url.path, response.status_code))
        print(f"  {response.request.method:6} {response.request.url.path} -> {response.status_code}")
        if response.request.method == "GET" and response.request.url.path.endswith("/records"):
            bodies.append(response.content)

    client._http.event_hooks["response"].append(seen)
    dns = AuthoritativeResolver()
    host = f"{NAME}.{domain}"

    def everywhere() -> list[tuple[str, list[str] | None]]:
        return dns.resolve_all(host, "A")

    def wait_for(want_present: bool) -> bool:
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            answers = everywhere()
            ok = bool(answers) and all(v is not None and ((IP in v) if want_present else (v == [])) for _s, v in answers)
            print("  nameservers: " + "; ".join(f"{s} = {'no answer' if v is None else (', '.join(v) or 'nothing')}"
                                                 for s, v in answers))
            if ok or time.monotonic() > deadline:
                return ok
            time.sleep(POLL)

    def refused(e: Exception) -> bool:
        return isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403)

    print(f"1. Backup: read the whole zone of {domain}")
    try:
        records = client.get_records(domain)
    except Exception as e:
        print(f"STOPPED at the read ({type(e).__name__}). " + ("GoDaddy refuses this account's API: use DNS_MODE=wildcard."
                                                             if refused(e) else "Nothing was written."))
        return 1
    backup = ROOT / "replay" / "raw" / f"dns_preflight_{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(bodies[0])
    print(f"   {len(records)} records saved to {backup.relative_to(ROOT)} ({len(bodies[0])} bytes)")
    if any(str(r.get("name", "")).lower() == NAME for r in records):
        print(f"STOPPED: a record named {NAME} already exists. Nothing was written.")
        return 1
    print("   nameservers before the write:")
    if not wait_for(False):
        print("STOPPED: the nameservers already answer for this name, or didn't answer. Nothing was written.")
        return 1

    status, written = 0, False
    try:
        print(f"2. Create: A {NAME} -> {IP}")
        try:
            client.set_records(domain, "A", NAME, [{"data": IP, "ttl": TTL}])
            written = True
        except Exception as e:
            print(f"STOPPED at the write ({type(e).__name__}). " + ("GoDaddy refuses writes: use DNS_MODE=wildcard."
                                                                  if refused(e) else "See the status above."))
            return 1
        print("3. Confirm at every nameserver")
        if not wait_for(True):
            print(f"   NOT confirmed within {WAIT_SECONDS}s")
            status = 1
    finally:
        if written:
            print(f"4. Delete: A {NAME}")
            try:
                client.delete_records(domain, "A", NAME)
            except Exception as e:
                print(f"   DELETE FAILED ({type(e).__name__}): remove A {NAME} by hand at godaddy.com")
                status = 1
            else:
                if not wait_for(False):
                    print(f"   still answered after {WAIT_SECONDS}s")
                    status = 1
            print("5. Compare the zone with the backup")
            try:
                after = client.get_records(domain)
            except Exception as e:
                print(f"   couldn't re-read the zone ({type(e).__name__})")
                status = 1
            else:
                same_bytes = bodies[-1] == bodies[0]
                same_records = sorted(json.dumps(r, sort_keys=True) for r in after) == sorted(
                    json.dumps(r, sort_keys=True) for r in records)
                print(f"   byte for byte the same: {same_bytes} · same records: {same_records} ({len(after)} records)")
                if not same_records:
                    status = 1
    print("Calls: " + ", ".join(f"{m} {s}" for m, _p, s in calls))
    print("RESULT: " + ("GoDaddy accepts our writes; the zone is as it was." if status == 0 else "see above"))
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
