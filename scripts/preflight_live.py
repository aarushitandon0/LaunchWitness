"""S11c pre-flight: run the app's OWN Claude paths against the live API once, check every reply, save fixtures.

    cd backend && CLAUDE_MODE=live ../.venv/Scripts/python ../scripts/preflight_live.py [reader | reader:<seller>] [namer] [policy] [doctor]

What runs (no arguments = all four parts), all through the app's routes or service functions:
  reader  POST /api/businesses for 3 fresh sellers + the handwritten photo; prices, tidy-up, the shop page renders
  namer   GET /api/businesses/<id>/names for the first shop
  policy  policy_check() on the 5 cases in tests/fixtures/policy_cases.json (the verdict must match `expect`)
  doctor  a practice launch, the `a_record` fault, "Check again": the investigating Doctor must look and re-point

Money: everything is recorded in a scratch database (replay/raw/preflight_s11c.db, git-ignored) whose daily cap is
$0.25, so the cap holds across re-runs on the same day. GoDaddy, DNS and mail are the pretend world. The key is read
from .env by the app's Settings and never printed. Stops at the first failure (re-run only the parts that are left).
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from markupsafe import escape  # noqa: E402
from sqlmodel import Session  # noqa: E402

from app.agents.claude_client import FIXTURE_DIR, FallbackClaudeClient, LiveClaudeClient, spent_today_usd  # noqa: E402
from app.agents.policy import policy_check  # noqa: E402
from app.agents.reader import HARD_FIXTURES, Profile  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.db import get_session, init_db, make_engine  # noqa: E402
from app.integrations import fake_integrations, get_integrations, get_practice_integrations  # noqa: E402
from app.main import create_app  # noqa: E402
from app.routers.businesses import get_claude  # noqa: E402
from app.safety.access import csrf_for  # noqa: E402
from app.sites.render import format_inr, render_site  # noqa: E402

CAP_USD = 0.25
ADMIN_TOKEN = "preflight-admin-token-0123456789"
ORIGIN = "http://localhost"
READERS = ["tiffin_hinglish", "candle_note", "tailor_from", "handwritten_photo"]
CASES = json.loads((HARD_FIXTURES.parent / "policy_cases.json").read_text(encoding="utf-8"))


class Browser(TestClient):
    """Like a real browser on the app: state-changing /api calls carry the Origin and the CSRF token."""

    def request(self, method, url, **kw):
        headers = dict(kw.pop("headers", None) or {})
        if method.upper() in ("POST", "PUT", "PATCH", "DELETE") and str(url).startswith("/api/"):
            headers.setdefault("Origin", ORIGIN)
            cookie = self.cookies.get("lw_session") or self.cookies.get("lw_guest")
            if cookie:
                headers.setdefault("X-CSRF-Token", csrf_for(cookie))
        return super().request(method, url, headers=headers, **kw)


class Recording:
    """Passes every call to live Claude and keeps (fixture name, reply)."""

    def __init__(self, live):
        self.live_client, self.replies = live, []

    def ask_json(self, **kw):
        data = self.live_client.ask_json(**kw)
        self.replies.append((kw["fixture"], data))
        return data


def save(name: str, data: dict) -> None:
    (FIXTURE_DIR / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_shop(case: dict, profile: Profile) -> None:
    """Real prices kept, "from" prices marked, and the seller page renders with every item on it."""
    prices = sorted(p.price_inr for p in profile.products)
    want, optional = sorted(case["expected_prices"]), case.get("optional_prices", [])
    extra = list(prices)
    for p in want:
        assert p in extra, f"price {p} missing: got {prices}"
        extra.remove(p)
    assert all(p in optional for p in extra), f"unexpected prices {extra}: got {prices}"
    for p in profile.products:
        if "from_prices" in case and p.price_inr in want:
            assert p.price_from == (p.price_inr in case["from_prices"]), f"price_from wrong for {p.name} ({p.price_inr})"
    page = render_site(profile, shop="lw-preflight")
    assert '<meta name="lw-shop" content="lw-preflight">' in page
    assert str(escape(profile.name)) in page, "the shop's name is not on the page"
    for p in profile.products:
        assert format_inr(p.price_inr) in page, f"{p.name}: price not on the page"
        assert str(escape(p.name)) in page, f"{p.name}: not on the page"
        if p.price_from:
            assert f"<small>from </small>{format_inr(p.price_inr)}" in page


def run_reader(client, rec, ids) -> dict:
    first = None
    for sid in ids:
        case = json.loads((HARD_FIXTURES / f"{sid}.json").read_text(encoding="utf-8"))
        files = None
        if case.get("photo"):
            files = {"photo": (case["photo"], (HARD_FIXTURES / case["photo"]).read_bytes(), "image/jpeg")}
            case["expected_prices"] = list(case["expected_prices"].values())
        n = len(rec.replies)
        r = client.post("/api/businesses", data={"description": case["description"], "price_list": case["price_list"]},
                        files=files, headers={"Origin": ORIGIN})
        assert r.status_code == 201, f"{sid}: {r.status_code} {r.text[:300]}"
        assert "x-assistant-note" not in r.headers, f"{sid}: fell back to a sample ({r.headers['x-assistant-note']})"
        assert len(rec.replies) == n + 1, f"{sid}: {len(rec.replies) - n} live calls (a retry means a bad first reply)"
        biz = r.json()
        raw = rec.replies[-1][1]
        Profile.model_validate(raw)  # the raw reply itself fits our schema
        check_shop(case, Profile.model_validate(biz["profile"]))
        save(f"reader_{sid}", raw)
        first = first or biz
        print(f"reader:{sid}: ok · {biz['profile']['name']!r} · {len(biz['profile']['products'])} items · saved")
    return first


def run_namer(client, rec, biz) -> None:
    r = client.get(f"/api/businesses/{biz['id']}/names")
    assert r.status_code == 200, f"namer: {r.status_code} {r.text[:300]}"
    assert "x-assistant-note" not in r.headers, "namer: fell back to sample names"
    names = r.json()
    assert names and all(n["domain"] and n["price_usd"] is not None for n in names), names
    fixture, raw = rec.replies[-1]
    save("namer_preflight_s11c", raw)  # its own file: tests pin the names in the older namer fixtures
    print(f"namer: ok · {[n['domain'] for n in names]} (asked as {fixture}) · saved")


def run_policy(claude, rec) -> None:
    for case in CASES:
        n = len(rec.replies)
        v = policy_check(claude, Profile.model_validate(case["profile"]))
        assert v.by == "claude" and len(rec.replies) == n + 1, f"policy:{case['id']}: not answered live (by {v.by}: {v.reason})"
        raw = rec.replies[-1][1]
        got = "ok" if v.ok else "held"
        assert case["expect"] in ("any", got), f"policy:{case['id']}: expected {case['expect']}, got {got}: {v.reason}"
        bad = case.get("must_not_contain")
        assert not bad or bad not in json.dumps(raw), f"policy:{case['id']}: obeyed the injected text"
        save("policy_ok" if case["id"] == "normal" else f"policy_{case['id']}", raw)
        print(f"policy:{case['id']}: {got} · {v.reason[:110]!r} · saved")


def run_doctor(client, rec, biz) -> None:
    admin = {"X-Admin-Token": ADMIN_TOKEN}
    csrf = {"Origin": ORIGIN}
    r = client.put(f"/api/businesses/{biz['id']}", json={"profile": biz["profile"], "subdomain": "meera"}, headers=csrf)
    assert r.status_code == 200, r.text[:300]
    p = client.post(f"/api/businesses/{biz['id']}/plans", json={"mode": "sandbox", "domain": None}, headers=csrf)
    assert p.status_code == 201, p.text[:300]
    a = client.post(f"/api/plans/{p.json()['id']}/approve", json={"approved_by": "Preflight"}, headers=csrf)
    assert a.status_code == 200, a.text[:300]
    assert client.get(f"/api/plans/{p.json()['id']}").json()["status"] == "done"
    r = client.put(f"/api/admin/businesses/{biz['id']}/demo-fault", json={"fault": "a_record"}, headers=admin)
    assert r.status_code == 200, r.text[:300]
    n = len(rec.replies)
    assert client.post(f"/api/businesses/{biz['id']}/checks", headers=csrf).status_code == 202
    rep = client.get(f"/api/businesses/{biz['id']}/report").json()
    turns = [(f, d) for f, d in rec.replies[n:] if f.startswith("investigate_site_points")]
    repairs = [x for x in rep["run"]["repairs"] if x.get("doctor")]
    assert turns and repairs, f"the Doctor didn't investigate: {json.dumps(rep['run'])[:600]}"
    d = repairs[0]["doctor"]
    assert d["source"] == "assistant" and d["fix_id"] == "repoint_site" and d["trace"], d
    assert all(c["passed"] for c in rep["run"]["checks"]), [(c["check"], c["passed"]) for c in rep["run"]["checks"]]
    for old in FIXTURE_DIR.glob("investigate_site_points_t*.json"):
        old.unlink()
    for f, data in turns:
        save(f, data)
    looks = ", ".join(t["tool"] for t in d["trace"])
    print(f"doctor:a_record: ok · looked at [{looks}] -> {d['fix_id']} · {d['finding'][:120]!r} · saved {len(turns)} turn(s)")


def main(args: list[str]) -> int:
    if os.environ.get("CLAUDE_MODE") != "live":
        print("Set CLAUDE_MODE=live in this command's environment (not in .env).")
        return 2
    parts = args or ["reader", "namer", "policy", "doctor"]
    readers = [a.split(":", 1)[1] for a in parts if a.startswith("reader:")] or (READERS if "reader" in parts else [])
    base = get_settings()
    db = ROOT / "replay" / "raw" / "preflight_s11c.db"
    settings = Settings(_env_file=None, anthropic_api_key=base.anthropic_api_key, claude_mode="live",
                        claude_model_strong=base.claude_model_strong, claude_model_cheap=base.claude_model_cheap,
                        claude_max_tokens=base.claude_max_tokens, claude_daily_spend_cap_usd=CAP_USD,
                        database_url=f"sqlite:///{db.as_posix()}", use_fakes=True, monitor_enabled=False,
                        admin_token=ADMIN_TOKEN, dev_mode=True, visitor_describes_per_day=1000,
                        visitor_launches_per_day=1000)
    engine = make_engine(settings.database_url)
    init_db(engine)
    with Session(engine) as s:
        before = spent_today_usd(s)
    rec = Recording(LiveClaudeClient(settings, engine))
    claude = FallbackClaudeClient(rec)
    integ = fake_integrations(settings)
    app = create_app(run_lifespan=False)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides.update({get_settings: lambda: settings, get_session: _session, get_claude: lambda: claude,
                                     get_integrations: lambda: integ, get_practice_integrations: lambda: integ})
    status = 0
    with Browser(app) as client:
        try:
            biz = None
            if readers:
                biz = run_reader(client, rec, readers)
            if "namer" in parts or "doctor" in parts:
                if biz is None:  # a shop from a saved reply: no Reader call is spent on it
                    from app.agents.claude_client import FixtureClaudeClient
                    app.dependency_overrides[get_claude] = lambda: FixtureClaudeClient()
                    biz = client.post("/api/businesses", data={"description": "x", "price_list": "y"},
                                      headers={"Origin": ORIGIN}).json()
                    app.dependency_overrides[get_claude] = lambda: claude
            if "namer" in parts:
                run_namer(client, rec, biz)
            if "policy" in parts:
                run_policy(claude, rec)
            if "doctor" in parts:
                run_doctor(client, rec, biz)
        except AssertionError as e:
            print(f"FAILED: {str(e)[:900]}")
            raw = rec.live_client.last_raw
            if raw:
                out = ROOT / "replay" / "raw" / "claude"
                out.mkdir(parents=True, exist_ok=True)
                (out / "preflight_last.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                print("  last raw reply saved to replay/raw/claude/preflight_last.json")
            status = 1
    with Session(engine) as s:
        after = spent_today_usd(s)
    print(f"{len(rec.replies)} live call(s) · spend this run ${after - before:.4f} · this part today ${after:.4f} (cap ${CAP_USD:.2f})")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
