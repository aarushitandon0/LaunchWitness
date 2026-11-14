# PROGRESS — master status

Claude Code reads this at the start of every session and updates it at the end. Keep it short and current; history goes in `BUILD_LOG.md`.

## Current milestone

**M3 — Launch engine: code done against fakes**; the only open M3 AC needs real infra. **M4: code-only parts done** (Checker, playbook, Doctor in fixture mode); report UI + monitoring not started. M0 done · M2 done · **M1 postponed** until GoDaddy credit is confirmed (decided 2026-11-14: M2 first, all local, then M1 once purchases are done).

## Next up

1. **M1** once credit is confirmed: user buys VPS, app domain, Titan mailbox on godaddy.com; deploy prod mode; wildcard `*.<APP_DOMAIN>` A record → VPS.
2. **Fable session — plug in real integrations** (list below), then flip `USE_FAKES=false` on the VPS and do the M3 AC1 sandbox launch with real HTTPS.
3. **Live Claude fixtures** (needs an API key; user approves each call): `scripts/capture_reader_fixtures.py` (3 Reader calls), then Namer and Doctor fixtures. All current Claude fixtures are **placeholders** (see below).
4. **M4 rest**: launch-check endpoint + "Run checks now", launch report page, demo fault toggle, light monitoring (APScheduler).

## ⚠️ Placeholder Claude fixtures (no live Claude call has been made yet)

Every file in `backend/tests/fixtures/claude/` is **hand-written** and carries a `_note` key saying so:
`reader_meera_cakes.json`, `reader_tiffin_service.json`, `reader_tailor.json` · `namer_meera_cakes.json`, `namer_tiffin_service.json`, `namer_tailor.json` · `doctor_<check>.json` ×8.
Replace the Reader ones with `cd backend && CLAUDE_MODE=live ../.venv/bin/python ../scripts/capture_reader_fixtures.py` (exactly 1 call per seller, ≈ $0.02 each, guarded by the daily cap). Live Claude spend so far: **$0.00**.

## Real integration TODO (Fable session)

Everything below is behind an interface with a working fake; tests cover the fakes. Fill these in, then set `USE_FAKES=false`. Do not change the guards (backup-before-write, domain-in-DB, spend guard).

| # | What | File → function | Notes |
|---|---|---|---|
| 1 | Domain availability + price | `backend/app/godaddy/availability.py` → `GoDaddyAvailabilityChecker.check(domains) -> list[Quote]` | Method not chosen (prod Availability API needs 50+ domains/spend; options: `gddy`, OTE, RDAP + fixed price table). Record the choice in Decisions. `Quote.price_usd` = first-year price in USD. |
| 2 | Is the domain in our account? | `backend/app/godaddy/client.py` → `GoDaddyClient.is_owned` | Implemented as `GET /v1/domains/{domain}` (404 = not owned); verify status values against the real account. |
| 3 | Scoped DNS writes | `GoDaddyClient.set_records` / `delete_records` | Implemented as `PUT/DELETE /v1/domains/{d}/records/{type}/{name}` (tests with a mock transport only). Verify on the app domain in OTE first, then prod. |
| 4 | Purchase | `GoDaddyClient.purchase_domain` | **Intentionally raises** `PurchaseNotSupported`: owner buys on godaddy.com, executor adopts on Resume. Leave as is unless the user says otherwise. |
| 5 | Mailbox (Titan) | `backend/app/godaddy/email.py` → `TitanMailboxProvider.find / create / status / dkim` | Via GoDaddy Email API or `gddy`. `dkim(domain)` must return `(record name, TXT value)`; planner assumes name `titan1._domainkey` (executor fails safely if different). Confirm `TITAN_MX` / `TITAN_SPF` values for GoDaddy-sold Titan. |
| 6 | Authoritative DNS lookups | `backend/app/integrations.py` → `real_integrations()` (`dns=RealDnsResolver(...)`) | Pass GoDaddy's authoritative nameserver IPs (`ns*.domaincontrol.com`, from the zone's NS records) so checks don't hit caches. |
| 7 | HTTPS probe | `backend/app/checks/http_probe.py` → `RealHttpProbe.fetch` | Implemented with httpx (cert verification on); verify a bad cert maps to `cert_valid=False` against a real host. |
| 8 | Certificate retry | `backend/app/agents/playbook.py` → `retry_certificate` | Currently re-requests the site (Caddy on-demand TLS retries on request). Optionally call Caddy's admin API. |
| 9 | Test-order arrival (demo mailbox) | `backend/app/mail/imap.py` → `ImapInboxReader.find` | Exists; verify against the real Titan inbox. For real sellers, add the "Yes, I got it" confirm link (SPEC §6) — not built. |
| 10 | Server config | `.env` on VPS | `SERVER_IP=<VPS IP>`, `APP_DOMAIN`, `APP_BASE_URL=https://<APP_DOMAIN>`, `USE_FAKES=false`, SMTP/IMAP passwords. |
| 11 | Live Claude | `backend/app/agents/claude_client.py` → `LiveClaudeClient` | Done (cap + max_tokens + usage table). Only needs `ANTHROPIC_API_KEY` + `CLAUDE_MODE=live`. |

