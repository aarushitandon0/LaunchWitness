# PROGRESS — master status

Claude Code reads this at the start of every session and updates it at the end. Keep it short and current; history goes in `BUILD_LOG.md`.

## Current milestone

**Session 19D (Nov 19, Opus, laptop): View shop, edit a live shop, New badge, safe live edits.** My shops: View shop (live
real shops, own address in a new tab, address shown) or Preview (practice/draft), Edit shop. A live shop's owner can edit and
add items; items can show "New" for 15 days. Customers never see an unconfirmed WhatsApp/UPI, and changed words on a live shop
pass the policy check first (held edits wait for the team; the shop stays live). 19C deploy confirmed. **Next: demo video,
submission.**

Decisions (S19D): `live_url` is set for a real live shop also when paused / held / on a break (its own page says so); the
Report keeps its existing "Open my shop" (hidden while a check runs, as before). Removing a WhatsApp/UPI value takes effect at
once (nothing to confirm). New badge: `new_until` = day marked + 15 (IST), shown while today <= new_until, server never stores
more than 15 days ahead; items added after launch are New by default; the badge uses the theme's accent/accent-ink pair (the
button pair, AA in every look). Only a change to the words the policy check reads (name, tagline, about, selling point, item
names/descriptions) re-runs it; prices, hours, photos, the badge, theme don't. While an edit is held she keeps editing her own
copy; any later save that still carries the held words waits too; taking them out publishes. A real server on saved Claude
answers holds every word edit (as launches). The team sees the held edit through "See the edit" (the owner's Review). The
local e2e stack allows 1000 live shops (`docker-compose.local.yml`; production keeps 40). Hero trace (new script, different
settings from 19C, so not comparable): live, full Chrome headless, 1440: 60-68 fps, idle 3.6%, CLS 0.027; 390 px x4 (DPR 3,
scrolling through the dark panel): 16-18 fps, idle 23-28%, CLS 0.0006.

**Session 19C (Nov 19, Opus, laptop): landing hero performance.** The 19A hero kept the main thread busy every frame (idle
37-47% desktop / 98% on a 4x-throttled phone; scroll 20 fps desktop, 9 fps phone). Measured with CDP traces, fixed the causes,
same look on desktop (frozen-frame pixel diff < 0.06%). Landing files only. Numbers, method and screenshots:
`docs/screenshots/hero-perf/` and BUILD_LOG 19C. **Next: demo video, submission.**

Decisions (S19C): phones / low-power devices (< 900 px wide, <= 4 CPU cores, or Save-Data) get a lighter hero: the light-lines
are drawn still (no drift, no glowing dots) and the stack does not spread apart on scroll; everything else (intro, breathing
stack, ring ball, card scale/dim/corners on scroll) is unchanged. All hero loops pause while the hero is off screen or fully
covered by the dark panel. Found, not fixed (out of scope): shop subdomains answer `/favicon.ico` with 404, which fails
`l-s16-themes` (6 tests) when e2e runs on full Google Chrome (`LW_CHROME`); the bundled headless browser never asks for it.

**Session 19B (Nov 19, Opus, laptop): test emails only when she asks, clearly marked TEST; everything re-checked and deployed.**
Launch / "Run checks now" / "Describe the problem" send the test order to the shop's order address; monitoring sends it to
LaunchWitness's own check mailbox (hello@), labelled as such, with no "Yes, I got it" link. Every test email starts
`TEST, not a real order:` with a grey banner and no customer links; real order emails unchanged. 19A (landing motion) was
already merged by the owner and deployed. VPS on the final `main`. **Next: demo video, submission.**

Decisions (S19B): a daily test missing from OUR mailbox is "couldn't check" (our side), never an alert to the seller; monitoring
tests go to hello@ only, even for team-run shops (one recipient), so the daily proof is always labelled "check mailbox"; the test
email drops the cancellation line, the Orders link and the pickup instruction (nothing to act on); the test order's note no longer
says "launch check"; `scripts/admin_check_shop.py` runs a manual or daily round from the CLI inside the container (audited
`admin (cli)`), because the check routes need a signed-in cookie, not `ADMIN_TOKEN`.

**Session 17 (Nov 18-19, Opus, laptop): LIVE. The first real shop is launched and proven.** Logo + favicon + app icons; one branded
email layout; demo shop https://meeras-eggless-bakes.launchwitness.com launched for real (7/7 checks, real Let's Encrypt cert, test order
found over IMAP); shared report https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz (chain intact); nightly backups + restore
test; the VPS deploys by `git pull` over a read-only deploy key. Four fixes found on the live run (see STATE). **Next: demo video, README,
brief PDF, submission.**

Decisions (S17): the logo's real colours (lime/cream/peach on ink) drive everything: the email button is lime with dark text (the art has
no purple), the tab icon sits on an ink tile, apple-touch/manifest on ink `#161614`; the mark is in the header only (the footer and the
sign-in page only mention the name in sentences); the free-subdomain launch proves the app's own inbox by signing in to it while the Titan
client is a stub; the app container uses public DNS (SECURITY.md, "DNS the app trusts"); the test-order wait is 120 s for launch and
"Check again", while scheduled monitoring keeps its later passes; the restore test runs into a temp folder, never into a running stack.

**Session 15 (Nov 17, Opus, cloud, unattended): where she sells, how customers pay, what the order form asks** (PR into `main`, merge after S14). Selling modes, validated delivery areas/PINs, fees, payment terms with exact UPI amounts, cancellation, food marks, break, days off, daily limit; all enforced on the server; address private. See STATE_FOR_NEXT_SESSION and SPEC §9d. CHECKS_MATRIX unchanged (no check changed; the test order only gets safe defaults).

**Session 14 (Nov 17, Opus, cloud, unattended): a theme for every kind of home business** (PR open, not merged: after the VPS smoke
test). Six themes on one engine and one safety layer; Claude picks `theme` / `accent` / `section_copy` (keys and short plain text
only), code validates and draws; rule-based fallback; look picker on Review (audited); fonts self-hosted (OFL, `docs/FONTS.md`); a
strict CSP on shop pages; honest content only (testimonials only if the seller pasted them). See STATE_FOR_NEXT_SESSION and SPEC §5a.
Decisions (S14): the hero line is the page's h1 only when the Reader provides one (else the shop name); the three old palettes
(`niche-*`) are replaced by the six themes (`niche` now only feeds the rule-based suggestion); her own About text wins over the
Reader's short paragraph; the picker's inline preview doesn't count as "looked at your preview"; the owner's switch saves at once.
**Hand-written placeholders: the `theme`/`accent`/`section_copy` values in the 12 saved Reader replies** (re-capture command in STATE).

**Session 13b (Nov 17, Opus, cloud): S13 verified on the real stack, VPS guide current, public resolvers.**
Docker prod-like stack rebuilt, `check_m1.sh --local` all PASS (now also: one `monitor_tick`, one `outbox_send`), e2e
**16/16** (2 new S13 flows: order while practice mail is down -> "retrying" -> "sent"; sign-in while the mail server is
unreachable -> "We're having trouble sending email" -> the link still arrives). After `docker compose restart app`: one
monitor job, one outbox sender, a planted `sending` row reset by the reconciler and sent. No product bug found in S13; one
stale e2e assertion fixed. `SMTP_DAILY_LIMIT=450`. `docs/NEXT_SESSION_VPS.md` updated S10.5 -> S13 with a full `.env`
checklist and a smoke test. Part 3: the daily run asks 8.8.8.8 / 1.1.1.1 / 9.9.9.9 (evidence, never an alert). Weekly
digest dropped from this week's scope (owner). Unit 1045 passed, 2 skipped.

