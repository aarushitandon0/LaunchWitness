"""Make ONE live Claude call per target and save the reply as a fixture.

Targets:
  reader:<seller_id>   sample sellers (tests/fixtures/sellers) and hard cases (tests/fixtures/sellers_hard)
  namer:<seller_id>    uses that seller's saved reader fixture as the profile
  doctor:<check>       a realistic failure of that launch check (doctor:all = every check)

Money rules (session 6): one call per target, never a retry; the run STOPS at
the first failed target so a broken prompt can't burn credit. Every reply is
also written to replay/raw/claude/<fixture>.json (git-ignored) so a bad reply
can be debugged offline instead of paying for another call. All calls go
through LiveClaudeClient (max_tokens, daily cap, ClaudeUsage rows).

Usage (CLAUDE_MODE=live and ANTHROPIC_API_KEY in the environment):
    cd backend && ../.venv/bin/python ../scripts/capture_live_fixtures.py reader:meera_cakes namer:meera_cakes
    ... --dry-run <targets>   worst-case cost per target, no key needed, no call made
    ... --report              today's live spend from the ClaudeUsage table, per fixture
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlmodel import Session, select  # noqa: E402

from app.agents import doctor, namer, reader  # noqa: E402
from app.agents.checker import Outcome  # noqa: E402
from app.agents.claude_client import (FIXTURE_DIR, LiveClaudeClient, call_cost_usd,  # noqa: E402
                                      estimate_input_tokens, spent_today_usd, today_utc)
from app.models import ClaudeUsage  # noqa: E402
from app.agents.playbook import FIXES_FOR  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402

MAX_CALLS = 12
RAW_DIR = ROOT / "replay" / "raw" / "claude"
SELLER_DIRS = [reader.SELLER_FIXTURES, reader.SELLER_FIXTURES.parent / "sellers_hard"]

# Realistic failures, worded exactly as checker.py words them (practice domain meerascakes.in).
DOCTOR_CASES = {
    "site_points": Outcome("site_points", False, "Your address doesn't lead to your website yet.",
                           "A meerascakes.in = nothing; want 203.0.113.10"),
    "https": Outcome("https", False, "Your website's security certificate isn't working yet.",
                     "status=0 cert_valid=False certificate verify failed"),
    "email_mx": Outcome("email_mx", False, "Emails sent to your address can't reach your mailbox.", "MX = nothing"),
    "email_spf": Outcome("email_spf", False, "Your emails may land in spam: the sending permission is missing.",
                         "TXT @ = nothing"),
    "email_dkim": Outcome("email_dkim", False, "Your emails aren't signed, so they may land in spam.",
                          "TXT titan1._domainkey = nothing"),
    "email_dmarc": Outcome("email_dmarc", False, "Order emails could land in spam: a protection setting is missing.",
                           "TXT _dmarc = nothing"),
    "test_order": Outcome("test_order", False, "A test order was sent but hasn't arrived in your inbox.",
                          "order #12 not found in orders@meerascakes.in"),
    "launch_clean": Outcome("launch_clean", False, "Some launch steps didn't finish.",
                            "plan failed; unfinished: ['Set up your mailbox']"),
}


def seller(seller_id: str) -> tuple[dict, Path]:
    for d in SELLER_DIRS:
        p = d / f"{seller_id}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")), d
    raise SystemExit(f"Unknown seller {seller_id}")


def request_for(target: str) -> tuple[str, dict, callable]:
    """-> (fixture name, ask_json kwargs, validator that raises on a bad reply)."""
    agent, _, arg = target.partition(":")
    if agent == "reader":
        s, d = seller(arg)
        image = None
        if s.get("photo"):
            image = ((d / s["photo"]).read_bytes(), "image/jpeg" if s["photo"].endswith(".jpg") else "image/png")
        content = reader.build_user_content(s["description"], s["price_list"], image)
        kw = dict(tier="strong", system=reader.SYSTEM, user=content, schema=reader.PROFILE_SCHEMA)
        return f"reader_{arg}", kw, reader.Profile.model_validate
    if agent == "namer":
        profile = reader.Profile.model_validate_json((FIXTURE_DIR / f"reader_{arg}.json").read_text(encoding="utf-8"))
        kw = dict(tier="cheap", system=namer.SYSTEM, user=namer.namer_user(profile), schema=namer.NAMES_SCHEMA,
                  max_tokens=300)

        def check(data):
            if not namer.clean_names(data.get("names", [])):
                raise ValueError("no usable names")
        return f"namer_{arg}", kw, check
    if agent == "doctor":
        failed = DOCTOR_CASES[arg]
        kw = dict(tier="cheap", system=doctor.SYSTEM, user=doctor.doctor_user(failed), schema=doctor.DIAGNOSIS_SCHEMA,
                  max_tokens=200)

        def check(data):
            if data.get("fix_id") not in FIXES_FOR[arg]:
                raise ValueError(f"fix {data.get('fix_id')!r} not allowed for {arg}")
        return f"doctor_{arg}", kw, check
    raise SystemExit(f"Unknown target {target}")


def report() -> int:
    engine = get_engine()
    init_db(engine)
    with Session(engine) as s:
        rows = s.exec(select(ClaudeUsage).where(ClaudeUsage.day == today_utc())).all()
    total = 0.0
    for r in rows:
        total += r.cost_usd
        print(f"{r.purpose:32} {r.model:18} in={r.input_tokens:6} out={r.output_tokens:5} ${r.cost_usd:.4f}")
    print(f"{len(rows)} call(s) today ({today_utc()} UTC) · total ${total:.4f}")
    return 0


def dry_run(plans, settings) -> int:
    models = {"strong": settings.claude_model_strong, "cheap": settings.claude_model_cheap}
    total = 0.0
    for target, _fixture, kw, _v in plans:
        limit = min(kw.get("max_tokens") or settings.claude_max_tokens, settings.claude_max_tokens)
        est_in = estimate_input_tokens(kw["system"], kw["user"])
        worst = call_cost_usd(models[kw["tier"]], est_in, limit)
        total += worst
        print(f"{target:28} {models[kw['tier']]:18} in<={est_in:5} out<={limit:5} worst ${worst:.4f}")
    print(f"Worst case for all {len(plans)} call(s): ${total:.4f} (cap ${settings.claude_daily_spend_cap_usd:.2f})")
    return 0


def main(args: list[str]) -> int:
    settings = get_settings()
    if args == ["--report"]:
        return report()
    dry = "--dry-run" in args
    targets = [a for a in args if a != "--dry-run"]
    if not dry and settings.claude_mode != "live":
        print("Set CLAUDE_MODE=live to run this.")
        return 2
    targets = [t for x in targets for t in ([f"doctor:{c}" for c in DOCTOR_CASES] if x == "doctor:all" else [x])]
    if not targets or len(targets) > MAX_CALLS:
        print(f"Give 1..{MAX_CALLS} targets.")
        return 2
    plans = [(t, *request_for(t)) for t in targets]  # fail on typos before spending anything
    if dry:
        return dry_run(plans, settings)
    engine = get_engine()
    init_db(engine)
    client = LiveClaudeClient(settings, engine)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with Session(engine) as s:
        before = spent_today_usd(s)
    status = 0
    for target, fixture, kw, validate in plans:
        client.last_raw = None
        try:
            data = client.ask_json(fixture=fixture, **kw)
            validate(data)
        except Exception as e:
            print(f"{target}: NOT saved ({type(e).__name__}: {str(e)[:300]}). Stopping: no more calls this run.")
            status = 1
        else:
            (FIXTURE_DIR / f"{fixture}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                                         encoding="utf-8")
            print(f"{target}: saved {fixture}.json")
        if client.last_raw:
            (RAW_DIR / f"{fixture}.json").write_text(json.dumps(client.last_raw, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
            r = client.last_raw
            print(f"   {r['model']} in={r['input_tokens']} out={r['output_tokens']} ${r['cost_usd']:.4f} stop={r['stop_reason']}")
        if status:
            break
    with Session(engine) as s:
        after = spent_today_usd(s)
    print(f"Spend this run: ${after - before:.4f} · today total: ${after:.4f} (cap ${settings.claude_daily_spend_cap_usd:.2f})")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
