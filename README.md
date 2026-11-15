# LaunchWitness

> **Describe your business. LaunchWitness puts it online on GoDaddy, proves a real order reaches you, fixes what breaks, and keeps checking.**

**Is your shop actually ready for customers?** Built for the GoDaddy Inclusive Innovation Hackathon 2026 (working name).

- **Live app:** `https://launchwitness.com` *(goes live in M1, when the VPS arrives)*. "Try it" runs in practice mode, so nothing is bought.
- **Demo video (3 min):** `<YouTube link>` *(placeholder)*
- **How it was built:** the combined Claude Code session replay at `https://launchwitness.com/build`, plus [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md)

---

## What it is

Meera bakes eggless cakes at home in Pune. Her customers find her on Instagram and order in messages. She has no website and no business email, and "DNS" means nothing to her.

Plenty of tools will make her a website. None of them tell her whether a customer's order will actually reach her. LaunchWitness does that, in this order:

1. **Proof.** Before she shares the link, a **real test order has to arrive in her inbox**. LaunchWitness also checks that the site opens securely and that her email settings are right. The report ends with **"Your business is ready for customers."** only when every check has passed.
2. **The Doctor.** Anything that fails is explained in one plain sentence and repaired from a fixed, safe list of fixes, then checked again. Nothing outside that list can run, and every change is backed up and can be undone.
3. **Watching.** After launch it re-checks her site every 15 minutes and her settings daily, fixes what it safely can, and emails her personal address before something breaks or expires.
4. **Generation, last.** If she has no site yet, she types two lines and pastes her price list (or a photo of it), and LaunchWitness builds a mobile shop with her menu, prices, WhatsApp button and UPI QR, on her own domain with business email.

Most builders stop at "your site is ready". LaunchWitness shows the proof.

## How it works

1. **Describe.** A few lines and a price list (or a photo of it). Claude reads them into an editable profile.
2. **Check.** She fixes anything wrong, then picks a free address or her own name. Claude suggests names, and code checks that they're really available and what they cost.
3. **Approve.** One card shows every step, every setting as before and after, and the exact cost. Nothing happens until she taps Approve.
4. **Launch and prove.** Code backs up DNS, then points the domain, sets up email and turns the site on with HTTPS. Then it runs the checks, including a real test order. Claude's Doctor explains any failure, and code applies a fix from the playbook and re-checks.
5. **Report and watch.** Every check with its result and time, the Doctor's sentences, and the full audit log. The site is re-checked every 15 minutes and the settings daily; expiry warnings go out at 30, 7 and 1 days.

## Safety rules

The model **decides and explains**; plain code **acts and checks**.

- **Approve before spending.** Nothing is bought without the owner's approval of the exact cost. In code, a purchase needs all of these:
  - `ALLOW_PURCHASE=true` (off by default)
  - a cost under the hard cap `MAX_SPEND_USD`
  - a matching approval record from the owner

  Domains are bought by the owner on godaddy.com and then adopted.
- **Preview before changing.** Every DNS change is shown as before and after first.
- **Back up, then undo.** The current records are saved before any DNS write. A write without a backup is refused, and a failed launch can be put back.
- **Scoped actions.** A launch can only touch its own domain (or its own subdomain), one record type and name at a time. The Doctor can only pick from 5 fixes in code (`restore_backup`, `readd_mx`, `readd_email_auth`, `retry_certificate`, `repoint_site`). Anything else is refused and logged. At most 3 attempts are made, and no fix spends money.
- **Everything is audited.** Every state change writes an audit event, shown in the report.
- **Safe public link.**
  - Visitors' businesses are always **practice** (a pretend GoDaddy), even on the real server.
  - There are per-visitor daily limits on describe, launch and contact messages.
  - Each business has a secret owner link; only its hash is stored.
  - Admin is off until a strong `ADMIN_TOKEN` is set.
- **No secrets in the repo.** All keys come from environment variables (`.env` exists only on the server). Transcripts are redacted and secret-scanned before they're committed.

## Architecture

