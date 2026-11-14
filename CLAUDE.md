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
    agents/            # claude_client.py (fixture|live); reader.py, namer.py, doctor.py (Claude); planner.py, executor.py, checker.py (code)
    godaddy/           # client.py (ote|prod), dns.py, domains.py, email.py
    sites/             # templates/seller.html, render.py
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
- Prod on the VPS (HTTPS + on-demand TLS): set `APP_DOMAIN` and `CADDYFILE=Caddyfile.prod` in `.env`, then `docker compose --env-file .env -f deploy/docker-compose.yml up -d --build`

## Style

- Small, readable modules; type hints; no clever abstractions.
- Every external call (GoDaddy, Claude, SMTP, IMAP, DNS) goes through one wrapper that can be faked in tests.
- Every action that changes state writes an `AuditEvent` (who/what/when/result).
- User-facing text is plain English a non-technical shop owner understands. No "MX", "A record" etc. in the seller UI — technical detail goes in an expandable "details" area.
- Commit messages: imperative, short, prefixed by milestone, e.g. `M2: add DNS backup before writes`.