Decisions (S13b): `SMTP_DAILY_LIMIT` default also 450 in `config.py` (not only `.env.example`), so a missing line in
the server `.env` can't fall back to the old 250 placeholder; public resolvers are information only (no alert, no re-check,
no fix even when all three disagree: the shop's own nameservers decide); they're asked on the daily run only, for
practice shops against the pretend world (labelled); the report shows the latest look in the monitoring card ("Seen from
the wider internet") because a quick run replaces the daily run as "latest" within 15 minutes.

**Session 13 (Nov 17, Opus, laptop): stopped after Part B by the owner.** Part 0: the 11 S12 Doctor fixtures captured live
($0.0025). Part A: durable email outbox (every email saved first, retried with backoff, dead letters shown to the team,
daily budget with priorities, honest sign-in "trouble sending", orders never lost, "Email to you" on the Orders page).
Part B: monitoring with a 4-worker pool, per-shop slots, a per-check watchdog, non-blocking inbox look, GoDaddy rate
limit (40 shops: quick 534 s -> ~163 s). **Not done: Part C (digest + public resolvers), Docker/check_m1/e2e.** Next steps:
`docs/STATE_FOR_NEXT_SESSION.md` -> Session 13.

Decisions (S13): sign-in mail failure answers 200 `mail_delayed` (was 503); the order_email audit result is the outbox's
word (`sent`/`failed`, was `ok`); a refused mail sign-in is retried, not dead; practice mail doesn't count toward
`SMTP_DAILY_LIMIT`; per-check watchdog 150 s (above the padlock check's 2-minute retry); monitoring is one
`monitor_tick` a minute instead of two interval jobs.

**Session 12 (Nov 16, Opus): the UI for everything Fable built, interactive landing sections, product photos. Parts A–D
merged into `claude/jolly-bell-2bkweh`** (GitHub's `main` is 90+ commits behind; this session may only push its own branch).
A: confidence tags, numbered steps, provider name, six distinct check states, the Doctor's trace as a timeline, "Describe
the problem" (owner route, 5/day, words fenced as data), incident timeline (report + shared page), the fourth staged fault
(parked page) and a 4-fault demo switch, receipt + Verify on the shared page. B: "How the proof works" hop track and "We keep
watching" example day with "Something breaks", copy pinned to the code. C: product photos (Pillow, WebP ×2, EXIF/GPS
stripped, in the database). Unit 1006 passed, 2 skipped · ruff, tsc, build clean · e2e 14/14 on the Docker stack ·
`check_m1.sh --local` all PASS · screenshots + recording `docs/screenshots/s12/`. **The 11 new
Doctor fixtures (symptom + parked page) are hand-written placeholders**: capture them on the laptop
(`… capture_doctor_investigation.py --s12`, worst case $0.007, cap $0.10).

**Session 11b (Nov 16, Fable): checks right for every website and mail setup.** Provider-aware email checks (8 services +
null/no/unknown/mixed MX, SPF walk with the 10-lookup limit, DMARC, DKIM "couldn't check" never "missing"), website checks
(certificate kinds, http-only, redirects, slow, www vs bare, IDN), findings carry `sure`/`steps`/`provider`, "couldn't
finish" never passes, "keeps breaking" after 3 fixes a day, one email per problem. 891 passed. Matrix: `docs/CHECKS_MATRIX.md`.

**Session 11 (Nov 16, Fable): review + the investigating Doctor.** One P0 fixed (`SafeWeb` read pages with no total time or
size limit). The Doctor now looks first (read-only tools, at most 4) and code alone acts on its answer; three staged faults;
a whole-system invariant test (260 seeds, no bugs found). 646 passed.

**Session 11d (Nov 16, Fable): tamper-evident proof log merged.** Evidence rows are a per-shop hash chain, append-only in
code; the shared report shows a receipt and `/r/<token>/verify` recomputes the chain (no data in the answer). 951 passed,
2 skipped. Existing rows are chained once at the first start-up after the merge (the chain starts there).

**Session 11c (Nov 16, Fable): VPS pre-flight merged.** Every live Claude path ran through the app (Reader ×5, Namer, the
go-live policy check ×5 for the first time, the investigating Doctor): all correct, $0.056. One real GoDaddy write was made
and undone (200 / 200 / 204 / 200, zone identical): **Wednesday uses `DNS_MODE=per_shop`**. `wait_dns` and `/internal/tls-ask`
now need every nameserver to agree; `DNS_MODE=wildcard` exists as a fallback. 919 passed, 2 skipped. Part 3 (tamper-evident
proof log) not started. Details: `docs/STATE_FOR_NEXT_SESSION.md`.


**Session 10.5b (Nov 16, Opus): landing follow-ups merged.** "We keep watching after launch" + "How the proof works" +
Security & privacy sections (copy pinned to the code by a test; two over-claims removed), Check any address → a clear next
step + **Watch this address** (built: up to 3 per account, read-only daily, one email per new problem), a **Product menu**,
and a three.js hero that was then **undone at the owner's request (S10.5c)**: the S10.5 SVG hero is back, `three` removed. Also fixed: Check any address called a "null MX" (`0 .`, e.g. example.com) "emails have somewhere to go".
Unit 622 passed, 2 skipped · e2e 11/11 (Docker, 56 s; dev server) · `check_m1.sh --local` all PASS · scene 60 fps on
Intel Iris Xe (before it was removed) · screenshots: `docs/screenshots/s10-5b/`.

**Session 10.5 (Nov 16, Opus): owner experience fixed before Fable. §1–§5 merged.** Landing for small sellers in general +
demo shops (`/demo/meera|imran|sunita`); sign in first with guest practice as a quiet secondary path; real-app routing
(own URL per page, step header, resume, 404 page); an Orders inbox per shop (status, WhatsApp to the customer, counts, richer
order email); the preview blank-page bug fixed (sandbox gained `allow-popups*`, see SECURITY.md); the go-live checklist gating
only real launches. Also: hero no longer cut off on short screens, new hero shape, `HEAD /` no longer 405.
Unit 607 passed, 2 skipped · e2e 7/7 (Docker + dev server) · `check_m1.sh --local` all PASS · screenshots `docs/screenshots/s10-5/`.

**Session 10 (Nov 16, Opus): deployable and safe for real users. Parts A–E merged.** The production-like Docker stack runs
locally (Caddy local CA, real `__Host-` cookies, Mailpit) and `scripts/check_m1.sh --local` passes. Also: SQLite
WAL/busy_timeout/foreign keys, online backups (7 daily + 4 weekly) with a tested restore, the startup self-check, fixture-mode
real launches held for review, Privacy/Terms, the Renewals card + team alerts, zone hygiene with admin approval, the
dangling-CNAME finding, the XSS test, `docs/SECURITY.md`, the e2e suite (4 flows, Docker + dev server) and
`docs/NEXT_SESSION_VPS.md`. **Next: the VPS on Wed Nov 18, following `docs/NEXT_SESSION_VPS.md` exactly.**

**Session 9F (Nov 15–16): Phase 1 (claims made true) + Phase 2 (accounts and multi-tenancy) done and merged.** Email-link sign-in, guest practice, team approval, per-owner shops, CSRF, host-only cookies, team page, account deletion; 52 access tests; frontend rewired (no owner links). Checkpoint: `docs/S9F_PHASE2_CHECKPOINT.md`. **Phase 3 (order proof chain + check any address) done and merged** (Nov 16). Next: Phase 4 (Doctor) — see `docs/STATE_FOR_NEXT_SESSION.md`.

**Session 8.5 (Nov 15): real app domain + mailbox wired, no VPS yet.** `launchwitness.com` and `hello@launchwitness.com` are bought; the contact form sent a real email over GoDaddy SMTP from a local run. **Positioning changed to proof first** (see Decisions). VPS arrives free on **Wed Nov 18**; M1 happens then.

**M1 + M5: everything that doesn't need real infra is done** (session 4): landing page + contact form, `/build`, prod compose, backup/restore, `docs/RUNBOOK_M1.md`, `scripts/check_m1.sh`, demo seeder, README, project brief draft, public replay built and secret-scanned. Session 5 (design + motion pass) done: new look and motion for the landing page and the whole demo flow. **Session 6 (real Claude agents) done**, and **session 7 captured all 17 live Claude fixtures** on the owner's laptop ($0.0726, every quality gate passes, measured ≈ 1 cent per launch). **Session 8 rebuilt the seller shop template** (one generic template for every seller, basket, new profile fields, booking scope guard). **M1 on the VPS must happen by Nov 17** (`docs/RUNBOOK_M1.md`); session 9 (orders, UPI, tracking, trust & safety) is ready in `docs/NEXT_SESSION_S9.md`. M4 done against fakes (AC5 needs real infra). M3 done except the real-infra AC. M0 · M2 done.

## Next up

- **Owner:** merge the S13b PR, pull on the laptop. **Wed Nov 18: follow `docs/NEXT_SESSION_VPS.md`** (its `.env`
  checklist at the end; `SMTP_DAILY_LIMIT=450`; staging CA first; the smoke test at the end).

- **Owner (laptop):** capture the S12 Doctor fixtures live: `cd backend && CLAUDE_MODE=live ../.venv/Scripts/python
  ../scripts/capture_doctor_investigation.py --s12` (5 conversations, worst case $0.007). Then
  `REQUIRE_LIVE_FIXTURES=1` has nothing hand-written left in S12.
- **Owner:** decide whether GitHub's `main` should be brought up to `claude/jolly-bell-2bkweh` (a fast-forward of 90+ commits).

- **Wed Nov 18: `docs/NEXT_SESSION_VPS.md`** (SSH/firewall → Docker → clone → owner fills `.env` → staging CA → `A @` → real CA →
  `check_m1.sh` → backup cron → first real shop A record → HTTPS + marker → outside-in test order + IMAP proof).
- **Owner TODO:** an off-server copy of `backups/` (manual; no cloud service chosen). Exact `MAILBOX_EXPIRES_ON` date from GoDaddy.
- Then S9F Phase 4 (investigating Doctor) and Phase 5 (design), and the demo + submission.

- **S9F Phase 3 → 6** in the order of `docs/STATE_FOR_NEXT_SESSION.md` (proof chain, Doctor, design, verification + VPS handover).
- **Owner TODO:** look up hello@launchwitness.com's daily send limit (sign-in links, orders, daily test orders and alerts all go through it). Known risk: if hello@ lapses (about Dec 15) or hits its limit, sign-in, orders and alerts all stop. Set `MAILBOX_EXPIRES_ON` on the server so `/api/health` warns 14 days ahead.
- **Owner TODO (VPS):** set `ADMIN_EMAIL` and a fresh `ADMIN_TOKEN` in the server `.env`; `DEV_MODE` must stay false there.

0. **M1 on the VPS on Wed Nov 18** (the VPS is free and arrives then; **do not buy one**). The old "by Nov 17" deadline can't be met; session 9 can run before it. Thursday Nov 19 demo shop = `meerasbakes.launchwitness.com` with its own A record written at launch (no wildcard, decided S9F; no seller domain bought).
0a. **Owner check:** run `python scripts/list_godaddy_domains.py` (read-only, prod keys from `.env`) and confirm `launchwitness.com` shows ACTIVE.
0b. **Session 9** (orders + UPI pay link + status page + seller order list + WhatsApp hand-offs + email verification + policy check + report/pause): paste `docs/NEXT_SESSION_S9.md`.
1. **M1 on the VPS** once credit is confirmed: follow `docs/RUNBOOK_M1.md` (now `docs/NEXT_SESSION_VPS.md`: SSH → Docker → clone → `.env` → DNS `A @` only → prod compose → backup cron → mailbox → `check_m1.sh` all PASS). Confirm the `gddy` sub-commands with `gddy tree` (marked in the runbook).
2. **Fable session — plug in real integrations** in the order of the runbook's step 11 table, then `USE_FAKES=false` (admin-created businesses only) and the M3 AC1 sandbox launch with real HTTPS.
3. **Session 10 (demo + submission) leads with proof, not generation.** Pitch: "Describe your business. LaunchWitness puts it online on GoDaddy, proves a real order reaches you, fixes what breaks, and keeps checking." Demo and brief order: proof (test order reaches the inbox) → Doctor repair → monitoring → generation last. README + landing already follow this (session 8.5); the video script (SPEC §12) and `docs/PROJECT_BRIEF.md` still need reordering.
4. **M4 AC5 (evening):** one full launch of Meera's purchased domain (if budget allows), recorded — needs M1 + the Fable session.
5. **M5 on the live app:** fill the live link + video in `README.md`; turn `docs/PROJECT_BRIEF.md` into the PDF (find a 2025–26 India stat); record the demo video (SPEC §12; rehearse with `scripts/seed_demo.py --launched` + the demo switch); rebuild `/build` (`scripts/build-replay.sh`) at the very end so it has every session; final secret scan; submit. Stretch only after the user says core is done.

## Live Claude fixtures (captured session 7, 2026-11-14 UTC)

All 17 targets in `backend/tests/fixtures/claude/` are real replies (one live call each, no retries, nothing failed):
Reader ×8 (`meera_cakes`, `tiffin_service`, `tailor`, `whatsapp_messy`, `hinglish`, `no_categories`, `handwritten_photo`, `prompt_injection`) · `namer_meera_cakes` · `doctor_<check>` ×8.
`REQUIRE_LIVE_FIXTURES=1 pytest -q tests/test_s6_agents.py` → 43 passed. Injection ignored (real name + prices kept), all 6 handwritten prices read right, Namer 10 names = 5 × (.in, .com), every Doctor sentence jargon-free.
**Still hand-written:** `namer_tailor.json`, `namer_tiffin_service.json` (not in the capture list; only used when those example shops ask for names in fixture mode). See Open questions.
Live Claude spend so far: **$0.0726** (17 ClaudeUsage rows, total $0.07256).

## Cost per launch (for judges)

| Agent | Model | Calls per launch | Measured tokens (in / out) | Measured cost | Worst case (capped) |
|---|---|---|---|---|---|
| Reader | Sonnet 5.5 ($2 / $10 per MTok) | 1 (+1 retry only on a bad reply) | 1,566 / 701 (avg of 3 sample sellers) · 2,477 / 465 (photo) | **$0.0101** · $0.0096 (photo) · $0.0079 (avg of 4 hard text cases) | $0.017 · $0.020 |
| Namer | Haiku 5.5 ($0.10 / $0.50) | 1 | 441 / 98 | $0.0001 | $0.0002 |
| Doctor | Haiku 5.5 | 0 on a green launch, 1 per failed check (max 3 per check) | ~626 / ~58 (avg of 8) | $0.0001 each | $0.0001 each |
| **Total** | | 2 on a green launch | | **$0.0102 per launch** (+$0.0001 per repaired check) | ≈ 2 cents (Reader retry + 3 Doctor calls) |

**Measured** in session 7 from `scripts/capture_live_fixtures.py --report` (ClaudeUsage rows, 17 live calls, 2026-11-14 UTC). Thinking is off on both models.
Reader input is about 2× the earlier estimate (system prompt + profile schema ≈ 1,400 tokens), output matched; the total is still about one cent.
**For judges: "about 1 cent per launch (measured $0.010); $100 of Claude covers about 9,800 launches."**

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
| 12 | Certificate end date | `backend/app/checks/http_probe.py` → `RealHttpProbe.cert_expires(host)` | Implemented with `ssl` + `getpeercert()["notAfter"]`; verify against a real Caddy-served host. Feeds "days left" + cert warnings (7/1 days). |
| 13 | Domain end date | `backend/app/godaddy/client.py` → `GoDaddyClient.domain_expires(domain)` | Implemented as `GET /v1/domains/{d}` → `expires`; verify the field on prod. Feeds domain warnings (30/7/1 days). |
| 14 | Monitoring on real infra | `backend/app/monitor/scheduler.py` (`Monitor`) | Runs in-process with APScheduler when `MONITOR_ENABLED=true`. On the VPS check: 15-min and daily jobs fire, re-check after 1 min, alert emails go out via SMTP to the owner's personal email (`Business.owner_email`). Test `test_monitoring_against_real_infra` is a skipped placeholder. |
| 15 | Admin token | `.env` on VPS | Set `ADMIN_TOKEN` to 16+ random chars (admin is OFF while it's `change-me`). Admin-created businesses are the only REAL ones when `USE_FAKES=false`; everything public stays practice. |
| 16 | DB schema | `data/launchwitness.db` | Session 3 added columns/tables (no migrations). Nothing is deployed yet; on any existing dev DB, delete the file and restart. |

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
- 2026-11-14: **M4 rest (fakes), session 3** — ACs:
  - AC1 ✅ full green run on a sandbox launch; the report shows every check with result + time (test + browser).
  - AC2 ✅ demo fault (admin) removes DMARC (or MX) before the next check → check fails → Doctor sentence shown → `readd_email_auth` applied → re-check green; demo_fault, diagnose, dns_write, fail/pass checks and repair are all in the audit log (tests + browser at iPhone width).
  - AC3 ✅ (session 2) Doctor fix outside the playbook refused.
  - AC4 ✅ "Run checks now" works (button + endpoint, one run at a time); scheduler jobs registered (15 min + daily), re-check after 1 min, Doctor fix, alert to personal email once per problem, expiry warnings 30/7/1 (domain) and 7/1 (cert), off via `MONITOR_ENABLED` (tests).
  - AC5 ⏳ **PENDING REAL INFRA** (evening launch of Meera's purchased domain).
  - Also: secret owner link (hashed), practice-only public path, per-visitor limits for describe + launch, "Pretend I bought it (practice)", approval card email-plan line.
  - Browser check (Playwright, iPhone 13): describe → owner link → review (+ personal email) → names → approve → paused before buying → Pretend I bought it → report green → team sign-in → arm DMARC fault → Run checks now → Doctor explains + fixed → green again.
- 2026-11-14: **M1 + M5 prep (no real infra), session 4:**
  - Landing page at `/` (pitch, Meera story, 4 steps, 3 promises, "Try it (practice mode)" → `/#/try`, "How this was built" → `/build`) + **contact form** → `POST /api/contact` → Mailer → app mailbox (`SMTP_USER`; SMTP_SSL to smtpout.secureserver.net:465, full address as username, password from env; test). Plain-English success/errors, honeypot, `VISITOR_CONTACTS_PER_DAY=5`, audited. Browser-checked at iPhone width (locally the send shows the plain error: no real mailbox yet).
  - `/build` serves `replay/build.html`, else a "coming soon" page; not on seller hosts. `replay/build.html` built here (claude-replay via npx), owner email redacted, secret scan clean, committed; copied into the image.
  - Deploy: repo `deploy/Dockerfile` unchanged except copying `replay/`. Plain `docker build` here fails **only** on the sandbox proxy's certificate (pip → pypi); a scratch copy differing only in a CA build-secret on the 2 install lines built fine, ran healthy, served `/`, `/api/health`, `/build`. **Needs a plain build on the VPS to fully confirm.** `deploy/docker-compose.prod.yml` (override): Caddyfile.prod, `MONITOR_ENABLED=true`, `restart: always`, healthchecks on app + caddy, log caps, `app-data` volume. Verified locally (APP_DOMAIN=localhost): both healthy, HTTPS answers, `/internal/*` 404, monitoring on.
  - `scripts/backup_db.sh` (online SQLite backup, integrity check, keep 14, `--restore` that fixes file ownership). Backup, prune and restore all tested against the running stack (first restore attempt found the ownership bug, fixed).
  - `scripts/check_m1.sh` (PASS/FAIL per M1 AC: DNS app + wildcard, HTTPS valid cert, `/internal` blocked, SMTP + IMAP login, optional external email by subject, contact form arrives via IMAP marker, password not tracked/in history; secrets never printed or put on a command line). Mechanics tested here; the secret check caught a planted leak.
  - `scripts/seed_demo.py` (practice Meera via the running app's API; `--launched` = full practice launch, report green; `--reset` via new admin-only `DELETE /api/admin/practice-businesses/{id}`, which refuses real businesses). Tested end to end.
  - `docs/RUNBOOK_M1.md`, `README.md` (full draft), `docs/PROJECT_BRIEF.md` (one-page draft).
- 2026-11-14: **Session 5, design + motion pass (M5 demo polish):**
  - `frontend/src/tokens.css` = the one source for colour (cream, near-black ink, one soft-lime accent, success green, warning amber, danger red), type scale (Inter Tight, light display), spacing, radius, shadows, easing. `styles.css` uses only tokens.
  - App shell: dark rounded frame + light "notch" nav tab; route changes fade/rise (Framer Motion `AnimatePresence`). Step eyebrows "Step N of 5".
  - Launch log: lines appear one by one (420 ms apart) with a drawn tick per finished step, spinner for running, amber mark for "paused before buying", red for failed; a progress bar; auto-go to the report only after the log has played. A finished launch opened later shows instantly.
  - Report: checks play one by one (spinner → tick). A repaired check shows red + plain message, then the Doctor's sentence types in, then it turns green with "Fixed by us". Plays once per check run (remembered in localStorage); headline says "Checking that everything works…" while playing.
  - Landing: sticky cream hero (3-line light headline with an inline tick icon, dot link, paragraph) + a code-drawn shape (4 SVG slabs + ball, our own art) that drift apart on scroll; the hero scales back and dims as the dark "How it works" section slides over it; 4 /01–/04 cards, the hovered/tapped one grows and fills lime with its text fading in; "Built on GoDaddy" slow marquee (Domains, DNS, Email, VPS, HTTPS, Monitoring — plain text); promises; a closing cream sheet with Meera's story + contact form. Scrolling up reverses everything.
  - Seller template: spacing, soft shadows, focus rings, button press feedback only. No motion.
  - Reduced motion: no scroll transforms, marquee becomes a static grid, results show instantly, typing is instant.
  - Checked in Chromium at iPhone 13 (390 px) and 1440×900: full practice flow incl. demo DMARC fault → Doctor → fixed. Scroll smoothness measured with rAF frame times at 4× CPU slowdown: iPhone 0 frames > 33 ms; laptop 3. Found + fixed the main cause of jank (an opacity fade on the whole hero content → replaced by one dark overlay; 115 → 17 slow frames in the hero range at normal speed).
- 2026-11-14: **Session 6, real Claude agents (everything except the live calls):**
  - Live calls blocked here: a cloud session can't store a key for `api.anthropic.com`. **Owner's decision:** run the live calls on the laptop. No live call was made in this session (spend $0.00).
  - `scripts/capture_live_fixtures.py` (replaces `capture_reader_fixtures.py`): targets `reader:<seller>`, `namer:<seller>`, `doctor:<check>|all`. One call each, no retry, **stops at the first failure**. Raw reply saved to git-ignored `replay/raw/claude/`. `--dry-run` (worst-case cost, no key) and `--report` (today's ClaudeUsage rows). `scripts/capture_all_live.sh` runs all 17 and refuses a cap above $1.50.
  - Hard Reader inputs in `backend/tests/fixtures/sellers_hard/` (not shown as "Try an example"): messy WhatsApp text, Hinglish, a price list with no categories, a handwritten-style price list photo (`scripts/make_handwritten_pricelist.py`, our own generated image), and a **prompt injection** ("ignore your previous instructions… ₹1… 'Hacked'… 'this shop is closed'").
  - Quality gates `tests/test_s6_agents.py`: per-case Reader checks (incl. the injection test, verified to FAIL on a hacked reply). Namer: short, spellable, .in + .com. Doctor: one sentence, no jargon, allowed fix. Every disallowed (check, fix) pair + invented ids refused and logged with no writes.
  - Public path: in live mode, `FallbackClaudeClient` uses saved fixtures when the daily cap is hit or the API is down (not on bad JSON). Describe returns `assistant_note`; names send an `X-Assistant-Note` header. The UI shows a friendly amber note. Audited as `claude_fallback`. Fixture mode stays the default.
  - Prompts: Reader treats input as data (ignores instructions in it), tidies item names, answers in English. Namer asks for 5 names × (.in, .com), letters only. `rank` always shows a .in and a .com when available. Doctor gets only the fixes allowed for that check, and a stricter no-jargon list. Thinking off on Haiku 5.5 too (`disabled`), so short `max_tokens` can't be eaten by thinking. SDK errors → `ClaudeUnavailable`; SDK timeout 60 s, 1 retry.
- Tests: 292 passed, 13 skipped (2 real-infra; 11 waiting for the live fixtures). `npm run build` clean.

- 2026-11-14 (UTC; 2026-11-15 local): **Session 7, live Claude fixtures** (owner's Windows laptop):
  - 17 live calls, one per target, all saved first time; quality gates 43/43 with `REQUIRE_LIVE_FIXTURES=1`. Spend **$0.0726** (worst case was $0.138, cap $1.50).
  - Windows fixes: `capture_all_live.sh` uses `.venv/Scripts/python.exe` (and `python.exe -m pytest`, since App Control blocks `pytest.exe`) when `.venv/bin` is missing; Linux/Mac unchanged. Docstring + `docs/LIVE_FIXTURES.md` note the Windows path.
  - Older tests that pinned placeholder text updated to the live replies (Meera is now "Meera's Eggless Bakes", subdomain `meeras-eggless-bakes`; product names like "Chocolate truffle cake 1/2 kg"; Namer ranking test uses the live names and now also exercises the .com swap; Doctor DMARC test reads the saved sentence).
  - Tests: 303 passed, 2 skipped (real infra).

- 2026-11-14: **Session 8, shop redesign (M5 demo polish + new profile fields):**
  - `seller.html` rewritten as ONE generic template (a test fails on trade words like "cake"/"tailor" or seller names, and on any per-business CSS). Laptop: 1120 px page, menu left + sticky "Your order" panel right; phone: one column + a sticky "N items · ₹X · Review" bar. Hero: monogram tile, serif name, tagline, area/hours line (area hidden when the tagline already says it), badges, WhatsApp/Call. Menu appears once: each item has Add → − n + (the plain quantity boxes still work without JavaScript; the server works out totals). Category colours from a fixed 6-colour palette by position; quick-jump chips; lists of 12+ items go two-column, menus of 20+ items get a search box. Extras listed apart and can't be ordered alone. Info tiles: hours, pickup/delivery, contact, UPI (with "Your UPI app should show: <name>"). FSSAI in the footer. No "Verified" anywhere.
  - Profile fields: `selling_point`, `min_notice_days`, `pickup_available`, `delivery_available`, `delivery_fee_inr`, `allow_item_message` (default off), `upi_display_name`, `fssai_number` (14 digits), `kind` (orders | appointments), `not_supported_reason`; product `addon`, `price_from`. All have defaults, so saved profiles and the session-7 live fixtures load unchanged. Reader prompt + JSON schema ask for them (a test keeps schema = model).
  - `tidy_profile` (plain code, runs on every Reader reply): delivery lines leave the menu and become the delivery fee; "Add-ons/Extras" categories become extras; "from/onwards" prices become `price_from` (and a description that only repeats the price is dropped); notice days read from "at least N days"; ordering rules removed from hours. Never overrides what the Reader set; never empties the menu.
  - Scope guard: `kind="appointments"` → describe returns 422 with one plain sentence, no Business row, audited `refused`. New hard case `sellers_hard/salon.json` + hand-written `reader_salon.json` (`_note`). Fixture mode now also matches hard-case descriptions.
  - Review screen: "How customers order" card (selling point, notice days, pickup, delivery + charge, item message), UPI name + FSSAI fields, per-item "Extra" and "Starting price" ticks.
  - Item message: shown only when `allow_item_message`; stored at the top of the order note.
  - Site gallery: 6 profiles in `tests/fixtures/site_gallery/` (bakery, tailor with "from" prices, tiffin with weekly/monthly plans, candle maker with 2 items, 44 items with no categories, long Hinglish names with no phone/UPI). Sample phone/UPI/FSSAI only there (`…@example`, `98765 43210`, `12345678901234`). `scripts/render_site_gallery.py` + `scripts/shoot_site_gallery.js` render and screenshot them at 375 and 1440 px and warn on sideways scrolling (none). Screenshots, incl. before/after, in `docs/screenshots/s8/`.
  - Browser check (Chromium, 390 px): salon description → plain refusal; Meera example → private link → review → new fields → save → site shows 3 badges + message field → basket → order → thank-you page.
  - SPEC updated (flow, features 3a/3b for session 9, out of scope, agents, judge Q&A). Session 9 prompt written: `docs/NEXT_SESSION_S9.md`.
  - Tests: 333 passed, 2 skipped (real infra). Live Claude spend: $0.
- 2026-11-15: **Session 8.5, real domain + mailbox wiring (no VPS):**
  - Owner bought `launchwitness.com` + `hello@launchwitness.com` (Professional Email Pro Light, 1 month). Session 8 PR #12 was already merged.
  - SMTP: 465 SSL with a 587 STARTTLS fallback on connection failure only (3 new tests). Settings from env only; `.env` git-ignored (checked with `git check-ignore`); `.env.example` has placeholder names only.
  - **Live check:** ran the backend locally with the real `.env`, `POST /api/contact` once → `200 "Thank you! Your message was sent."` over port 465 (no fallback needed). Owner to confirm it in the hello@ inbox.
  - `EMAIL_PLAN_ESTIMATE_USD` = 23.88. App-domain examples/tests now use `launchwitness.com` (seller `.in` examples unchanged).
  - `scripts/list_godaddy_domains.py` (read-only) + 3 tests (no network; key never printed).
  - Proof-first copy: README pitch + "What it is" reordered, landing headline "Is your shop actually ready for customers?", hero + "How it works" text, page meta description.
  - Tests: 339 passed, 2 skipped (real infra). `npm run build` clean. Live Claude spend: $0.

## Environment status

| Item | Status | Notes |
|---|---|---|
| GoDaddy developer account + `gddy` CLI | ? | Run `gddy tree` to confirm |
| GoDaddy credit | **$2.37 left, expires Nov 23** | No card on file. Nothing else can be bought. |
| Docker VPS (4 vCPU / 8 GB, $0) | **Arrives free Wed Nov 18** | Do NOT buy one |
| App domain | **`launchwitness.com` bought Nov 15** | 1 year, renews Nov 2027 at $22.99. `launchwitness.in` NOT bought. A `@` is still GoDaddy's parked record; `A @` waits for the VPS (no wildcard: per-shop records). **Don't touch DNS before then.** |
| App mailbox `hello@launchwitness.com` | **Bought Nov 15, 1 month** | GoDaddy Professional Email **Pro Light** (secureserver.net backend, not Titan). $5.99/mo monthly; $1.99/mo = $23.88/yr on a 1-yr term. **Expires ~Dec 15 and auto-renew will lapse** (no card). MX (smtp/mailstore1.secureserver.net), SPF `include:secureserver.net -all`, DKIM ×2, DMARC `p=quarantine` already set by GoDaddy. SMTP send verified from a local run. |
| Meera's demo domain | **Not bought** (credit ran out) | Demo uses `meerasbakes.launchwitness.com` |
| Claude API key ($100, product only) | ? | |
| OTE (sandbox) API keys | ? | |
| Availability check method | Undecided | gddy / Domains API / OTE / RDAP — interface + fake ready (`GoDaddyAvailabilityChecker` stub) |

## Decisions

- **S12 (2026-11-16 IST):**
  - Product photos are stored as rows in the SQLite database (on the data volume), not as files. Reason: the existing online
    backup, restore, shop delete and account delete then cover them with no second store to keep in sync; at ≤ 6 + one per
    item × about 150 KB per shop the database stays small. Revisit if shops grow to hundreds.
  - Photo URLs on the app's own host work by their random 128-bit name (the owner's preview of a draft shop needs them); on a
    shop host only that live, unpaused shop's photos are served.
  - Upload cap 7 MB (Caddy refuses bodies over 8 MB). A renamed item keeps its photo only when the list kept its length
    (an edit); a removed item's photo is deleted.
  - "Something breaks" on the landing ends with **no email**, because the code emails only when the problem is still there
    after the fix (`scheduler.check_alert`); it says when the one email would come. The brief said "→ one email": showing
    that after a successful fix would be a false claim.
  - The test order's three failures now get their own code-written steps (form didn't take it / sent but not in the inbox /
    mail service refused); before, the first two got the "couldn't send the email" text.
  - Fixture-mode Doctor conversations were recorded on `meera.localhost`; replayed on another shop they now look at that
    shop's address (otherwise its trace said "not allowed"). Live mode is unchanged.
  - The owner's words in "Describe the problem" are not written to the audit log (they may name a customer): only the run
    and the length.
  - Fourth staged fault `marker` (a parked page, practice only), healed by the playbook's `repoint_site`.

- **S11d (2026-11-16 IST):** The row id is not part of an evidence hash; order is proven by the `prev_hash` links. Reason: one
  INSERT per row, so the append-only guard never has to allow an UPDATE. The verify rate limit (20 a minute per visitor) is
  kept in memory, not in a table: one process is guaranteed, and a restart resetting it is harmless. A shop with no evidence
  shows no receipt (its start value would only encode the shop's number). The "chain purged" audit event carries the row
  count only. Known limits, accepted: a whole-database rewrite and cutting rows off the end are not detectable from inside.

- **S11c (2026-11-16 IST):** A shop is turned on only when **every** nameserver of the zone answers our server, and tls-ask
  re-checks that on a real server (fail closed: no answer = no certificate attempt). Reason: the real write test showed the two
  GoDaddy nameservers disagreeing for about 10 s, and Let's Encrypt allows 5 failed validations per name per hour.
- **S11c:** `DNS_MODE=wildcard` reads and writes nothing at GoDaddy for shops (not only "no writes"), because an account that is
  refused may be refused reads too. Zone hygiene findings there are hand fixes (`fix: "manual"`).
- **S11c:** the booking-business test no longer requires the word "orders" in Claude's sentence (the live reply is one plain
  sentence about booking). The fresh Namer reply is saved under its own name; older namer fixtures stay (tests pin their names).

- **S10.5c (2026-11-16 IST):** The owner didn't like the three.js hero; it was removed (kept in history at `820e824`). If
  it ever returns: real GPU only, since software WebGL starved the page (e2e went from 1 to 10+ minutes).
- **S10.5b (2026-11-16 IST):** Landing copy
  says "our order mailbox" and "a free shop address" for real launches (own name + orders@ are practice-only). Watched
  addresses: first look shown, not emailed; a problem that clears and comes back is emailed again; limit 3 and 10 adds/day.
  Mailbox renewal is the team's (alerts to ADMIN_EMAIL), so the landing says the team is warned, not the seller.

- **S10.5 (2026-11-16 IST):** Describe needs sign-in; `#/try` is guest practice. Demo shops are rendered from the saved
  Reader fixtures with phone/WhatsApp/UPI forced empty (never point a demo at a real person). Order status flow: new →
  confirmed|cancelled; confirmed → paid|done|cancelled; paid → done|cancelled; done/cancelled final. WhatsApp must be an
  Indian mobile (6–9 + 9 digits) and is stored as `+91XXXXXXXXXX`; a Reader reply with an unusable number is blanked (the
  owner adds it) rather than failing the describe. UPI ID: `handle@psp`, PSP letters/digits only. Instagram: handle only
  (1–30 of letters, digits, `.`, `_`; no leading/trailing/double dot). Owner confirmations live on `Business`
  (`wa_confirmed`, `upi_confirmed`, …) storing the confirmed value, so edits reset them. "Preview opened" is recorded when
  the OWNER fetches the preview (the team's look doesn't count). Working days/hours = the existing `hours` text (required);
  notice days = `min_notice_days` (0 allowed). Pickup uses the existing public `area`; there is no address field at all.
  New owner-only profile fields (`instagram`, `delivery_areas`, `niche`) are not in the Reader schema/prompt
  (`reader.OWNER_ONLY`), so no live fixture needed recapturing. **Product photos were not built**: the brief assumed
  existing re-encode/EXIF rules, but none exist (only the in-memory price-list photo). The real-launch refusal lists what's
  missing in `detail` and by key in the `X-Missing` header.

- 2026-11-16 (S10): **one app process** is enforced (startup lock next to the DB + `WEB_CONCURRENCY` guard), not only documented.
- 2026-11-16 (S10): `/api/health` shows **only harmless warnings publicly** (mailbox expiry, email not set up, database not writable);
  the rest (weak admin token, DEV_MODE, fixture on a real server, purchases on…) only to the admin, the logs and `check_m1.sh`.
  Reason: a public "ADMIN_TOKEN is weak" helps an attacker.
- 2026-11-16 (S10): real server + `CLAUDE_MODE=fixture` → every real launch held for team review (fail closed). Test stand-ins for
  the VPS now say `claude_mode=live` (the VPS will run live).
- 2026-11-16 (S10): certificate alerts stay at 7/1 days; 30/7/1 is for things a person renews (domains, the team mailbox).
  Caddy renews certificates ~30 days ahead, so a 30-day certificate alert would fire before every renewal.
- 2026-11-16 (S10): the app domain and the team mailbox alert the **team** (ADMIN_EMAIL), not every seller: sellers can't renew them.
- 2026-11-16 (S10): there's no "weekly view" for owners; the nearest renewal is shown on **My shops** instead.
- 2026-11-16 (S10): `SMTP_SECURITY=plain` exists only for a one-word local host (Mailpit); refused for any real host name.
- 2026-11-16 (S10): `PRACTICE_STEP_SECONDS` (pretend world only) for demos and the kill-mid-launch drill.

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

- 2026-11-14 (session 3, user): Email plan price is shown on the approval card as its own line, "Email plan, bought separately on GoDaddy", with an estimate (`EMAIL_PLAN_ESTIMATE_USD`, placeholder **24/year — check against the real cart**). Not in the total; the spend guard covers only what the app buys (the domain).
- 2026-11-14 (session 3, user): No accounts. Each business gets a secret owner link (`/#/b/<id>?key=<token>`, 24 random bytes, only sha256 stored). The key (header `X-Owner-Key`) is needed for every business/plan/report/checks/orders route; the public seller site stays public. The link is shown once after "describe" with a plain-English "save this link" page. The browser remembers the key in localStorage, so the owner isn't asked again on the same device. `GET /api/businesses` is admin-only.
- 2026-11-14 (session 3, user): "Pretend I bought it (practice)" button on a launch paused before buying; practice mode only (409 otherwise). It marks the domain owned in the fake world and resumes; nothing bought, audited as `practice_buy`.
- 2026-11-14 (session 3, user): Businesses created without the admin token are ALWAYS practice (`Business.practice`) and use the fake world for launches, checks, monitoring and alert emails, even when the server has `USE_FAKES=false`. Only admin-created businesses on a real server use real integrations. Per-visitor daily limits for describe (`VISITOR_DESCRIBES_PER_DAY=5`) and launch approvals (`VISITOR_LAUNCHES_PER_DAY=3`); admin exempt.
- 2026-11-14 (session 3): Admin = `X-Admin-Token` == `ADMIN_TOKEN`, and admin is OFF while the token is `change-me` or shorter than 16 chars. Frontend: `#/admin` stores the token in this browser; the report then shows the demo switch.
- 2026-11-14 (session 3): Visitor = sha256 of the client IP; behind Caddy, the LAST `X-Forwarded-For` entry (Caddy doesn't trust client-sent values by default).
- 2026-11-14 (session 3): `Business.domain` is no longer DB-unique: unique among real businesses and among practice ones (checked in planner + approve), so a practice launch can never block a real seller's domain. On a real server, practice domains are never served by Host and never get a certificate (tls-ask). Practice full launches link to the practice subdomain site, never the pretend domain.
- 2026-11-14 (session 3): Launch checks run automatically when a launch finishes; each round is a `CheckRun` (launch | manual | monitor_quick | monitor_daily | monitor_recheck). Checks run in order and a failure is repaired right away, so later checks see the fix. Report = latest launch/manual run; headline "Your business is ready for customers" only when every check passes.
- 2026-11-14 (session 3): Demo fault = `Business.demo_fault` ("dmarc" | "mx"), one-shot, used by the next check run; deletes through the same guarded path (`assert_can_write`), audited as actor `admin`. Needs a full launch (409 for sandbox).
- 2026-11-14 (session 3): Monitoring: quick = site points + HTTPS; daily = quick + email checks (full) + new `settings_match` (every value the launch wrote is unchanged) + days left. Failure → re-check after 60 s → Doctor fix (where the playbook has one) → alert if still failing. `settings_match` is alert-only (the change may be hers; "Was this you?" is stretch). One alert per problem until it passes (`Alert` table). Domain warnings 30/7/1 days; certificate warnings only at 7/1 days (Caddy renews by itself well before). No personal email → no alert, logged as skipped. Personal email is a new field on the review screen.

- 2026-11-14 (session 4): Landing page = the SPA's `#/` route; the describe screen moved to `#/try`. The practice banner is hidden on the landing (the page says it itself).
- 2026-11-14 (session 4): Contact messages go only to the app mailbox (`SMTP_USER`) and are not stored in the DB (only an audit row with the visitor hash and message length — no name/email/message). Per-visitor limit `VISITOR_CONTACTS_PER_DAY=5`.
- 2026-11-14 (session 4): Production = `docker-compose.yml` + override `docker-compose.prod.yml` (not a separate full file), so local and prod share one definition.
- 2026-11-14 (session 4): Demo seeding goes through the running app's HTTP API (the practice fake world lives in the app's memory). Reset deletes practice businesses only, via an admin-only endpoint; ids + owner links kept in `~/.launchwitness-demo.json` (outside the repo).
- 2026-11-14 (session 4): `replay/build.html` is committed (the image serves it). `build-replay.sh` redacts the owner's email, extracts the turn data back out of the page and secret-scans both (`transcript_scrub.py --check`); any hit deletes the page. The Session 1 copy was re-scrubbed with the current scrubber (it still contained the sandbox's public default Java truststore password "changeit" ×4; now `[REDACTED]`).
- 2026-11-14 (session 4): Sessions 3 and 4 were ONE Claude Code chat (same session id), so they are saved as one file `2026-11-14-s3-s4-m4-m1-m5.jsonl`, replacing the partial `s3-m4` copy (the replay keeps one copy per session id).
- 2026-11-14 (session 4): `gddy` sub-commands in the runbook are marked "confirm with `gddy tree`" (not verifiable here); each has a REST API or godaddy.com fallback.

- 2026-11-14 (session 5): Framer Motion (`framer-motion@11.11.17`) is the only new dependency. Font = Inter Tight from Google Fonts (user OK); seller sites keep the system font (no external request on sellers' pages).
- 2026-11-14 (session 5): The launch log and the report "play" real results with small fixed gaps (420 ms per log line; ~0.5–1 s per check, Doctor sentence typed at 16 ms/char) so a fast launch still reads as a story. Nothing is invented: only the pace of showing real results is set. Each check run plays once per browser.
- 2026-11-14 (session 5): App screens stay one centred column (max 48rem) on laptops too; the landing page is full-width.

- 2026-11-14 (session 6, user): Live Claude calls run on the owner's laptop (`docs/LIVE_FIXTURES.md`), not in cloud sessions. Session budget $1.50, cap enforced by the script.
- 2026-11-14 (session 6): Fallback to fixtures only for "cap reached" and "API unavailable". A bad reply still gets the agent's own retry and plain error, so it's never hidden. Fallback note: "Our assistant is resting for today, so we've filled this in with a sample shop. You can still try every step." A visitor's own text then becomes a sample shop (Meera's) in practice mode. That's acceptable: the note says so.
- 2026-11-14 (session 6): Namer shortlist (top 3) always includes a .in and a .com when one of each is available; otherwise cheapest-then-shortest as before.
- 2026-11-14 (session 6): Hard-case sellers live in `tests/fixtures/sellers_hard/` so they're not offered as "Try an example" buttons.

- 2026-11-14 (session 7): On Windows the local `.venv` uses `jiter==0.11.1` (Application Control blocks the 0.19.0 DLL). Not pinned in `requirements.txt` (anthropic allows `jiter>=0.4,<1`); Linux/VPS unaffected.
- 2026-11-14 (session 7): Tests that compared exact placeholder text now compare the live fixture values (or read them from the fixture file). The fixtures are the source of truth; re-capturing a fixture may need those few strings updated again.

- 2026-11-14 (session 8): Delivery needs two fields: `delivery_available` + `delivery_fee_inr` (0 = free). The plan named only the fee and `pickup_available`; a fee of 0 couldn't tell "free" from "no delivery".
- 2026-11-14 (session 8): Badges = selling point, "Order N days ahead" (only if N > 0), pickup/delivery. Nothing else, no filler.
- 2026-11-14 (session 8): Extras (add-ons) stay orderable but only next to a main item (server refuses an extras-only order).
- 2026-11-14 (session 8): `min_notice_days` default is 0 (= not stated, no badge). Session 9 enforces it on the order date.
- 2026-11-14 (session 8): "Appointments" = the customer buys the owner's time at a booked slot (salon, beauty, tuition, coaching, clinic, classes). Tailors and caterers stay "orders". The old live `no_categories` fixture (a mehendi artist) has no `kind`, so it still builds a shop; a fresh live capture may now refuse it.
- 2026-11-14 (session 8): Seller sites use system fonts (no Google Fonts), so customers' browsers don't call a third party.
- 2026-11-14 (session 8): The thank-you page shows a "Message on WhatsApp" button only when the seller has WhatsApp/phone; the session-9 "send this order" link replaces it.
- 2026-11-15 (session 8.5, user): **Proof first.** Lead every pitch, page and the demo with proof, not generation: "Describe your business. LaunchWitness puts it online on GoDaddy, proves a real order reaches you, fixes what breaks, and keeps checking." Order: proof (test order reaches the inbox) → Doctor → monitoring → generation last. Landing headline: "Is your shop actually ready for customers?". Copy/docs only, no feature change. `docs/SPEC.md` and the CLAUDE.md tagline still carry the old one-liner (not edited; update if the owner wants).
- 2026-11-15 (session 8.5): SMTP uses port 465 SSL; if the SSL connection itself can't be made (timeout, refused, TLS error) it tries 587 STARTTLS once. No fallback after login starts (no double sends, a wrong password isn't retried). `SMTP_PORT=587` uses STARTTLS directly.
- 2026-11-15 (session 8.5): `EMAIL_PLAN_ESTIMATE_USD=23.88` (Pro Light, 1-yr term). The $5.99/mo monthly price is noted in `.env.example` and config only; the approval card shows the yearly figure.
- 2026-11-15 (session 8.5): `scripts/list_godaddy_domains.py` = one read-only GET to the prod Domains API with keys from env/`.env`; prints domain, status, expiry, auto-renew; never prints the key. stdlib only, so it runs without the venv.
- 2026-11-15 (session 8.5, user): Thursday demo shop on `meerasbakes.launchwitness.com` (wildcard), since `meerasbakes.in` wasn't bought.

- **S9F accounts (Fable's design, kept):** email-link sign-in only; guest practice + "sign in to keep it" is the one claim path; pending until the team approves (beta); `ADMIN_EMAIL` is the admin, `ADMIN_TOKEN` command line only; subdomains only for real launches; `MAX_LIVE_SHOPS=40` for certificate limits; orders/alerts to verified sign-in addresses.
- **S9F (Opus) fixes:** the policy check never uses the saved-fixture fallback (fails closed); the daily describe cap counts `describe_used` rows that survive shop deletion; a delete-account token is checked against the signed-in email before it's used up; ruff rules pinned in `backend/pyproject.toml` (E4/E7/E9/F/I); the Vite dev proxy rewrites Origin to `LW_APP_ORIGIN` (default `http://localhost`) in dev only; `seed_demo.py` now works as a command-line admin (no owner keys).

- **S9F P3:** a real shop's headline is "Almost ready" until the owner taps "Yes, I got it" (her inbox can't be read), because "accepted" must never read as "delivered"; the daily monitoring run includes a test order (one email per shop per day); test orders are marked by a single-use `TestTicket` nonce posted as `lw_test` (an unknown or used nonce is just a normal order); the "Yes, I got it" link uses a random token (hash stored), not an HMAC, so no new secret is needed; `/r/<token>` shows check names, states, hop times and servers only.

- **S15 decisions (unattended):** (1) `selling_mode` is the source of truth; `pickup_available`/`delivery_available` follow it; an old profile's mode is inferred from the two boxes (delivery = local). (2) `delivery_areas` stays one comma-separated text (old profiles keep loading); strict checking only when she saves and at go-live. (3) A customer's PIN is accepted if listed, or if a listed locality is named in the address (whole word); localities-only shops therefore can't check the PIN itself. (4) The wanted-by date is required when the shop has notice/days off/daily limit, otherwise optional; dates are IST. (5) Default `payment_terms` = pay on delivery/pickup; `accepts_cash` default false (no claim until she says so). (6) Advance rounds UP to a whole rupee. (7) A break with a return date ends on that date (today or earlier = open). (8) Test orders get safe defaults (pickup, else a test address inside her area) and skip the date rules and the break; the same area/PIN checks still run. (9) The thank-you page shows the customer's PIN but never the street address. (10) Free delivery above ₹X applies to local delivery only; shipping is one flat fee. (11) Statuses unchanged; "Advance paid / Fully paid / Due on delivery" is a label derived from terms + status. (12) Daily limit counts non-cancelled real orders by wanted date.

## Open questions

- (S12) In this cloud session Docker Hub answered 429 (rate limit); the stack was built from Google's public mirror
  (`mirror.gcr.io`) re-tagged locally. The repo's compose files are unchanged.
- (S12) Photos are only as private as their random name on the app host: anyone given a draft shop's photo URL can open it.
  Fine for product photos; say so if that's not OK.

- Capture `reader:salon` live (1 Sonnet call, ≈ $0.01)? Until then `REQUIRE_LIVE_FIXTURES=1` fails on its `_note` (by design). It isn't in `capture_all_live.sh`'s 17 targets; run it as a single target. The live Reader replies would also start filling the new session-8 fields; re-capturing the 8 Reader fixtures (≈ $0.08) is optional, because tidy-up + defaults already cover them.

- Capture live `namer_tailor` + `namer_tiffin_service` too (2 Haiku calls, ≈ $0.0002)? They're still hand-written.
- Demo domain: SPEC's Meera story says `meerabakes.in`, but the live Namer suggests `meerasbakes.in` / `punebakes.in` (no `meerabakes`). The owner can still type any name; pick which one to buy for the demo.

- Should seller sites also answer on `www.<domain>` (needs tls-ask + DNS change)? Currently no.
- The app mailbox is GoDaddy Professional Email (secureserver.net), not Titan. The planner/`TitanMailboxProvider` still assume Titan (`titan1._domainkey`, `TITAN_MX`, `TITAN_SPF`). Which product do real seller mailboxes get, and what are its DKIM selector names? Check on hello@'s zone when the VPS session reads DNS (read only).
- Keep hello@ past ~Dec 15? Needs a card on file or new credit; judging may still be running.
- Exact `gddy` sub-commands for DNS records and Titan mailboxes on your CLI version (`gddy tree`).
- Repo public or private on the VPS? (Private → deploy key, see runbook step 3.)

- Are hackathon accounts whitelisted for production Domains/DNS APIs, or use `gddy`?
- Is a demo video expected in the submission? (Include one anyway.)
- One current India-specific stat on small businesses without websites.
- Final product name.