## Done

- 2026-11-14: Idea, spec, plan finalized (`docs/SPEC.md`, `docs/BUILD_PLAN.md`).
- 2026-11-14: **M0 Scaffold** — all 3 ACs pass:
  - AC1: stack up via compose; `http://localhost` serves the React page showing "LaunchWitness is running and ready", `/api/health` → `{"ok":true,"env":"ote"}`, `/internal/*` returns 404 through Caddy. Both Caddyfiles pass `caddy validate`. *Caveat:* in the Claude Code cloud sandbox `pip`/`npm` inside `docker build` can't trust the sandbox's egress-proxy CA, so the image was built there with a scratch-only copy of the Dockerfile that mounts the CA as a build secret (only difference: two `RUN` lines), then `compose up`. The repo Dockerfile is unchanged and should build as-is on a normal machine/VPS.
  - AC2: `pytest -q` → 52 passed, incl. purchase blocked by default (+ cap, approval, reuse cases) and tls-ask rejecting unknown domains.
  - AC3: autouse test guard blocks every non-local socket connect/UDP send/DNS lookup and clears proxy env vars; each real wrapper has a test proving it can't reach the network. Secret scan clean; a test checks `.env.example` lists every setting.

- 2026-11-14: **M2 Reader + seller site** — ACs:
  - AC1 ✅ Meera's sample input → profile (fixture mode); editing a price on the review screen updates the rendered site (test + browser check).
  - AC2 ✅ `meera.localhost` shows her site (test + Playwright at iPhone width).
  - AC3 ✅ order form → stored `Order` + email via Mailer (FakeMailer in tests; real SMTP on the server once M1 is live).
  - AC4 ✅ live Claude spend for M2 = $0 (< $2). Live client enforces `CLAUDE_MAX_TOKENS` and `CLAUDE_DAILY_SPEND_CAP_USD` (13 tests). Reader fixtures are still placeholders (user had no API key).
- 2026-11-14: **M3 Launch engine (fakes)** — ACs:
  - AC1 ⏳ **PENDING REAL INFRA**: sandbox launch name → approve → done works end to end from the UI against the fake world (test + Playwright); "live site at subdomain with HTTPS" needs the VPS + Caddy (test marked skip).
  - AC2 ✅ DNS backup exists before any DNS write (ordering tests; a write without a backup is refused).
  - AC3 ✅ executor refuses domains/labels not in the DB for this business (tests, incl. domain removed after approval).
  - AC4 ✅ `ALLOW_PURCHASE=false` → full mode stops at the purchase step with a clear message; nothing bought, no DNS touched (test). Owner buys manually → Resume adopts the domain and finishes (test).
