# First Claude Code prompt (Session 1 — M0 Scaffold)

Paste everything below the line into Claude Code, started from the repo root.

---

You're building LaunchWitness with me for the GoDaddy hackathon. Before anything else:

1. Read `CLAUDE.md` fully, then `docs/PROGRESS.md`, then the **M0** section of `docs/BUILD_PLAN.md`. Skim `docs/SPEC.md` sections 5, 8 and 9 (agents, architecture, safety) only.
2. Reply with a short plan for this session: the files you'll create, in order, and which M0 acceptance criteria each step satisfies. Then wait for my OK.

Session goal: **complete M0 (Scaffold, local only).** Nothing in this session calls the real Claude API, GoDaddy, SMTP, IMAP or public DNS — everything external goes through wrapper interfaces with fake implementations, and tests prove it.

Specifics for M0:
- Backend: Python 3.12, FastAPI, SQLModel/SQLite, pydantic-settings reading `.env` (copy `.env.example` → `.env` locally; never commit `.env`).
- Wrappers + fakes: `GoDaddyClient` (ote|prod switch from `GODADDY_ENV`), `ClaudeClient` (`CLAUDE_MODE=fixture|live`, fixture reads `backend/tests/fixtures/`), `Mailer`, `InboxReader`, `DnsResolver`.
- Spend guard module with tests proving purchase is blocked unless `ALLOW_PURCHASE=true` AND cost ≤ `MAX_SPEND_USD` AND an approval exists.
- `/api/health` and `/internal/tls-ask` (with tests: unknown domains rejected).
- Models: Business, Plan, Approval, DnsBackup, CheckResult, AuditEvent (minimal fields).
- 3 sample seller inputs in `backend/tests/fixtures/sellers/` (Meera's home cakes, a home tiffin service, a tailor) — realistic Indian small-business text with ₹ prices.
- Frontend: Vite + React + TS, one page that shows health status.
- `deploy/docker-compose.yml` (caddy + app) and `deploy/Caddyfile` with a local mode and a prod mode (on-demand TLS with `ask` → `/internal/tls-ask`).
- Fill in the "Commands" section of `CLAUDE.md` with the real commands once they work.

Done means every M0 acceptance criterion passes: `docker compose -f deploy/docker-compose.yml up --build` serves the page at http://localhost with health ok, `pytest -q` passes, no real network calls in tests, no secrets in the repo.

At the end of the session: update `docs/PROGRESS.md` (Done, Next = M1, Decisions, Open questions), add a "Session 1" entry to `docs/BUILD_LOG.md` using its template, and commit with messages prefixed `M0:`.