```
            ┌──────────── GoDaddy Docker VPS ────────────┐
 browser ──▶│ Caddy (HTTPS, on-demand TLS + "ask" hook)  │
            │   └─▶ FastAPI app                          │──▶ GoDaddy Domains / DNS / Email APIs
            │        ├─ API + React app (Vite build)     │──▶ Claude API (Reader, Namer, Doctor)
            │        ├─ seller sites (1 Jinja template,  │──▶ Titan SMTP / IMAP (app mailbox)
            │        │   chosen by Host header)          │──▶ public DNS / HTTPS probes
            │        ├─ agents: Planner, Executor,       │
            │        │   Checker, playbook (code)        │
            │        ├─ APScheduler light monitoring     │
            │        └─ SQLite (volume, nightly backup)  │
            └────────────────────────────────────────────┘
```

| Agent | Who | Job |
|---|---|---|
| Reader | Claude (strong model, 1 call) | description + price list (or photo) → profile + site copy |
| Namer | Claude (cheap) + code | suggest ~10 names; code checks availability + price; best 3 |
| Planner | code | steps, before/after DNS diff, cost → approval card |
| Executor | code | runs the approved plan with the guards above; resumable step log |
| Checker | code | address points here (authoritative DNS), HTTPS, MX/SPF/DKIM/DMARC, real test order, launch clean |
| Doctor | Claude (cheap) + code | one plain sentence + a fix id from the playbook; code applies and re-checks |

Every outside service (GoDaddy, Claude, SMTP, IMAP, DNS, HTTPS) sits behind one wrapper with an in-memory fake. Tests block all real network calls.

**Stack:** Python 3.12, FastAPI, SQLModel/SQLite, httpx, dnspython, APScheduler, `anthropic` SDK, pytest · React + Vite + TypeScript, plain CSS · Caddy · Docker Compose.

## Run it

Locally in practice mode (fakes for GoDaddy, DNS, mailbox and HTTPS; saved Claude responses, so no keys are needed):

```bash
cp .env.example .env
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm install && npm run build)
cd backend && ../.venv/bin/pytest -q                      # tests (no network)
../.venv/bin/uvicorn app.main:app --port 8000             # http://localhost:8000
```

Or the full stack with Caddy: `docker compose -f deploy/docker-compose.yml up --build` → http://localhost

Rehearse the demo:
- `python3 scripts/seed_demo.py --launched` creates Meera's shop and runs a practice launch.
- `--reset` removes it.
- For the demo fault (DMARC removed, then fixed by the Doctor): set `ADMIN_TOKEN` to 16+ characters, open `/#/admin`, then use the switch on the report.

Production on the VPS: follow [`docs/RUNBOOK_M1.md`](docs/RUNBOOK_M1.md) (copy-paste steps with a check after each). `scripts/check_m1.sh` verifies the result, and `scripts/backup_db.sh` backs up and restores the database. More commands are in [`CLAUDE.md`](CLAUDE.md).

## How I built this with Claude Code

The whole product was built in Claude Code sessions, each one following a fixed ritual written in [`CLAUDE.md`](CLAUDE.md):
1. Claude reads the progress file and proposes a plan mapped to the acceptance criteria.
2. It waits for my OK before coding.
3. It makes small, tested commits.
4. At the end it updates [`docs/PROGRESS.md`](docs/PROGRESS.md) and [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md), then saves a redacted transcript.

- **I make the product decisions**: scope, safety rules, budget, and what to postpone. Claude asks when the spec doesn't answer something and records the answer under "Decisions". For example: no accounts but a secret owner link; a "Pretend I bought it" button for practice; the email plan shown as a separate estimate.
- **Hard rules hold across sessions**:
  - no secrets in the repo
  - Claude never spends money
  - GoDaddy defaults to the sandbox
  - $0 of live Claude calls during development (saved fixtures instead)
- **Every feature session ends with a real-browser check at phone width.** These checks caught real bugs, for example practice launches linking to a pretend domain that could be someone else's site.
- **The full record**: every session's transcript is replayed at `/build` (built with `scripts/build-replay.sh` from the redacted, secret-scanned copies in `replay/sessions/`). The human-written summary per session is in [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md).

## Docs

- [`docs/SPEC.md`](docs/SPEC.md): product spec
- [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md): milestones and acceptance criteria
- [`docs/PROGRESS.md`](docs/PROGRESS.md): status, decisions, real-integration TODO
- [`docs/RUNBOOK_M1.md`](docs/RUNBOOK_M1.md): going live on the VPS
- [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md): one-page brief (draft for the PDF)