- 2026-11-14: **M4 code-only parts (fakes)**: Checker (8 checks), playbook (5 fixes), Doctor in fixture mode with max 3 attempts. AC3 ✅ Doctor fix outside the playbook is refused and logged, nothing changes (test). Missing-DMARC → explained → fixed → re-check green, all audited (test).
- Tests: 183 passed, 1 skipped (the real-infra HTTPS AC).

## Environment status

| Item | Status | Notes |
|---|---|---|
| GoDaddy developer account + `gddy` CLI | ? | Run `gddy tree` to confirm |
| GoDaddy credit confirmed by organizers | Waiting | Don't buy before confirmation |
| Docker VPS (4 vCPU / 8 GB, $0) | Not bought | |
| App domain | Not chosen | |
| Titan Pro Light mailbox hello@ | Not bought | |
| Meera's demo domain | Optional | Only if credit left |
| Claude API key ($100, product only) | ? | |
| OTE (sandbox) API keys | ? | |
| Availability check method | Undecided | gddy / Domains API / OTE / RDAP — interface + fake ready (`GoDaddyAvailabilityChecker` stub) |

## Decisions

- 2026-11-14: Name is LaunchWitness (working name, may change).
- 2026-11-14: Hero = launch + proof before first customer; repair happens during launch; light monitoring is core, full monitoring is stretch.
- 2026-11-14: Hosting = GoDaddy Docker VPS (Option B), FastAPI + React + Caddy + SQLite.
- 2026-11-14: Claude API $100 is for the product only; dev uses fixtures.
- 2026-11-14: Build process shown via one combined claude-replay page at `/build` + `docs/BUILD_LOG.md`.
- 2026-11-14 (M0): Caddy mode chosen by `CADDYFILE` (`Caddyfile` = local HTTP on `:80`, any host; `Caddyfile.prod` = `{$APP_DOMAIN}` auto-HTTPS + on-demand TLS for everything else, `ask` → `http://app:8000/internal/tls-ask`). Added `CADDYFILE` to `.env.example`.
- 2026-11-14 (M0): `/internal/*` is answered with 404 by Caddy in both modes; only Caddy reaches it over the Docker network. App port 8000 is not published.
- 2026-11-14 (M0): tls-ask allows exactly: `APP_DOMAIN`, `<Business.subdomain>.APP_DOMAIN` (one label), and `Business.domain` (exact match). `www.<seller domain>` is NOT allowed yet (see open questions).
- 2026-11-14 (M0): Spend guard = `ALLOW_PURCHASE` AND `0 < cost ≤ MAX_SPEND_USD` AND an unused `Approval` for the same business + action + target whose amount covers the cost. `mark_used()` after purchase. Every allow/block writes an `AuditEvent`. `GoDaddyClient` has no purchase method yet.
- 2026-11-14 (M0): Wrapper pattern = a `Protocol` + real class + `Fake*` class per external service. Claude fixtures live at `backend/tests/fixtures/claude/<agent>_<case>.json` and are copied into the Docker image so fixture mode works in the container.
- 2026-11-14 (M0): `RealDnsResolver` returns `[]` for NXDOMAIN / no answer / timeout (a check treats that as "not found").
- 2026-11-14 (M0): Python deps pinned in `backend/requirements.txt` (+ `requirements-dev.txt`); frontend pinned (React 18.3, Vite 5.4). App container runs as non-root; SQLite on the `app-data` volume.

