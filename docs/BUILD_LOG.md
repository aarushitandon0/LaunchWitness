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

### Session 5 — 2026-11-14 — Design and motion pass
- Goal: make the demo feel premium and smooth (M5 demo polish), at iPhone width and on a laptop. No changes to the spec or to any backend behaviour.
- Asked Claude to: build design tokens, animate the app flow (step transitions, streaming launch log, checks going green one by one, red → Doctor sentence → green), and build a scroll-linked landing page inspired by (not copied from) a reference video: cream hero card inside a dark frame with a notch nav, dark sections sliding over it, cards that expand in lime, a slow marquee. Seller template only lightly polished. Respect reduced motion.
- Claude built: `tokens.css`, `motion.tsx` (drawn tick, typing text, reduced-motion hook), a rewritten `styles.css`, the dark-frame app shell with page transitions, the new landing (code-drawn layered shape, sticky hero, 4 expanding step cards, GoDaddy marquee, promises, contact), the streaming launch log with progress bar, and the report playback. Added framer-motion.
- I changed / rejected: picked Inter Tight; asked that it fit laptops too (landing is two-column on wide screens, step cards sit in a row and expand sideways).
- Result: walked the full practice flow in Chromium at 390 px and 1440 px, including the demo DMARC fault being explained and fixed on screen. Frame-time test found the hero jank came from fading the whole hero's opacity; replaced it with one overlay (0 slow frames on the phone test). On mobile the shape first covered the headline; moved it above. 258 tests pass.
- Next: M1 on the real VPS (runbook).

