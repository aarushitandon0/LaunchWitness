"""Restart drill for the local production-like stack (deploy/README.md). Runs INSIDE the app container:

    docker compose ... exec -T app python - < scripts/restart_drill.py start     # practice launch, prints plan id
    docker compose ... exec -T app python - < scripts/restart_drill.py <plan_id> # after the kill: its state

`start` makes a practice shop for a throwaway user straight in the database and approves a practice plan
through the API on localhost:8000 (inside the container, as the shop's owner), so a launch is running when
the caller kills the container. Never touches anything real (practice + pretend world only).
"""

import json
import sys
import urllib.request

from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import Plan

arg = sys.argv[1] if len(sys.argv) > 1 else "start"
engine = get_engine()

if arg == "start":
    from app.accounts import create_session
    from app.models import Business, Membership, User
    from app.safety.access import csrf_for

    s = get_settings()
    with Session(engine) as db:
        u = User(email=f"restart-drill-{__import__('secrets').token_hex(3)}@example.test", status="approved")
        db.add(u)
        db.commit()
        db.refresh(u)
        raw = create_session(db, s, u, "restart-drill")
        profile = json.load(open("tests/fixtures/sellers/meera_cakes.json", encoding="utf-8"))
        b = Business(name="Restart drill", description=profile["description"], subdomain=f"drill{u.id}",
                     practice=True, profile_json=json.dumps({"name": "Restart drill", "products": [
                         {"name": "Cake", "price_inr": 500}]}))
        db.add(b)
        db.commit()
        db.refresh(b)
        db.add(Membership(user_id=u.id, business_id=b.id, role="owner"))
        db.commit()
        bid = b.id

    def call(method, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:8000{path}", method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Origin": s.origin,
                                              "Cookie": f"{s.session_cookie}={raw}", "X-CSRF-Token": csrf_for(raw)})
        return json.load(urllib.request.urlopen(req, timeout=20))

    plan = call("POST", f"/api/businesses/{bid}/plans", {"mode": "sandbox"})
    call("POST", f"/api/plans/{plan['id']}/approve", {"approved_by": "drill"})
    print(plan["id"])
else:
    with Session(engine) as db:
        p = db.exec(select(Plan).where(Plan.id == int(arg))).one()
        steps = json.loads(p.steps_json)
        print(json.dumps({"plan_status": p.status,
                          "messages": [st["message"] for st in steps if st["status"] in ("failed", "running")],
                          "still_running": [st["kind"] for st in steps if st["status"] == "running"]}))
