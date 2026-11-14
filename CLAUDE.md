# CLAUDE.md — LaunchWitness

Read this file fully at the start of every session. It is the source of truth for how you work in this repo.

## What we are building

LaunchWitness (working name) — GoDaddy Inclusive Innovation Hackathon 2026, Round 2 (build Nov 13–20, 2026).

> Describe your business. LaunchWitness launches it on GoDaddy and proves everything works before your first customer arrives.

A small seller types a few lines + a price list. LaunchWitness builds her site from one fixed template, buys/points her domain, sets up her email, then **proves** it all works (HTTPS, DNS, email records, a real test order arriving in her inbox), repairs or undoes anything that fails during launch, and keeps lightly checking afterwards.

Full product spec: `docs/SPEC.md`. Milestones and acceptance criteria: `docs/BUILD_PLAN.md`.

## Session ritual (every session, no exceptions)

1. **Start:** read `CLAUDE.md`, then `docs/PROGRESS.md` (current milestone, what's done, what's next, open questions). Only read `docs/SPEC.md` / `docs/BUILD_PLAN.md` sections relevant to today's task.
2. **Before coding:** state in 3–6 bullets what you will do this session and which acceptance criteria from `docs/BUILD_PLAN.md` it targets. Wait for the user's OK if the plan changes anything in `docs/SPEC.md`.
3. **While coding:** small commits, each one working. Run tests before every commit.
4. **End:** update `docs/PROGRESS.md` (move items to Done, set Next, add decisions/open questions) and append one entry to `docs/BUILD_LOG.md` (template inside). Then commit.
5. **Save the transcript:** run `bash scripts/save-transcript.sh <N> <milestone>` (e.g. `2 m2`; set `REDACT_EMAILS=<owner's email>` in the shell, never in a file). It copies this session's transcript to `replay/sessions/<date>-s<N>-<milestone>.jsonl`, redacts the owner's personal email (and any webmail address), replaces each secret-looking value with `[REDACTED]` (strict patterns; code like `password: SecretStr` and base64 screenshot data are not flagged), then re-scans. If anything real-looking remains, it saves nothing and exits 1 — **never commit that transcript**; tell the user which lines matched (it prints line numbers and kinds, never values). Commit the saved file only when the script reports a clean scan. `replay/raw/` stays git-ignored.

## Hard rules

- **No secrets anywhere in the repo.** All keys come from environment variables (see `.env.example`). Never print a secret, never write it to a file other than `.env` (which is git-ignored), never paste it into a commit, test, fixture or log. If you see a secret in a file, stop and tell the user.
- **Never spend money.** Do not run any GoDaddy purchase (domain or email) yourself — not via API, not via `gddy`. Purchases are done by the user on godaddy.com with hackathon credit. In code, purchase paths are guarded by `ALLOW_PURCHASE=false` (default) AND a `MAX_SPEND_USD` cap AND an owner approval record. Never change those defaults.
- **GoDaddy environment:** default `GODADDY_ENV=ote` (sandbox). Production calls only when the user sets `GODADDY_ENV=prod` explicitly. Never write DNS to a domain that is not in the app's own database.
- **Claude API budget is $100 total, for the product only.** During development, do not call the live Claude API for UI work: use saved fixtures in `backend/tests/fixtures/`. Live calls only when a task is specifically about the prompt/agent, and keep `max_tokens` tight. Strong model only for the Reader; cheap model for Namer and Doctor (see env vars).
- **The model never acts alone on money or DNS.** Claude only *decides and explains* (Reader, Namer, Doctor). Plain code *acts and checks* (Planner, Executor, Checker). The Doctor may only pick from the fixed playbook in code.
- **Scope:** build the core features in `docs/BUILD_PLAN.md` order. No stretch item until the user says core is done. Out of scope: payments, inventory, WhatsApp/Instagram APIs, multiple templates, generating custom site code.
- **Don't invent product decisions.** If the spec doesn't answer something, pick the simplest option, write it under "Decisions" in `docs/PROGRESS.md`, and mention it in your end-of-session summary.

## Stack

- Backend: Python 3.12, FastAPI, SQLModel/SQLite, httpx, dnspython, APScheduler, `anthropic` SDK, pytest.
- Frontend: React + Vite + TypeScript, plain CSS (no heavy UI kit).
- Seller sites: server-rendered by FastAPI (Jinja2) from ONE template + the seller's profile, chosen by the `Host` header.
- Infra: one GoDaddy Docker VPS, `docker compose` with `caddy` (HTTPS, on-demand TLS with an `ask` endpoint) + `app` (FastAPI serving API, built frontend and seller sites).
- Email: send via SMTP of the app's one Titan mailbox (`smtpout.secureserver.net`, full address as username, password from env). Read the demo inbox via IMAP (password from env).
- GoDaddy: REST APIs (Domains, DNS, Email) behind one client class, plus `gddy` CLI for manual exploration.

## Repo layout (target)

