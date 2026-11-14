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

### Session 2 — 2026-11-14 — M2 Reader + seller site, then M3 launch engine and M4 repair code (all on fakes)
- Goal: M2 (all 4 ACs), then — after the user postponed live calls — M3 against fakes (backup-before-write, domain-in-DB, purchase-blocked ACs) and the code-only parts of M4 (playbook, Doctor refuse-outside-playbook, Checker).
- Asked Claude to: follow the ritual, add a transcript-saving step, build the Reader/review/site/orders in fixture mode and ask before any live call; later, build M3 entirely against fakes and list every real-integration gap for the next session.
- Claude built: `scripts/save-transcript.sh` (redact + secret-scan, never saves on a match) and a replay script that also reads `replay/sessions/`; live Claude spend cap + max_tokens + usage table; Reader (strict Pydantic profile, one retry, photo input); review screen; ONE mobile-first seller template (menu by category in ₹, WhatsApp link, server-side UPI QR, privacy page) served by Host header; order form → DB + email. Then: fake world (scoped DNS writes, availability, mailbox, authoritative DNS, HTTP probe), Namer, Planner (steps + before/after diff + cost), approval card, Executor with guards and resumable step log, mailbox create/adopt/poll/retry; Checker (8 checks), 5-fix playbook, Doctor with max 3 attempts.
- I changed / rejected: approved the plan; postponed M1 (credit not confirmed); declined live Claude calls for now (no API key) — fixtures stay placeholders. Claude caught that its first secret-scan printed part of the matched secret and changed it to print line numbers only; it also replaced whole-zone DNS replace with per-record writes so a launch can't wipe unrelated records.
- Result: 183 tests pass (1 skipped: live HTTPS needs the VPS). M2 done; M3 done except the real-infra AC; M4 code-only parts done. Verified in a real browser at phone width: describe → review → edit price → site → order; free-address launch → approve → done; own-name launch → stops at purchase with a plain message. Live Claude spend: $0.
- Next: M1 purchases + VPS, then plug in the "Real integration TODO" list in PROGRESS.md and record live fixtures.
- Follow-up (same session): the transcript secret scan matched 6 false positives (code annotations, the scanner's own fake test key, random bytes in a screenshot) and refused to save. On the user's instruction Claude rewrote the scan as `scripts/transcript_scrub.py`: redact matched values with `[REDACTED]` and keep the rest, skip code annotations and base64 images, refuse to save if an independent re-scan still finds anything (15 tests). The session 2 transcript was then saved and committed.

### Session 3 — 2026-11-14 — M4 rest: launch report, demo fault, monitoring, owner links (all on fakes)
- Goal: finish M4 against fakes: AC1 (green sandbox run with times), AC2 (demo fault → Doctor → fix → green, audited), AC4 ("Run checks now" + scheduled jobs); plus the guards needed before judges get a public link.
- Asked Claude to: record my answers to two open questions (email plan shown as a separate estimate; owner link with a hashed token instead of accounts), build the report page, an admin-only demo fault, APScheduler light monitoring, per-visitor limits and a practice-only public path, then check the whole flow in a real browser at phone width.
- Claude built: `safety/access.py` (owner key, admin token, visitor id, limits); per-business integrations (practice businesses always use the fake world); `agents/launch_check.py` (CheckRun, demo fault, Doctor repairs, days left); `monitor/scheduler.py` (15-min + daily jobs, 1-minute re-check, alerts once per problem, expiry warnings); `routers/report.py`; new `settings_match` check; certificate/domain end dates on the wrappers; frontend owner-link page, report page, team sign-in + demo switch, "Pretend I bought it (practice)", email-plan line, personal email field.
- I changed / rejected: Claude found that DMARC only exists on own-name launches, which can't finish in practice without a purchase; I chose a practice-only "Pretend I bought it" button over moving the demo fault to the site address. I confirmed the practice-only reading of the live-link guard and asked for the visitor limit on "describe" too. $24/year is a placeholder email price to check against the cart.
- Result: 245 tests pass, 2 skipped (real-infra). Browser run at iPhone width passed end to end. It caught three things that were then fixed: passing checks said the same thing twice; a confusing "I bought it, resume" button in practice; and in practice "Open my website" pointed at the pretend own-name domain (which could be someone's real site). Live Claude spend $0, GoDaddy spend $0.
- Next: M1 purchases + VPS, Fable session for the real-integration TODO list (now 16 rows), then M4 AC5 evening launch and M5.

### Session 4 — 2026-11-14 — M1 + M5 prep without real infrastructure
- Goal: do every M1 and M5 task that doesn't need the VPS, GoDaddy credit or a Claude key, so the next session is just following steps.
- Asked Claude to: build the landing page + contact form, `/build`, deploy prep (Dockerfile without the sandbox workaround, prod compose, DB backup), a copy-paste M1 runbook with checks, an M1 check script, a demo seeder, and README + project brief drafts; then secret-scan and publish the build replay.
- Claude built: landing page (`/`) with contact form → Mailer → app mailbox; `/build` route; `deploy/docker-compose.prod.yml`; `scripts/backup_db.sh` (+ restore), `scripts/check_m1.sh`, `scripts/seed_demo.py` (+ admin-only practice reset endpoint); `docs/RUNBOOK_M1.md`, `README.md`, `docs/PROJECT_BRIEF.md`; build-replay now redacts my email and scans the published page (`transcript_scrub.py --check`).
- I changed / rejected: asked for the secret scan + email redaction on `build.html` before committing it, and approved replacing the partial session 3 transcript with one complete file for this chat (sessions 3 + 4 share one Claude Code session).
- What testing caught: the Docker build here fails only on the sandbox proxy certificate (a scratch copy with the CA as a build secret built and ran healthy — still to confirm with a plain build on the VPS); the first DB restore crash-looped the app because `docker cp` left the file owned by root, so restore became `--restore` that fixes ownership; the replay scan refused to publish because the Session 1 copy still held the sandbox's public default Java truststore password, so that copy was re-scrubbed.
- Result: 258 tests pass, 2 skipped (real infra). Prod stack verified locally (healthy, HTTPS, `/internal` blocked, monitoring on); backup/prune/restore, seeder and reset tested; landing page checked at iPhone width. `$0` spend.
- Next: on the VPS, `docs/RUNBOOK_M1.md` top to bottom, then the integration rows in its step 11 order.
