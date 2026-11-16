"""Capture the investigating Doctor's LIVE tool loop for the three staged faults (S11), as fixtures
`backend/tests/fixtures/claude/investigate_<check>_t<turn>.json` (one file per turn).

Run on the owner's laptop:  cd backend && CLAUDE_MODE=live ../.venv/Scripts/python ../scripts/capture_doctor_investigation.py [--dry-run] [--cap 0.30]
S12 (parked-page fault + "Describe the problem", 5 conversations, cap $0.10):  … capture_doctor_investigation.py --s12 [--dry-run]

The tools are NOT run for real here: each fault has the exact results the pretend world gives in the tests
(same shop `meera.localhost`, same texts), so the saved turns replay against that world. Only Claude is live.
Stops at the first fault whose answer isn't the expected action; that fault's files are not written.
Never prints the key. Spend is recorded in the app's ClaudeUsage table like every other call.
"""

import json
import os
import sys

sys.path.insert(0, os.getcwd())

from sqlmodel import Session, select  # noqa: E402

from app.agents import investigator as inv  # noqa: E402
from app.agents.checker import Outcome  # noqa: E402
from app.agents.claude_client import (  # noqa: E402
    FIXTURE_DIR,
    LiveClaudeClient,
    call_cost_usd,
    estimate_input_tokens,
    today_utc,
)
from app.agents.playbook import fixes_for  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine, init_db  # noqa: E402
from app.models import ClaudeUsage  # noqa: E402

HOST, IP, MODE = "meera.localhost", "127.0.0.1", "sandbox"
GOOD_A = f"A {HOST} = {IP} (authoritative; our server is {IP})"
GOOD_PAGE = "status=200 certificate_valid=True shop_marker=present"
SCENARIOS = {
    "site_points": {
        "failed": Outcome("site_points", False, "Your address doesn't lead to your website yet.",
                          f"A {HOST} = nothing; want {IP}"),
        "tools": {"resolve": f"A {HOST} = nothing (authoritative; our server is {IP})",
                  "fetch": "status=None certificate_valid=True ConnectTimeout",
                  "evidence": "no proof steps stored for this run yet"},
        "expect": "repoint_site",
    },
    "test_order": {
        "failed": Outcome("test_order", False, "Your order form works, but we couldn't send the order email.",
                          "order LW-A39WX6PC: mail server refused or unreachable"),
        "tools": {"smtp_test": "login refused: the mail service did not accept our sign-in",
                  "resolve": GOOD_A, "fetch": GOOD_PAGE,
                  "evidence": "site_points:dns_answer, https:http_response, test_order:form_post"},
        "expect": inv.NEEDS_OWNER,
    },
    "https": {
        "failed": Outcome("https", False, "Your website's security certificate isn't working yet.",
                          "status=None cert_valid=False certificate verify failed"),
        "tools": {"fetch": "status=None certificate_valid=False certificate verify failed",
                  "resolve": GOOD_A, "evidence": "site_points:dns_answer"},
        "expect": "retry_certificate",
    },
}
MARKER_PAGE = "status=200 certificate_valid=True shop_marker=MISSING"
# S12 (--s12): the fourth staged fault (a parked page) and the "Describe the problem" box. Cap $0.10.
S12 = {
    "https_marker": {
        "failed": Outcome("https", False, "Your address opens a page, but it isn't your shop.",
                          "status=200 cert_valid=True; shop marker missing (page status 200)"),
        "tools": {"fetch": MARKER_PAGE, "resolve": GOOD_A, "evidence": "site_points:dns_answer"},
        "expect": "repoint_site", "symptom": "",
    },
    "site_points_symptom": {**SCENARIOS["site_points"], "symptom": "My shop doesn't open"},
    "https_symptom": {**SCENARIOS["https"], "symptom": "Customers see a security warning"},
    "https_marker_symptom": {"failed": Outcome("https", False, "Your address opens a page, but it isn't your shop.",
                                               "status=200 cert_valid=True; shop marker missing (page status 200)"),
                             "tools": {"fetch": MARKER_PAGE, "resolve": GOOD_A},
                             "expect": "repoint_site", "symptom": "My address opens someone else's page"},
    "test_order_symptom": {**SCENARIOS["test_order"], "symptom": "Order emails aren't reaching me"},
}
DEFAULT_TOOLS = {"smtp_test": "ok: connected and signed in", "mailbox_status": "mailbox active"}


