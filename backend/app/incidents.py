"""Incident timeline per shop (S12): each failure → investigation → fix → re-check becomes one entry in plain
words, built only from stored rows (CheckRun, CheckResult, the Doctor's stored trace). No Claude call.

Status of an entry: "open" (still failing, nothing decided yet), "fixed" (a later check passed), "needs_you"
(the Doctor handed it to the owner), "keeps_breaking" (automatic fixing stopped for the day).
"Couldn't check" / "couldn't finish" results are not incidents: they say nothing about the shop.

`public=True` (the shared report) leaves out the owner's instructions and every technical value; the entries
never contain customer data (no order numbers, names or addresses: only check titles and the Doctor's sentences).
"""

import json
from datetime import timedelta

from sqlmodel import Session, select

from app.agents.checker import TITLES
from app.models import CheckResult, CheckRun, utcnow

DAYS = 30
MAX_RUNS = 400
MAX_ENTRIES = 20

FIX_WORDS = {
    "repoint_site": "We pointed your address at your shop again",
    "retry_certificate": "We asked for a new security certificate (the padlock)",
    "readd_mx": "We re-added the email settings we made at launch",
    "readd_email_auth": "We re-added the email protection settings we made at launch",
    "restore_backup": "We put your settings back the way they were before the launch",
}
LOOK_WORDS = {
    "resolve": "Looked up where your address leads",
    "fetch": "Opened your shop page",
    "evidence": "Read the proof stored for this check",
    "smtp_test": "Tried signing in to our mail service (sent nothing)",
    "mailbox_status": "Checked that our mailbox is active",
}


def _iso(v) -> str | None:
    return v.replace(tzinfo=None).isoformat() + "Z" if v else None


def _plain(r: CheckResult) -> tuple[str, bool]:
    d = json.loads(r.detail) if r.detail.startswith("{") else {"plain": r.detail}
    return d.get("plain", ""), bool(d.get("unfinished"))


def timeline(session: Session, business_id: int, *, public: bool = False) -> list[dict]:
    since = utcnow() - timedelta(days=DAYS)
    runs = session.exec(select(CheckRun).where(CheckRun.business_id == business_id, CheckRun.status == "done",
                                               CheckRun.started_at >= since)
                        .order_by(CheckRun.id.desc()).limit(MAX_RUNS)).all()[::-1]
    if not runs:
        return []
    results = session.exec(select(CheckResult).where(CheckResult.run_id.in_([r.id for r in runs]))
                           .order_by(CheckResult.id)).all()
    by_run: dict[int, list[CheckResult]] = {}
    for r in results:
        by_run.setdefault(r.run_id, []).append(r)

    open_: dict[str, dict] = {}
    done: list[dict] = []
    for run in runs:
        repairs = {x["check"]: x for x in json.loads(run.repairs_json or "[]")}
        rows = by_run.get(run.id, [])
        for check in dict.fromkeys(r.check for r in rows):
            mine = [r for r in rows if r.check == check]
            first, last = mine[0], mine[-1]
            plain, unfinished = _plain(first)
            if unfinished:
                continue  # we didn't know: not an incident
            inc = open_.get(check)
            if first.passed and inc is None:
                continue
            if first.passed:  # it was open and now passes without anything this run
                inc["steps"].append({"at": _iso(first.created_at), "what": "Checked again: working"})
                inc["status"], inc["closed_at"] = "fixed", _iso(first.created_at)
                done.append(open_.pop(check))
                continue
            if inc is None:
                inc = {"check": check, "title": TITLES.get(check, check), "opened_at": _iso(first.created_at),
                       "closed_at": None, "status": "open", "steps": []}
                open_[check] = inc
                inc["steps"].append({"at": _iso(first.created_at), "what": f"Failed: {plain}"})
            elif inc["steps"][-1]["what"] != f"Still failing: {plain}":
                inc["steps"].append({"at": _iso(first.created_at), "what": f"Still failing: {plain}"})
            doctor = next((json.loads(r.doctor_json) for r in mine if r.doctor_json), None)
            rep = repairs.get(check, {})
            if doctor:
                looks = [LOOK_WORDS.get(t.get("tool", ""), "Looked") for t in doctor.get("trace", [])]
                if looks:
                    inc["steps"].append({"at": _iso(first.created_at), "what": " → ".join(looks)})
                if doctor.get("finding"):
                    inc["steps"].append({"at": _iso(first.created_at), "what": f"Found: {doctor['finding']}"})
            for a in rep.get("attempts", []):
                if a.get("applied") and a.get("fix_id") in FIX_WORDS:
                    inc["steps"].append({"at": _iso(last.created_at), "what": FIX_WORDS[a["fix_id"]]})
            if last.passed:
                inc["steps"].append({"at": _iso(last.created_at), "what": "Checked again: working"})
                inc["status"], inc["closed_at"] = "fixed", _iso(last.created_at)
                done.append(open_.pop(check))
            elif rep.get("keeps_breaking"):
                inc["status"] = "keeps_breaking"
            elif doctor and doctor.get("fix_id") == "needs_owner":
                inc["status"] = "needs_you"
                if not public and doctor.get("owner_instruction"):
                    inc["next"] = doctor["owner_instruction"]
            else:
                inc["status"] = "open"
    entries = list(open_.values()) + done
    entries.sort(key=lambda e: e["opened_at"] or "", reverse=True)
    for e in entries:
        e["steps"] = e["steps"][:12]
    return entries[:MAX_ENTRIES]
