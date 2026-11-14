# LaunchWitness — Build Plan

Milestones in order. Each has tasks and **acceptance criteria** (AC). A milestone is done only when every AC passes. Claude Code: target ACs explicitly at the start of each session.

| Milestone | Target date | Needs credits? |
|---|---|---|
| M0 Scaffold (local) | Nov 14 | No |
| M1 Required basics live | Nov 15 | Yes (VPS, domain, mailbox) |
| M2 Reader + seller site | Nov 16 | No (fixtures; 1–2 live Claude calls) |
| M3 Launch engine | Nov 17 | Uses app domain only |
| M4 Checks, Doctor, report, light monitoring | Nov 18 | Uses app domain; one full launch in the evening |
| M5 Polish, demo, replay, submission | Nov 19–20 | No |

---

## M0 — Scaffold (local, no external calls)

Tasks
- Repo layout per `CLAUDE.md`. `backend/` FastAPI app with `config.py` (pydantic-settings reading `.env`), `db.py`, empty routers.
- `GET /api/health` → `{"ok": true, "env": "<GODADDY_ENV>"}`.
- SQLite models: `Business`, `Plan`, `Approval`, `DnsBackup`, `CheckResult`, `AuditEvent` (fields minimal; can grow).
- Wrapper interfaces with **fake** implementations for tests: `GoDaddyClient`, `ClaudeClient`, `Mailer` (SMTP), `InboxReader` (IMAP), `DnsResolver`.
- `ClaudeClient` supports `CLAUDE_MODE=fixture|live`; fixture mode reads `backend/tests/fixtures/*.json`.
- Spend guard module: `ALLOW_PURCHASE`, `MAX_SPEND_USD`, approval required — with unit tests proving purchase is blocked by default.
- 3 sample seller inputs in `backend/tests/fixtures/sellers/` (Meera's cakes + 2 others: e.g. a home tiffin service, a tailor), each with description + price list text.
- `frontend/` Vite React TS app with one page that calls `/api/health`.
- `deploy/docker-compose.yml` (services: `caddy`, `app`) and `deploy/Caddyfile` (local mode: `localhost`; prod mode: `{$APP_DOMAIN}` + on-demand TLS `ask` → `app:8000/internal/tls-ask`).
- `/internal/tls-ask?domain=` returns 200 only for the app domain, its subdomains in DB, and domains in DB.

AC
- [ ] `docker compose -f deploy/docker-compose.yml up --build` serves the frontend at `http://localhost` and `/api/health` returns ok.
- [ ] `pytest -q` passes; includes tests: purchase blocked by default; tls-ask rejects unknown domains.
- [ ] No real network calls in tests. No secrets in repo; `.env.example` lists every variable.

---

## M1 — Required basics live (hackathon checklist)

Tasks (user does purchases on godaddy.com; Claude Code helps with commands/config)
- VPS: SSH key, Docker installed, repo deployed, `.env` on server only.
- App domain A record (and wildcard `*`) → VPS IP; Caddy HTTPS on the app domain.
- Titan Pro Light mailbox `hello@<APP_DOMAIN>` created (via `gddy`), test email from another account arrives.
- Contact form on the app's own landing page → sends to the mailbox over SMTP (`smtpout.secureserver.net`, full address as username, password from env).

AC
- [ ] `https://<APP_DOMAIN>` loads with a valid certificate.
- [ ] Mailbox receives an external test email.
- [ ] Contact form submission arrives in the mailbox.
- [ ] SMTP password only in server `.env`; `git grep` for it finds nothing.

---

## M2 — Business reader + seller site

Tasks
- Reader agent: one Claude call (strong model) → strict JSON: `name, tagline, about, area, hours, phone/whatsapp, upi_id?, tone, products[{name, price_inr, description, category}]`. Validate with Pydantic; on invalid JSON retry once, then show an error.
- Photo input: accept image upload, send as image block.
- Save 3 real responses as fixtures; UI work uses fixture mode.
- Profile review screen: editable form, save.
- Seller template (`sites/templates/seller.html`): hero, menu grouped by category with prices, about, hours, order form, "Order on WhatsApp" (`https://wa.me/<number>?text=...`), UPI QR (generated server-side from `upi://pay?pa=...&pn=...`), privacy page. Mobile-first, looks professional.
- Host-based routing: request to a domain/subdomain in DB renders that business's site.
- Order form → stores order + emails it (to app mailbox in sandbox/demo).

AC
- [ ] Pasting Meera's fixture input produces a profile; editing a price updates the rendered site.
- [ ] `meera.<APP_DOMAIN>` (or `meera.localhost` locally) shows her site.
- [ ] Order form submission produces an email (fake mailer in tests; real mailbox on server).
- [ ] Total live Claude spend for M2 < $2.

---

## M3 — Launch engine

Tasks
- Namer: cheap-model call → ~10 names; code checks availability (`gddy`/Domains API/OTE/RDAP, whichever works — record choice in PROGRESS) → top 3 with price.
- Planner (code): builds `Plan` = ordered steps + DNS records to add + total cost; renders a before/after DNS diff.
- Approval card UI: domain, cost, each setting in plain words (technical details expandable), Approve button → `Approval` row.
- Executor (code): runs steps in order; **DNS backup before first DNS write**; streams step log to UI (SSE or polling); every step → `AuditEvent`.
- Modes: `sandbox` (subdomain of app domain, no purchase) and `full` (purchase step guarded; demo purchase done manually on godaddy.com, executor then "adopts" the owned domain).
- Mailbox step: create or adopt mailbox; poll until ready; retry on failure (no undo).

AC
- [ ] Sandbox launch of Meera end to end from the UI: name → approve → live site at subdomain with HTTPS.
- [ ] DNS backup JSON exists before any DNS write (test proves ordering).
- [ ] Executor refuses to touch a domain not in DB (test).
- [ ] With `ALLOW_PURCHASE=false`, full mode stops at the purchase step with a clear message (test).

---

## M4 — Launch check, Doctor, report, light monitoring

Tasks
- Checker (code): domain resolves (query GoDaddy authoritative NS directly), HTTPS valid, MX/SPF/DKIM/DMARC present, test order arrives (confirm link + IMAP for demo mailbox), launch finished cleanly.
- Doctor: cheap-model call with the failed check(s) → `{plain_explanation, fix_id}` where `fix_id ∈ playbook`; code applies fix, re-checks; max 3 attempts; refuse + log anything outside playbook.
- Playbook (code): `restore_backup`, `readd_mx`, `readd_email_auth` (SPF/DKIM/DMARC), `retry_certificate`, `repoint_site`.
- Demo fault toggle: admin-only switch that omits/deletes DMARC (or MX) before the check, so the fix shows reliably.
- Launch report page: headline "Your business is ready for customers" (or what's left), each check with result + timestamp, audit log, Doctor sentences.
- Light monitoring: APScheduler — every 15 min site+HTTPS; daily DNS/email match + cert/domain expiry days; re-check once after 1 min before alerting; alerts to owner's personal email; expiry warnings at 30/7/1 days; "Run checks now" button.

AC
- [ ] Full green run on a sandbox launch, report shows all checks with times.
- [ ] With the demo fault on, check fails → Doctor sentence shown → fix applied → re-check green, all in the audit log.
- [ ] Doctor returning a fix outside the playbook is refused (test).
- [ ] "Run checks now" works; scheduled job registered.
- [ ] **Evening:** one full launch of Meera's purchased domain (if budget allows), recorded.

---

## M5 — Polish, demo, replay, submission

Tasks
- UI polish on the 3-minute path; empty/error states in plain English.
- Live-link guards: per-visitor launch limit, max tokens per call, daily Claude spend cap; judges' "try it" = sandbox only.
- `scripts/build-replay.sh` → one combined replay of all Claude Code sessions → served at `https://<APP_DOMAIN>/build`.
- README: what it is, demo link, video, how to run, architecture, safety rules, "How I built this with Claude Code" (links `/build` and `docs/BUILD_LOG.md`).
- Record demo video (script in SPEC §12). Project brief PDF.
- Final check of every hackathon requirement on the live app; secrets scan of repo and replay; submit.

AC
- [ ] Every item in SPEC §11 ready.
- [ ] `/build` replay loads and contains sessions from first to last.
- [ ] `git grep -iE "(api[_-]?key|secret|password)\s*=\s*\S"` finds nothing real.

---

## Stretch (only after M4 is accepted)

1. Full monitoring (daily test order, change detection, incident history)
2. /verify page with DNS TXT proof
3. MCP server over the engine tools
4. Fleet view