### Session 6 — 2026-11-14 — Real Claude agents (prepared; live calls moved to the laptop)
- Goal: replace every placeholder Claude fixture with a live one, stress the Reader with hard inputs (messy WhatsApp, Hinglish, no categories, handwritten photo, prompt injection), quality-gate the Namer and Doctor, make the public path fall back to fixtures when the cap is hit, and quote a cost per launch. Budget: at most $1.50 of live Claude.
- Asked Claude to: plan first, spend as little as possible, stop calling Claude the moment something fails and fix it offline, add a prompt-injection input and test, then push, merge, rebuild the replay and run the app locally for me.
- Claude built: a capture script for all three agents (one call per target, no retry, stops at the first failure, raw replies kept for offline debugging, `--dry-run` cost estimate, `--report` spend) + a one-command laptop wrapper that refuses a cap above $1.50; five hard Reader inputs incl. a generated handwritten-style photo and an injection attempt; `tests/test_s6_agents.py` quality gates; `FallbackClaudeClient` + friendly UI notes; prompt changes (Reader treats input as data; Namer .in + .com; Doctor sees only the fixes allowed for that check).
- I changed / rejected: lowered the budget from $3 to $1.50; added the prompt-injection case; when the cloud session turned out unable to hold an Anthropic key, I chose to run the 17 live calls on my laptop and asked for everything else to be finished and merged.
- What checking caught: Haiku 5.5 thinks by default, so a 200-token Doctor reply could have been cut off and wasted a call (thinking now off). The first `.in`/`.com` rule rewrote the names list and broke the ranking tests (moved into `rank`). The fallback tests first changed the wrong app object (now use the test client's app). The injection test was checked to fail on a deliberately "hacked" reply.
- Result: 292 tests pass, 13 skip (11 wait for the live fixtures). Worst case for all 17 live calls: $0.14. Estimated ≈ 1 cent per launch. **Live Claude spend this session: $0.00** (ClaudeUsage table empty).
- Next: run `bash scripts/capture_all_live.sh` on the laptop, commit the fixtures, fill in the measured cost per launch; then M1 on the VPS.

### Session 7 — 2026-11-14 (UTC) — Live Claude fixtures
- Goal: replace the placeholder Reader/Namer/Doctor fixtures with real replies, pass the session 6 quality gates in strict mode, and measure the cost per launch. Budget: at most $1.50, as little as possible.
- Asked Claude to: follow the ritual, never read or print `.env`, dry-run first and wait for my "go", make one live call per target with no retries, stop and fix offline on any failure, then commit the fixtures + docs, save the transcript, rebuild the replay and merge.
- Claude built: Windows support in `scripts/capture_all_live.sh` (`.venv/Scripts`, `python -m pytest`), a Windows note in `docs/LIVE_FIXTURES.md`, the 17 live fixtures, and test updates for the new fixture text; measured cost table in PROGRESS.md.
- What checking caught: before any call, the Anthropic SDK wouldn't import because Windows Application Control blocks `jiter` 0.19.0's DLL; an older `jiter` (0.11.1) loads and is allowed by the SDK, so it was installed in the local venv only. After the calls, the script's last step failed because `pytest.exe` is blocked too (switched to `python -m pytest`; no extra spend). The full suite then showed 6 older tests pinned to the placeholder text (e.g. "Meera's Home Cakes"); one landing test was passing only because the old host name no longer existed, so it was updated too.
- Result: all 17 calls succeeded first time: prompt injection ignored, all 6 handwritten prices right, Namer gives 5 × (.in, .com), Doctor sentences jargon-free. Strict gates 43/43; full suite 303 passed, 2 skipped. **Live Claude spend: $0.0726** (ClaudeUsage, 17 rows). **Measured ≈ $0.010 per launch (about 1 cent).**
- Next: M1 on the VPS (`docs/RUNBOOK_M1.md`).

### Session 8 — 2026-11-14 — Shop redesign: one generic template for every seller
- Goal: M5 demo polish. The seller site looked like a plain text page on a laptop, listed the menu twice, treated delivery as a product and had nowhere to put "order 2 days ahead".
- Asked Claude to: first think through what a small seller actually needs (orders, payment, tracking, being told about orders) and list the holes, then redesign the template, keeping it generic: badges only from data, `allow_item_message` as a profile field (default off), fixed category palette, tested on 6 very different sellers at 375 and 1440 px, a scope guard for booking businesses, UPI display name + FSSAI number, never a "Verified" label. Then fold everything about payments and tracking into a session 9 prompt and update SPEC.
- Claude built: the new `seller.html` (laptop menu + sticky order panel, phone sticky basket bar, Add → − n + steppers over plain quantity boxes, extras section, two-column long lists + search, info tiles, UPI name); 10 new profile fields + 2 product fields; `tidy_profile`; the booking scope guard; review-screen fields; a 6-seller site gallery with render + screenshot scripts; `tests/test_s8_shop.py` (29 tests); SPEC changes; `docs/NEXT_SESSION_S9.md`.
- I changed / rejected: made it generic rather than Meera-shaped; added the scope guard, UPI display name, FSSAI and the no-"Verified" rule; moved email verification, a policy check and report/pause into session 9; set the M1-by-Nov-17 deadline.
- What checking caught: the tailor page scrolled sideways on phones (a grid column grew to fit the category chips; fixed with `minmax(0, 1fr)`); basket prices broke one digit per line next to long Hinglish names; the 44-item menu left a big empty column on laptops (now two columns + search); "Price starts from ₹300" repeated the "from ₹300" price (tidy-up drops it); the review page needed the "I've saved it" step in the browser check.
- Result: 333 passed, 2 skipped. All 6 gallery sellers checked at 375 and 1440 px with no sideways scrolling; full practice flow checked in the browser. Live Claude spend: $0.
- Next: M1 on the VPS by Nov 17; session 9 from `docs/NEXT_SESSION_S9.md`.

### Session 8.5 — 2026-11-15 — Real domain + mailbox wiring, proof-first copy
- Goal: M1 prep without a VPS: the contact form sending through the real `hello@launchwitness.com` mailbox; real email price; proof-first positioning.
- Asked Claude to: make SMTP env-only with 465 SSL and a 587 STARTTLS fallback, send one real contact-form message from a local run without printing the password, set the real email plan price, switch app-domain references to `launchwitness.com`, add a read-only "list my GoDaddy domains" script, and reorder the README + landing around proof (test order → Doctor → monitoring → generation last).
- Claude built: the fallback in `app/mail/smtp.py` (only when the SSL connection can't be made; never after login, so no double sends or password retries) + 3 tests; `scripts/list_godaddy_domains.py` + 3 tests; `EMAIL_PLAN_ESTIMATE_USD=23.88`; README pitch, landing headline "Is your shop actually ready for customers?", runbook step 0 (purchases done), PROGRESS, session 9 note.
- I changed / rejected: bought `launchwitness.com` + a 1-month Pro Light mailbox (not `.in`, not a seller domain: credit ran out); no DNS changes until the VPS arrives free on Wed Nov 18; demo on `meerasbakes.launchwitness.com`.
- What checking caught: the mailbox is GoDaddy Professional Email (secureserver.net), not Titan, while the planner still assumes Titan's DKIM name (open question); the old "M1 by Nov 17" deadline can't hold with a Nov 18 VPS; a mixed-case `LaunchWitness.in.` test case was missed by the first find-and-replace.
- Result: real contact-form email sent over port 465 (HTTP 200, no fallback needed). 339 passed, 2 skipped. Live Claude spend: $0.
- Next: session 9 (`docs/NEXT_SESSION_S9.md`), M1 on Wed Nov 18.

### Session 9F — 2026-11-15/16 (IST) — Claims made true, then accounts and multi-tenancy (Fable, finished by Opus)
- Goal: make every claim on screen true (Phase 1), then let many sellers use one app safely (Phase 2).
- Asked Claude to: Fable audited the app and fixed B1–B9/S2/S5–S8 (commit `d02a430`), then designed accounts: email-link sign-in, guest practice, team approval, one access gate, CSRF, host-only cookies, route classification. Fable hit its usage limit mid-Phase 2; Opus was asked to finish it without redesigning, make it green, write the access test suite and the frontend, and merge.
- Claude built: (Fable) `accounts.py`, `tenancy.py`, `agents/policy.py`, auth/admin routers, `request_guard.py`, `route_table.py`, models + migration; (Opus) the remaining test updates, `tests/test_s9_phase2_access.py` (52 tests incl. a generated owner-route matrix), the frontend (sign in, check email, confirm, My shops, account, team page, CSRF in `api.ts`, guest/pending banners, "Launch for real"), `seed_demo.py` on the admin token, checkpoint doc + screenshots.
- I changed / rejected: no claim flow other than guest → sign in; subdomains only; approval card shows $0; never name other builders.
- What checking caught: the policy check failed **open** in live mode (the fixture fallback answered "ok"); deleting a shop reset the per-user Claude cap; anyone signed in could burn another user's delete link; the account page showed a stale "pending" after approval (cached `/me`); the top-bar sign-in link was invisible on the dark bar; a lifespan test was touching the developer's real database.
- Result: 437 passed, 2 skipped; ruff, `tsc --noEmit` and the build clean. Live Claude spend: $0.
- Next: Phase 3 (order proof chain + check any address).

### Session 9F Phase 3 — 2026-11-16 (IST) — The order proof made real (Opus)
- Goal: make the differentiator real: prove each hop of an order separately, never call "accepted" "delivered", and let anyone check an address.
- Asked Claude to: evidence table; outside-in test order through the public form with an SSRF guard; separate hops (form → mail server → inbox or owner tap); HTTPS marker + certificate wait; authoritative DNS; report hop trace and "N of M proven"; shareable `/r/<token>`; daily test order; "Check any address"; WhatsApp "Send this order to the shop"; mailbox expiry warning.
- Claude built: `app/proof.py`, `app/checks/safe_fetch.py`, `app/routers/proof.py`, `AuthoritativeResolver`, `Evidence`/`TestTicket`/`ReportShare`/`AddressCheck` tables, `accept_order_form` (one form handler for customers and the checker), report hop trace + share panel + "Yes, I got it" page, landing check section; `tests/test_s9_phase3_proof.py` (40 tests).
- What checking caught: a real shop with the owner's own inbox showed "ready" on a mail server's "accepted" alone (now "Almost ready" until her tap); my headline edit briefly swallowed the "ready" branch (suite caught it); the landing section's heading was invisible on the dark background and had no phone gutter (screenshots caught both).
- Result: 477 passed, 2 skipped; ruff, tsc and build clean. Real network paths (SafeWeb, AuthoritativeResolver, IMAP) are unit-tested with stubs only: unproven until the VPS. Live Claude spend: $0.
- Next: Phase 4 (investigating Doctor), Phase 5 (design), Phase 6 (verification + VPS handover).


### Session 10 — 2026-11-16 (IST) — Deployable and safe for real users, before the VPS (Opus)
- Goal: make Wednesday's VPS deploy boring: run the full stack in Docker exactly as on the VPS, then data safety, the watchdog features, verification and a cold-start VPS guide.
- Asked Claude to: audit `deploy/` against the code, run the stack the production way locally (HTTPS, `DEV_MODE=false`, fakes, a mail catch-all) and prove cookies, guards, rate limits, restarts; SQLite done properly + tested backups; a startup self-check; legal pages; Renewals, zone hygiene, a dangling-CNAME finding; Playwright e2e + SECURITY.md + a secret scan of the history; `docs/NEXT_SESSION_VPS.md`.
- Claude built: `deploy/docker-compose.local.yml` + `deploy/README.md` (14 mismatches found and fixed or documented), Caddyfile.prod hardening, `app/singleton.py`, SQLite pragmas, `app/backup.py` + `backup_db.sh`/`restore_db.sh`, `app/selfcheck.py`, fixture-mode hold, `Legal.tsx`, `app/renewals.py` + team alerts, `app/zone_hygiene.py` + team page section, dangling CNAME, `e2e/` (4 flows), `test_s10_*.py`, `scripts/secret_scan.sh`, `docs/SECURITY.md`, `docs/NEXT_SESSION_VPS.md`.
- What checking caught: `foreign_keys=ON` exposed the admin demo delete leaving proof rows behind (fixed); the old restore would have replayed a stale WAL into a restored DB; the stack check's own token would have used up the admin's daily sign-in links on the VPS; a `.env` value with spaces before its comment could hide a leaked password from the leak check; the local compose loaded the real `.env` into a local container; a naive XSS assertion flagged escaped text (switched to an HTML parser); Git Bash path conversion broke the backup scripts on Windows.
- Result: 523 passed, 2 skipped; ruff, tsc and build clean; e2e 4/4 on the Docker stack and on the dev server; `check_m1.sh --local` all PASS; secret scan of repo + history clean. Live Claude spend: $0.
- Next: the VPS (Wed Nov 18) with `docs/NEXT_SESSION_VPS.md`.

### Session 10.5 — 2026-11-16 (IST) — What the owner found while testing (Opus)
- Goal: fix four problems found on the local Docker stack and gather the right details before a shop can go live, for real
  sellers, without changing any backend security rule.
- Asked Claude to: rewrite the landing for small sellers (Meera only as a demo shop), sign in first with guest practice as a
  secondary path and proper routing, an Orders page with WhatsApp to the customer and statuses, fix the blank preview, and a
  go-live checklist that only gates real launches. Mid-session: fix the cut-off hero headline and make the hero shape smoother,
  rounder, with more layers; restart Docker after the session was interrupted.
- Claude built: `sites/demo.py`, `Steps.tsx`, `Orders.tsx`, `GoLive.tsx`, `golive.py`, a new router + top bar, order status
  route + links, the preview link script + sandbox change, Profile fields/validators, owner confirmations, the Report's
  "Checked by you", e2e flows `e`/`f` (+ orders and the gate in `a`), `e2e/screens/` for screenshots, 4 new test files.
- What checking caught: the preview bug's real cause (a `srcdoc` frame resolves `#menu` against the APP's URL); a
  sandboxed frame without `allow-forms` refuses a form before any `submit` event, so the first fix never ran; Meera's sample
  offers delivery, so the gate correctly refused her without delivery areas; the hero was clipped because a fixed-height card
  centred content taller than short screens. The interrupted session left two files as blank bytes (restored from git and
  redone; every tracked file re-scanned).
- I changed / rejected: product photos deferred (no upload storage exists yet, despite the brief).
- Result: unit 607 passed, 2 skipped; ruff/tsc/build clean; e2e 7/7 on Docker and dev server; `check_m1.sh --local` all PASS.
  Live Claude spend: $0.
- Next: the Fable session, then the VPS (Wed Nov 18).

### Session 10.5b — 2026-11-16 (IST) — Landing: keep watching, Product menu, watch any address, a 3D hero (Opus)
- Goal: make the landing say clearly that we keep watching, add a product menu, a next step after Check any address, and a
  hero that means something, with every sentence matched to the code.
- Asked Claude to: a monitoring section from the real schedule, a Product mega-menu, "Watch this address" only if small and
  clean, and the hero first as a meaningful SVG stack, then (changed mid-session) a lazy three.js "witness" scene.
- Claude built: landing sections #proof/#watch/#security, `ProductMenu.tsx`, `app/watch.py` + `routers/watch.py` +
  `WatchedAddress`, `src/hero/scene.ts` + `HeroScene.tsx` + a rendered still, e2e flow `g`, screenshot run `s105b`.
- What checking caught: two landing claims true only in practice mode (own name, orders@ mailbox); the mailbox renewal is
  the team's, not the seller's; headless Chrome's software WebGL made the scene starve the page, which real GPU-less visitors
  would also feel (now: still image); the first scene looked washed out and its check unreadable (iterated on real-GPU
  screenshots: richer colours, lens turned to the camera, labels kept inside the card, phone bleed fixed).
- Result: see PROGRESS; scene 60 fps on Intel Iris Xe at 1917/1440/375; Live Claude spend $0.
- Next: the Fable session, then the VPS (Wed Nov 18).

### Session 10.5c — 2026-11-16 (IST) — Undo the 3D hero (Opus)
- The owner didn't like the three.js hero. Removed it (scene, still image, `three` dependency, its e2e checks and the loop
  recording) and restored the S10.5 SVG hero; everything else from S10.5b stays. The scene remains in git history (`820e824`).