- 2026-11-14 (M2): Reader output = `Profile` (name, tagline, about, area, hours, phone, whatsapp, upi_id, tone, products[name, price_inr, description, category]); structured output via `output_config` JSON schema; thinking off (`between_tools`) on Sonnet 5.5 to save tokens. One retry on invalid JSON *or* failed validation, then a plain-English error.
- 2026-11-14 (M2): Fixture-mode Reader picks `reader_<seller>` by matching the input to a sample seller, else Meera's.
- 2026-11-14 (M2): Daily cap check = today's recorded spend + worst case for the call (estimated input + full `max_tokens` output) must fit; unknown model prices are refused. Prices in code: Sonnet 5.5 $2/$10, Haiku 5.5 $0.10/$0.50 per MTok.
- 2026-11-14 (M2): Photos: JPG/PNG/WebP/GIF up to 5 MB.
- 2026-11-14 (M2): Orders are emailed to the app mailbox (`SMTP_USER`) only; the order is saved even if the email fails (`email_status=failed`, shown on the review screen). Order form = quantity per menu item + note + name + phone (≥10 digits); honeypot field against bots. No payment taken.
- 2026-11-14 (M2): WhatsApp link uses `whatsapp`, else `phone`; 10-digit numbers get `91`. UPI QR = server-side SVG (segno) of `upi://pay?pa=…&pn=…&cu=INR`; hidden when no UPI ID.
- 2026-11-14 (M2): Default site address = slug of the business name (unique, reserved words blocked); seller can edit it on the review screen. Unknown `<label>.APP_DOMAIN` → "site isn't set up" 404, other unknown hosts → the app.
- 2026-11-14 (M3): `USE_FAKES=true` by default (practice mode, banner in the UI): one in-memory fake world per process. `SERVER_IP` setting added (default `127.0.0.1`).
- 2026-11-14 (M3): DNS writes are one (type, name) at a time (`set_records`/`delete_records`); whole-zone replace removed. Existing TXT @ values are kept when SPF is added.
- 2026-11-14 (M3): Sandbox launch = backup app zone → A `<sub>` → `SERVER_IP` → use app mailbox → wait for authoritative DNS → live. Full launch = get domain (adopt if owned, else guarded purchase) → backup → A @ → mailbox `orders@<domain>` → MX/SPF/DKIM/DMARC → wait → live. DMARC = `v=DMARC1; p=quarantine; adkim=r; aspf=r`.
- 2026-11-14 (M3): Total cost on the card = domain price only (mailbox plan is bought separately on godaddy.com; the step only creates/adopts the mailbox). Approve re-checks the price; any increase → re-review.
- 2026-11-14 (M3): Approve writes `Approval(action="launch")` (+ `buy_domain` when there's a cost) and sets `Business.domain` — that's when a domain becomes "in the app's database". Step log = `Plan.steps_json`, UI polls every second. Failed/blocked plans can be resumed; finished steps are skipped.
- 2026-11-14 (M4): Doctor must pick a fix that is in the playbook AND listed for that check (`FIXES_FOR`); else refused + logged. Sandbox launches run site checks only (site, HTTPS, test order, launch clean); email checks are for full launches.

- 2026-11-14 (session 2): Transcript scrubber (`scripts/transcript_scrub.py`, called by `save-transcript.sh`) redacts values instead of dropping the whole transcript: emails → `[redacted-email]`, key/secret values → `[REDACTED]`; skips base64 image data and code-annotation values (`SecretStr`, `settings.…`, `self.…`, env lookups, type names); an independent re-scan refuses to save if anything remains. It over-redacts code/test text that *talks about* secrets (safe direction). Session 2 transcript saved as `replay/sessions/2026-11-14-s2-m2-m3.jsonl`.

## Open questions

- Should seller sites also answer on `www.<domain>` (needs tls-ask + DNS change)? Currently no.
- Mailbox cost: should the approval card include the Titan plan price (and the purchase go through the spend guard), or stay "bought separately"?
- Owner authentication: the review/launch API has no login yet — anyone with the app URL can edit any business. Needed before judges get a public "try it" link (M5).

- Does the credit cover domain + Pro Light fully? Exact cart total?
- Are hackathon accounts whitelisted for production Domains/DNS APIs, or use `gddy`?
- Is a demo video expected in the submission? (Include one anyway.)
- One current India-specific stat on small businesses without websites.
- Final product name.