def spent(engine) -> float:
    with Session(engine) as s:
        rows = s.exec(select(ClaudeUsage).where(ClaudeUsage.day == today_utc())).all()
    return sum(r.cost_usd for r in rows if r.purpose.startswith("investigate_"))


def main(args: list[str]) -> int:
    settings = get_settings()
    s12 = "--s12" in args
    scenarios = S12 if s12 else SCENARIOS
    cap = float(args[args.index("--cap") + 1]) if "--cap" in args else (0.10 if s12 else 0.30)
    turns = inv.MAX_TOOL_CALLS + 1
    longest = max(inv.investigator_user(sc["failed"], MODE, "", [{"tool": "resolve", "args": {}, "short_result": "x" * 200}] * 4)
                  for sc in scenarios.values())
    worst = len(scenarios) * turns * call_cost_usd(settings.claude_model_cheap,
                                                   estimate_input_tokens(inv.SYSTEM, longest), inv.TOKENS_PER_TURN)
    print(f"{len(scenarios)} faults x up to {turns} turns on {settings.claude_model_cheap}: worst case ${worst:.4f} (cap ${cap:.2f})")
    if worst > cap:
        print("Worst case is over the cap: not running.")
        return 2
    if "--dry-run" in args:
        return 0
    if settings.claude_mode != "live":
        print("Set CLAUDE_MODE=live to run this.")
        return 2
    engine = get_engine()
    init_db(engine)
    before = spent(engine)
    live = LiveClaudeClient(settings, engine)
    for key, sc in scenarios.items():
        check, symptom = sc["failed"].check, sc.get("symptom", "")
        var = inv.variant(sc["failed"], symptom)
        replies: list[dict] = []

        def ask(turn: int, user: str, check=check, var=var, replies=replies) -> dict:
            data = live.ask_json(fixture=inv.fixture_name(check, turn, var), tier="cheap", system=inv.SYSTEM, user=user,
                                 schema=inv.ANSWER_SCHEMA, max_tokens=inv.TOKENS_PER_TURN)
            replies.append(data)
            return data

        def tool(name: str, data: dict, sc=sc) -> dict:
            args_ = {k: data.get(k) for k in inv.TOOL_ARGS.get(name, ()) if data.get(k) not in (None, "")}
            result = sc["tools"].get(name) or DEFAULT_TOOLS[name]
            if name == "fetch" and str(args_.get("url", "")).rstrip("/") != f"https://{HOST}":
                result = "refused: only this shop's own https address can be opened"  # as the real tool would
            if name == "resolve" and str(args_.get("name", "")).lower().rstrip(".") != HOST:
                result = "refused: only this shop's own address can be looked up"
            return {"tool": name, "args": args_, "short_result": result}

        data, trace = inv.loop(ask, sc["failed"], MODE, symptom, tool, HOST)
        fix = data.get("fix_id")
        looks = ", ".join(t["tool"] for t in trace) or "none"
        print(f"{key}: looked at [{looks}] -> {fix!r}: {str(data.get('finding', ''))[:160]}")
        ok = fix == sc["expect"] and (fix == inv.NEEDS_OWNER or fix in fixes_for(check, MODE)) and trace
        if not ok:
            print(f"  NOT SAVED: expected {sc['expect']!r} after at least one look. Spent so far ${spent(engine) - before:.4f}")
            return 1
        for old in FIXTURE_DIR.glob(f"investigate_{check}{var}_t*.json"):
            old.unlink()
        for turn, reply in enumerate(replies):
            (FIXTURE_DIR / f"{inv.fixture_name(check, turn, var)}.json").write_text(
                json.dumps(reply, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"  saved {len(replies)} turn(s)")
    print(f"Real spend for this capture: ${spent(engine) - before:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