### Session 11 — 2026-11-16 (IST) — Review and the investigating Doctor (Fable; entry written in S12)
- Goal: a P0 hunt over everything since Phase 1, then a Doctor that looks before it chooses a fix.
- Claude built: the `SafeWeb` limits (streamed, 300 KB, 20 s per page); `app/agents/investigator.py` (five read-only tools,
  at most 4 looks, code checks the answer, rule-based fallback labelled "standard"); three staged faults; the whole-system
  invariant test (`tests/test_s11_invariants.py`, 260 seeds).
- What checking caught: the model first told the seller to "check your mail password" (the mailbox is ours): the instruction
  for a refused sign-in is now always the code's. The invariant test's first version passed with zero alert emails sent.
- Result: 646 passed, 2 skipped. No e2e or screenshots that session.

### Session 11b — 2026-11-16 (IST) — Checks right for every website and mail setup (Fable; entry written in S12)
- Goal: every website and email setup gets a correct, plain answer; every failed check ends in a fix or exact steps.
- Claude built: `app/checks/mail_setup.py` (8 services, SPF walk, DMARC, DKIM never "missing"), `app/checks/web_setup.py`,
  `dns_resolver.lookup` with "our lookup failed", "couldn't finish" never passing, "keeps breaking" after 3 fixes a day, one
  email per problem, `docs/CHECKS_MATRIX.md`, an 18-test real-network run.