```
backend/
  app/
    main.py            # FastAPI app, routers, host-based seller site routing
    config.py          # settings from env (pydantic-settings)
    db.py, models.py   # SQLite tables: Business, Plan, DnsBackup, CheckResult, AuditEvent, Approval
    audit.py           # one helper to write AuditEvent rows
    routers/           # health.py (/api/health), internal.py (/internal/tls-ask)
    safety/            # spend_guard.py (ALLOW_PURCHASE + MAX_SPEND_USD + Approval)
    checks/            # dns_resolver.py (public DNS lookups, real + fake)
    agents/            # claude_client.py (fixture|live); reader.py, namer.py, doctor.py (Claude); planner.py, executor.py, checker.py, playbook.py (code)
    integrations.py    # bundle of outside services (fake world or real), FastAPI dependency
    godaddy/           # client.py (ote|prod, scoped DNS writes), availability.py, email.py (mailbox)
    sites/             # templates/seller.html, render.py, hosts.py, routes.py, orders.py
    monitor/           # scheduler.py (light monitoring)
    mail/              # smtp.py, imap.py
  tests/               # pytest; fixtures/ holds saved Claude responses + sample seller inputs
frontend/              # Vite React app
deploy/                # Dockerfile, docker-compose.yml, Caddyfile (local), Caddyfile.prod
docs/                  # SPEC.md, BUILD_PLAN.md, PROGRESS.md, BUILD_LOG.md
scripts/               # build-replay.sh and helpers
```

## Commands (keep this section updated as they become real)

- One-time setup: `cp .env.example .env` · `python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt` · `cd frontend && npm install`
- Backend tests: `cd backend && ../.venv/bin/pytest -q` (or `pytest -q` with `.venv` activated). Tests block all non-local network calls.
- Backend only (dev): `cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000`
- Frontend dev: `cd frontend && npm run dev` (proxies `/api` to :8000) · build: `npm run build` (FastAPI serves `frontend/dist`)
- Run locally (full stack): `docker compose -f deploy/docker-compose.yml up --build` → http://localhost · stop: `docker compose -f deploy/docker-compose.yml down`
- Practice mode: `USE_FAKES=true` (default) runs GoDaddy/DNS/mailbox/HTTP against in-memory fakes; set `SERVER_IP`, `USE_FAKES=false` on the VPS once the real integrations exist (see PROGRESS.md "Real integration TODO").
- Live Claude fixtures (owner's laptop; cloud sessions can't hold the key): `bash scripts/capture_all_live.sh` (17 calls, worst case $0.14, cap must be ≤ $1.50, stops at the first failure; details `docs/LIVE_FIXTURES.md`). Single targets: `cd backend && ../.venv/bin/python ../scripts/capture_live_fixtures.py [--dry-run] reader:<seller> | namer:<seller> | doctor:<check>|all` · spend today: `… --report` · strict check: `REQUIRE_LIVE_FIXTURES=1 pytest -q tests/test_s6_agents.py`. Handwritten test image: `.venv/bin/python scripts/make_handwritten_pricelist.py <out.jpg>`
- Team (admin) access in the browser: set `ADMIN_TOKEN` (16+ chars) in `.env`, open `/#/admin`, paste it. The report page then shows the demo fault switch. Owners use their private link (`/#/b/<id>?key=…`, shown once after "describe").
- Monitoring: on by default (`MONITOR_ENABLED=true`, starts with the app); tests never start it.
- Save session transcript: `bash scripts/save-transcript.sh <N> <milestone>` · build replay page: `REDACT_EMAILS=<owner email> bash scripts/build-replay.sh` → `replay/build.html` (served at `/build`; redacts emails, secret-scans the page, deletes it on any hit). One Claude Code session = one file in `replay/sessions/` (the replay keeps one copy per session id: if a chat continues, replace its earlier partial file).
- Prod on the VPS: follow `docs/RUNBOOK_M1.md`. Start/update: `docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build` (Caddyfile.prod, monitoring on, restart always, healthchecks) · M1 check: `bash scripts/check_m1.sh` · DB backup: `bash scripts/backup_db.sh` (restore: `--restore <file>`)
- Demo rehearsal (practice, needs the app running): `python3 scripts/seed_demo.py [--url URL] [--launched]` · reset: `ADMIN_TOKEN` in env, `python3 scripts/seed_demo.py --reset`
- Seller site gallery (6 very different sellers, phone + laptop screenshots): `.venv/bin/python scripts/render_site_gallery.py <tmp_dir> && node scripts/shoot_site_gallery.js <tmp_dir> docs/screenshots/<session>` (warns on sideways scrolling)
- App pages: `/` landing + contact form · `/#/try` describe · `/#/admin` team access · `/build` replay

## Style

- Small, readable modules; type hints; no clever abstractions.
- Every external call (GoDaddy, Claude, SMTP, IMAP, DNS) goes through one wrapper that can be faked in tests.
- Every action that changes state writes an `AuditEvent` (who/what/when/result).
- User-facing text is plain English a non-technical shop owner understands. No "MX", "A record" etc. in the seller UI — technical detail goes in an expandable "details" area.
- Commit messages: imperative, short, prefixed by milestone, e.g. `M2: add DNS backup before writes`.
