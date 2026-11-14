# Build log — how LaunchWitness was built with Claude Code

One entry per Claude Code session, newest last. This is what judges read to understand the process; the full transcripts are in the combined replay at `/build`.

## Template (copy for each session)

```
### Session N — YYYY-MM-DD — <short title>
- Goal: <milestone + acceptance criteria targeted>
- Asked Claude to: <1–2 lines>
- Claude built: <files/features>
- I changed / rejected: <what the human decided or corrected>
- Result: <ACs passed, tests, what works now>
- Next: <one line>
```

---

### Session 0 — 2026-11-14 — Ideation and spec
- Goal: settle the idea and plan before writing code.
- Worked with Claude (chat) to pressure-test the idea: dropped "rollback after launch" as the hero after realizing that in a setup we control, little breaks post-launch; moved repair into the launch itself; kept light monitoring.
- Output: `docs/SPEC.md`, `docs/BUILD_PLAN.md`, `CLAUDE.md`.
- Next: M0 scaffold.

### Session 1 — 2026-11-14 — M0 scaffold (local, no external calls)
- Goal: M0, all three ACs (compose serves page + health ok; pytest incl. purchase-blocked and tls-ask tests; no real network in tests, no secrets).
- Asked Claude to: read the docs, propose a file-by-file plan mapped to ACs, then build M0 with every external service behind a wrapper with a fake.
- Claude built: FastAPI backend (`config`, `db`, six SQLModel tables, `audit` helper, `/api/health`, `/internal/tls-ask`); wrappers + fakes for GoDaddy (ote|prod), Claude (fixture|live), SMTP, IMAP, DNS; spend guard; 3 Indian seller fixtures (home cakes, tiffin, tailor) + a placeholder Reader fixture; Vite/React/TS health page; Dockerfile, compose, local + prod Caddyfiles; an autouse pytest guard that blocks and records any non-local network call.
- I changed / rejected: approved the plan as proposed. Notable fixes during the session: the network guard first let traffic escape via the sandbox's local HTTPS proxy (fixed by clearing proxy env vars in tests); dnspython swallows the guard's error, so that test asserts on the guard's record instead; one commit had gone in with a failing test hidden by a pipe and was amended before pushing.
- Result: 52 tests pass; stack verified at http://localhost through Caddy (health ok, `/internal/*` blocked); both Caddyfiles validate. In the cloud sandbox the image needed a scratch-only CA build secret; repo Dockerfile unchanged.
- Next: M1 — buy VPS/app domain/mailbox (user), deploy prod mode, real HTTPS.