- What checking caught: 7 bugs from the real-network run (Zoho's SPF names, example.com's wildcard DKIM, an alias judged as
  its own domain, two trust-list mismatches, https→http, old fixtures that weren't really healthy).
- Result: 891 passed, 2 skipped. The UI didn't show the new fields yet (done in S12).

### Session 11c — 2026-11-16 (IST) — Pre-flight for the VPS (Fable)
- Goal: prove shop generation works with live Claude through the app, and remove hosting surprises before Wednesday.
- Asked Claude to: run Reader/Namer/policy/Doctor live under a $0.25 cap; trace DNS-before-TLS; a wildcard fallback; one
  approved real DNS write and undo; (if time) a tamper-evident proof log.
- Claude built: `scripts/preflight_live.py`, 3 new seller inputs + 5 policy cases with live fixtures, `tests/test_s11c_live.py`;
  `resolve_all` / `points_here`, the tls-ask DNS gate, `DNS_MODE`, `tests/test_s11c_hosting.py`, the guide's new sections;
  `scripts/preflight_dns_write.py`.
- What checking caught: the real write showed GoDaddy's two nameservers disagreeing for about 10 s, which the old one-server
  wait would have accepted; `reader_salon.json` was still a placeholder; a test pinned Claude's exact wording.
- I changed / rejected: Part 3 not started (budget). The new Namer reply did not replace the pinned fixture.
- Result: 919 passed, 2 skipped; strict live-fixture gate passes; live spend $0.056; write test 200/200/204/200, zone identical.
- Next: the VPS (Wed Nov 18), `DNS_MODE=per_shop`.

### Session 11d — 2026-11-16 (IST) — Tamper-evident proof log (Fable)
- Goal: the evidence behind every report claim must itself be checkable.
- Asked Claude to: chain every Evidence row by hash per shop, make evidence append-only, backfill old rows once, show a
  receipt on the shared report with a public verify, and say first if any of it was a bad idea.
- Claude built: `app/chain.py` (canonical JSON, `append`, `verify`, `backfill`, `purge`, ORM guards), `GET /r/<token>/verify`,
  the receipt line, `tests/test_s11d_chain.py` (32 tests), chain check added to the Session 11 invariant test.
- What checking caught: a time given in another time zone would have been stored as local digits and failed verification
  (now made UTC before hashing); two test set-up slips.
- I changed / rejected: said up front what the chain cannot show (a full rewrite, rows cut off the end, an old receipt can't
  be checked against a newer chain); none of that was added, as it is outside the brief.
- Result: 951 passed, 2 skipped; ruff clean; no live Claude, no DNS, no email.
- Next: the VPS (Wed Nov 18).

### Session 12 — 2026-11-16 (IST) — The UI for the checks and the Doctor, interactive landing, product photos (Opus)
- Goal: show on screen what S11–S11d built; make "How the proof works" and "We keep watching" interactive; product photos.
- Asked Claude to: post a short plan, say first if anything was a bad idea, merge each part with `--no-ff`, keep every claim
  on screen matching the code.
- Claude built: A: confidence tags, numbered steps, provider name, six distinct check states, the Doctor's trace as a
  timeline, "Describe the problem" (owner route, 5/day, words fenced and not logged), incident timeline (report + shared
  page), a fourth staged fault (parked page) and a 4-fault demo switch, receipt + Verify. B: hop track and example day with
  "Something breaks", copy pinned by `test_s12_landing_copy.py`. C: product photos (`app/photos.py`, Pillow, WebP ×2,
  EXIF/GPS stripped, in the database, served from the shop host, 24 tests). D: Docker stack, e2e, screenshots + recording.
- What checking caught: in fixture mode the saved Doctor conversation looked up `meera.localhost` on every shop, so its
  trace said "not allowed" (e2e); the landing's old `.hops` grid broke the report's hop line into a column (screenshot);
  a hop's panel opened and closed on one click (focus + toggle); the dot sat 15 px low on phones; the test order's form and
  inbox failures were given the "couldn't send the email" steps; "We tried 0 times"; a deleted item shifted photos onto the
  wrong item (positional rename); newer Chromium fails navigations to a bare 404 (e2e helper fixed).
- I changed / rejected (Claude said so first): pushed to the session branch, not `main` (the only branch this cloud session
  may push; GitHub's `main` is 90+ commits behind); the new Doctor fixtures are hand-written placeholders (no key in the
  cloud); "Something breaks" ends with no email, because the code doesn't email after a successful fix; photos live in the
  database, not as files, so backups and deletions cover them.
- Result: unit 1006 passed, 2 skipped; ruff, tsc, build clean; Docker stack rebuilt, `check_m1.sh --local` all PASS; e2e
  14/14 on the Docker stack (7 new flows); screenshots + a 20 s recording in `docs/screenshots/s12/`. Live Claude: $0.
- Next: capture the S12 fixtures on the laptop (`capture_doctor_investigation.py --s12`, cap $0.10), then the VPS (Wed Nov 18).

### Session 13 — 2026-11-17 (IST) — Live S12 fixtures, an email outbox, monitoring at 40 shops (Opus, laptop)
- Goal: reliability before the VPS day: no lost email, monitoring that scales, real Doctor fixtures.
- Asked Claude to: capture the S12 fixtures live, build a durable outbox, measure and fix monitoring for 40 shops, then a weekly digest and a public-resolvers check.
- Claude built: Part 0 (11 live fixtures, $0.0025; the capture script crashed on an unexpected `evidence` call, fixed). Part A: `app/outbox.py` + `Outbox` table, every sender moved onto it, sender job, reconcile, budget + priorities, admin card, honest sign-in/contact wording, the Orders email state, 21 tests. Part B: a 40-shop slow pretend world, measured first (quick 534 s, daily 670 s simulated; one hang holds everyone up), then a worker pool, per-shop slots on a one-minute beat, a per-check watchdog, a later inbox look, a shared GoDaddy limiter (quick ~163 s, daily ~300 s), 10 tests; SPEC capacity note.
- I changed / rejected: stopped the session after Part B (Part C and the Docker/e2e verification move to the next session). Claude flagged up front the risk of changing every email path the day before the VPS, and that a Python "watchdog" can stop waiting for a check but can't kill it.
- Result: unit suite 1037 passed, 2 skipped, 19 deselected; long S11 invariant profile (240 seeds) passed; ruff/tsc/build clean; Docker, check_m1 and e2e not run this session.
- Next: Docker + e2e (with the new "order while mail is down" flow), then Part C.

### Session 13b — 2026-11-17 (IST) — S13 verified on Docker + e2e, the VPS guide, public resolvers (Opus, cloud, unattended)
- Goal: prove S13's outbox and monitoring on the real stack the day before the VPS, and make the VPS guide followable cold.
- Asked Claude to: rebuild the prod-like stack, pass `check_m1.sh --local`, run e2e plus two new S13 flows, check restart
  behaviour in the logs, turn every failure into a test; set `SMTP_DAILY_LIMIT=450`; update the VPS guide; then the
  public-resolvers check.
- Claude built: `e2e/tests/i-s13.spec.ts` (order while practice mail is down -> retrying -> sent; sign-in while Mailpit is
  stopped -> "trouble sending" -> the link arrives), a scheduler-jobs line in `check_m1.sh`, the guide's "what changed"
  table, expected start-up logs, go-live checklist steps, email troubleshooting, the full production `.env` checklist and
  a 10-line smoke test; `SMTP_DAILY_LIMIT=450` + SPEC capacity (at most 360 shops per mailbox); Part 3: public resolvers
  as evidence on the daily run (8 tests, CHECKS_MATRIX rows, report card line).
- What checking caught: the S12 symptom e2e still expected the hand-written placeholder's "You said" (the live fixture
  doesn't echo); the new Orders e2e first failed because `page.goto` to the same hash URL doesn't reload the app (the
  outbox had sent the order 35 s after mail came back); the S11 invariant test listed the machine evidence steps and had
  to learn `public_resolvers`; one run of `test_godaddy_calls_stay_under_the_rate_limit` failed in a full run and
  passed every time after (timing under load: open doubt); a guide line claimed a "check your spam folder" hint that the
  sign-in page doesn't have (corrected).
- I changed / rejected: (unattended) Docker Hub worked; pip/npm inside the build needed the sandbox CA, so the image was
  built from a scratch Dockerfile copy (never committed) and the stack started with `up -d --wait` on that image.
- Result: unit 1045 passed, 2 skipped; ruff, tsc, build clean; `check_m1.sh --local` all PASS; e2e 16/16 (twice, before
  and after Part 3). Live Claude: $0. Not seen running: the daily public-resolvers look inside the app process (a shop's
  daily slot can be up to 24 h away; covered by unit tests).
- Next: the VPS (Wed Nov 18), `docs/NEXT_SESSION_VPS.md`.

### Session 13c — 2026-11-17 (IST) — pre-VPS test run on the laptop (Opus, laptop)
- Goal: run every check once on the laptop before the VPS; fix only what fails.
- Result: backend 1044/1045 in a full run under Docker+e2e load (`test_s13_scale.py` 40-shop timing), 10/10 alone;
  strict fixtures 1035 passed (scale file excluded, verified alone); ruff, tsc, build clean; Docker up; `check_m1.sh
  --local` all PASS; e2e 15/16 then h-s12 6/6 after the fix; secret scan clean; backup + restore OK, app healthy.
- Fixed: two S12 e2e asserts used the 5 s default while the reloaded report replays the run (box/incident hidden): 30 s.
  Added the sign-in "Can't find it? Look in your spam or promotions folder." line + e2e check.
- Open: Compose warns `"ztE" variable is not set` when reading the repo's `.env` — a `$` inside a value gets
  interpolated by Compose. On the VPS (`--env-file .env`) that value would be mangled: quote it with single quotes or
  write `$$`. Live Claude: $0.
