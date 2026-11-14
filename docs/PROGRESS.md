# PROGRESS — master status

Claude Code reads this at the start of every session and updates it at the end. Keep it short and current; history goes in `BUILD_LOG.md`.

## Current milestone

**M0 — Scaffold (local)** · started 2026-11-14

## Next up

- M0 tasks in `docs/BUILD_PLAN.md`.

## Done

- 2026-11-14: Idea, spec, plan finalized (`docs/SPEC.md`, `docs/BUILD_PLAN.md`).

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

## Open questions

- Does the credit cover domain + Pro Light fully? Exact cart total?
- Are hackathon accounts whitelisted for production Domains/DNS APIs, or use `gddy`?
- Is a demo video expected in the submission? (Include one anyway.)
- One current India-specific stat on small businesses without websites.
- Final product name.
