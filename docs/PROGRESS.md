# PROGRESS — master status

Claude Code reads this at the start of every session and updates it at the end. Keep it short and current; history goes in `BUILD_LOG.md`.

## Current milestone

**M1 — Required basics live** · M0 done 2026-11-14

## Next up

- M1 tasks in `docs/BUILD_PLAN.md` (needs credits: VPS, app domain, mailbox — user buys on godaddy.com).
- First thing on the VPS: run the M0 AC1 command there (`docker compose -f deploy/docker-compose.yml up --build`), then prod mode.
- Carry-overs for M2: enforce `CLAUDE_DAILY_SPEND_CAP_USD` in `LiveClaudeClient`; replace the hand-written Reader fixture with a real saved response.

## Done

- 2026-11-14: Idea, spec, plan finalized (`docs/SPEC.md`, `docs/BUILD_PLAN.md`).
- 2026-11-14: **M0 Scaffold** — all 3 ACs pass:
  - AC1: stack up via compose; `http://localhost` serves the React page showing "LaunchWitness is running and ready", `/api/health` → `{"ok":true,"env":"ote"}`, `/internal/*` returns 404 through Caddy. Both Caddyfiles pass `caddy validate`. *Caveat:* in the Claude Code cloud sandbox `pip`/`npm` inside `docker build` can't trust the sandbox's egress-proxy CA, so the image was built there with a scratch-only copy of the Dockerfile that mounts the CA as a build secret (only difference: two `RUN` lines), then `compose up`. The repo Dockerfile is unchanged and should build as-is on a normal machine/VPS.
  - AC2: `pytest -q` → 52 passed, incl. purchase blocked by default (+ cap, approval, reuse cases) and tls-ask rejecting unknown domains.
  - AC3: autouse test guard blocks every non-local socket connect/UDP send/DNS lookup and clears proxy env vars; each real wrapper has a test proving it can't reach the network. Secret scan clean; a test checks `.env.example` lists every setting.

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
| Availability check method | Undecided | gddy / Domains API / OTE / RDAP |

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

## Open questions

- Should seller sites also answer on `www.<domain>` (needs tls-ask + DNS change)? Currently no.

- Does the credit cover domain + Pro Light fully? Exact cart total?
- Are hackathon accounts whitelisted for production Domains/DNS APIs, or use `gddy`?
- Is a demo video expected in the submission? (Include one anyway.)
- One current India-specific stat on small businesses without websites.
- Final product name.
