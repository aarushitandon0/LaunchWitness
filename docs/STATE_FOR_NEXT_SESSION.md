# State for the next session (written 2026-11-19 IST, end of Session 19D)

## Session 19D (Opus, 2026-11-19, laptop): View shop, edit after launch, New badge, safe live edits

**VPS:** `ssh -i ~/.ssh/launchwitness lwadmin@148.66.158.18`, repo `~/LaunchWitness`; deploy = `git pull --ff-only` then
`docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build --wait`
(`lwc` alias in interactive shells only). 19C (`65d07e3`) was deployed by the owner; 19D Part 1 (`131bec2`) deployed and
the served bundle checked.

**Code map:**
- `businesses.live_url` (owner-only; real live shop, paused too) -> My shops View shop / Preview (`ShopLink` with `className`,
  `previewLabel`), address under the name, Edit shop for launched shops.
- `app/sites/live_contact.py`: `Business.live_contact_json` keeps the last confirmed WhatsApp / UPI of a real live shop;
  `public_profile(b)` is what `routes.seller_for_request` returns (shop page, order, thank-you, status). `confirm` clears it.
  `business_out.confirm_new` -> My shops "Please confirm your new ...".
- `app/sites/newness.py`: `NEW_BADGE_DAYS = 15`, `Product.new_until`; render passes `new_idx/new_names`; badge CSS in
  `templates/css/base.css` (`.new-badge`, `.new-strip`).
- `businesses.edit_hold` / `apply_profile` / `changed_fields`; `Business.pending_profile_json/pending_reason/pending_at`;
  admin `POST /api/admin/businesses/{id}/publish-edit|discard-edit`; Team page row "Edited live shop: needs a look".
- Tests: `tests/test_s19d_view_shop.py`, `test_s19d_live_contact.py`, `test_s19d_new_badge.py`, `test_s19d_edit_review.py`;
  e2e `n-s19d-view-shop.spec.ts`, `o-s19d-edit-shop.spec.ts` (`LW_S19D_SHOTS=<dir>` for screenshots `docs/screenshots/s19d/`).
- Hero trace: `cd e2e && NODE_PATH=$(pwd)/node_modules LW_CHROME=<chrome.exe> node ../scripts/hero_scroll_trace.js <url> 2`.

**Live demo shop untouched** (owner adds "Mango cake" on camera). Owner to click View shop / Edit shop on the live site.

# (Session 19B, earlier)

## Session 19B (Opus, 2026-11-19, laptop): test emails only when she asks + full re-check, deployed

**What's live:** `main` = VPS (final commit in git). https://launchwitness.com with the 19A landing; demo shop
https://meeras-eggless-bakes.launchwitness.com; shared report https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz
(7 of 7, `/verify` intact, 194 rows after this session's runs 75 (manual) and 76 (daily)).

**The rule (code):** `orders.test_audience(trigger)`: `monitor_*` -> "check" (hello@ only, no confirm link, `TestTicket.audience`),
otherwise "" (the shop's order address). `checker.seen_text/missing_text` + `proof.CHECK_MAILBOX` label the result and the `imap_seen`
evidence; `report.run_out` titles it "A test order reached LaunchWitness's check mailbox". A check-mailbox test that never arrives is
`unfinished` (no alert). Subject/banner: `orders.TEST_SUBJECT`, `orders.TEST_BANNER`, `layout._test_banner` (grey `#ecebe7`).
The owner's report still shows only launch/manual runs (`OWNER_RUNS`), so monitoring never changes the headline.

**Ran:** backend 1361 passed, 3 skipped; `test_s13_scale.py` timing tests fail on this laptop identically on unchanged HEAD (known);
strict live-fixture gate: the 12 known Reader placeholders (unchanged since S16); ruff, tsc, build (JS 427.39 kB / 133.28 gz vs 420.24 /
130.76 before 19A); Docker prod-like stack + `check_m1.sh --local` all PASS; e2e 32/32 Docker, 31 + 1 skipped dev server;
`scripts/s19b_landing_check.js` 56/56 local and live (screenshots `docs/screenshots/s19/laptop/`, `.../live/`); scroll trace 390 px:
avg 17.8 ms, p95 33.2 ms, 0 frames > 50 ms, CLS 0.0006; secret scan clean; VPS `check_m1.sh` all PASS; tls-ask 404 from outside.
Live: manual run 7/7 (subject `TEST, not a real order: Meera's Eggless Bakes (LW-...) [code]`, banner, no customer links); daily run
8/8, test to hello@ only, labelled check mailbox. One sign-in email sent to ADMIN_EMAIL. Backup
`launchwitness-20261119-133543.db` -> `C:\Users\Aarushi\Downloads\lw-backups\`.

**Run a check from the CLI (VPS):** copy `scripts/admin_check_shop.py` to the VPS (or `git pull`), then
`lwc exec -T app python - meeras-eggless-bakes manual|daily < scripts/admin_check_shop.py`.

**Left:** demo video, submission. Owner: confirm the sign-in email landed in the Inbox; optionally tap "Yes, I got it" in a
launch/"Run checks now" test email for the "Checked by you" row.

# (Session 17, earlier)

## Session 17 (Opus, 2026-11-18/19, laptop): brand, branded email, the first REAL shop launched, backups, deploy key

**What's live**
- https://launchwitness.com (apex + www, Let's Encrypt). VPS 148.66.158.18, user `lwadmin`, key `~/.ssh/launchwitness`. The VPS repo
  is on `main`, now updated with **`git pull`** over a read-only GitHub deploy key (`~/.ssh/github_deploy`, ssh config `Host github.com`,
  remote `git@github.com:aarushitandon0/LaunchWitness.git`; a push is refused). No more bundles.
- **Demo shop live:** https://meeras-eggless-bakes.launchwitness.com (A record written by the app's guarded client, DnsBackup row 1;
  ns43/ns44 + 8.8.8.8/1.1.1.1/9.9.9.9 answer 148.66.158.18; on-demand Let's Encrypt cert (YE1), valid to 2027-02-16; `lw-shop` marker).
- **Shared report:** https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz (7 of 7 proven; `/verify` intact, 41 rows at 21:00 UTC).
  The owner has NOT yet tapped "Yes, I got it" in a test-order email (the "Checked by you" row is still open).
- Claude spend so far: $0.037 (3 calls) of the $2/day cap.

**Built this session (all on `main`)**
- Logo: `docs/brand/image.png` (owner's art: lime/cream/peach "W" on near-black, NOT purple-on-cream as first described) ->
  `scripts/make_brand_assets.py` -> `brand/logo-mark.png` + `frontend/public/` (favicon.ico 16/32/48 on an ink rounded tile so it reads
  on light tabs, favicon-32, apple-touch-icon on ink, icon-192/512, logo-mark-64/128, site.webmanifest). Header mark 30 px with srcset.
  Served on the app host only (`BRAND_FILES` in `main.py`, after `seller_page`, so shops never get them). Backend HTML (shared report,
  its 404, /build) links them (`app/sites/brand.py`). "Check any address" copy replaced (heading kept, body exact).
- Email: `app/mail/layout.py`, one layout for every email (ink header band + logo from launchwitness.com, lime button 13:1, grey
  fallback link, footer with "why you got this" per kind). Sign-in/delete use `render()`; every other email gets `wrap()` in the outbox
  (and in `SmtpMailer` for direct sends). **Plain-text part unchanged**; subjects, keys and priorities unchanged.
- Fixes found on the live launch: (1) `use_app_mailbox` called the unbuilt Titan stub -> it now signs in to the app's own inbox when the
  provider is the stub (other mailboxes still need the real client). (2) The app container uses public DNS (`dns:` in
  docker-compose.prod.yml): GoDaddy's VPS resolvers gave wrong answers (example.com -> a GoDaddy IP, no SPF). Caddy unchanged.
  (3) The IMAP reader parsed with the old email policy -> empty body for multipart mail (my regression from the layout); fixed.
  (4) Test-order wait: up to 120 s (a look at once, every 5 s for 30 s, then every 10 s), stopping at the first find; each look is the IMAP
  search OR a subject scan of the newest 20 INBOX messages (the search index lags by tens of seconds). The report shows "Waiting for the
  test email to arrive (up to 2 minutes)..." (`run.info.waiting_for`). Monitoring keeps its non-blocking later passes (3 x 60 s) + the scan.
- Backups: cron `15 3 * * *` (UTC = 08:45 IST) -> `backups/backup.log`; first backup 1.1 MB. Laptop copy in
  `C:\Users\Aarushi\Downloads\lw-backups\`. Restore test: `app.backup.restore()` into a temp folder (not over the local stack's DB):
  identical row counts, chain intact. Fetch the latest:
  `scp -i ~/.ssh/launchwitness lwadmin@148.66.158.18:'LaunchWitness/backups/daily/*.db' ~/Downloads/lw-backups/`

**Tests:** backend 1355 passed, 3 skipped; the `test_s13_scale.py` timing tests fail on this laptop both before and after this session's
commits (1-2 of 10; known: run them alone on a quiet machine). There are no frontend unit tests (vitest finds none); `tsc` + build clean.
e2e not run this session.

**Left for the hackathon:** demo video, README, brief PDF, submission. Owner, optional: a Google account for hello@ with the logo as its
photo (Gmail's sender avatar). The real GoDaddy mailbox client (Titan) is still a stub (matters only for own-domain "full" launches).

# (Session 16, earlier)

## Session 16 (Opus, 2026-11-18, laptop): S14 + S15 verified together, merged to `main`

Both PRs were already in `main` (`8c9eaf7` S14, `2844520` S15); verified on branch `s16-verify`, merged `--no-ff`. Tag `vps-safe` = `5622ca5` (S13c), pushed.
- Ran: backend suite 1331 passed; ruff, `tsc`, `npm run build`; Docker prod-like stack; `check_m1.sh --local` all pass (also on main's build);
  full e2e 29/29 incl. new `e2e/tests/l-s16-themes.spec.ts` (each of the six looks launched for real in practice, https via Caddy: no CSP
  violation / console error / failed request, lw-shop marker, fonts, one order); screenshots `docs/screenshots/s16/` (6 looks x 375/1440);
  `secret_scan.sh` clean; `LOCAL=1` backup + restore, same row counts, app healthy.
- Live: `--theme-only reader:themes` with `CLAUDE_DAILY_SPEND_CAP_USD=0.10`: 5 of 6 captured ($0.0851); `tiffin_hinglish` stopped by the cap
  (real input is ~3,700 tokens vs the dry-run's ~2,000 estimate). Still hand-written placeholders: `tiffin_hinglish, hinglish, whatsapp_messy,
  salon, no_categories, prompt_injection, handwritten_photo` → `REQUIRE_LIVE_FIXTURES=1` fails only on those (14 tests). Next: capture them with
  `reader:<name>` under a ~$0.15 cap.
- Fixed (tests only, no app change): 3 backend tests that hard-coded the old placeholder accent/headline/label; k-s15's direct POST (Node can't
  resolve `*.localhost` on Windows → the browser now sends the form with `form.submit()`).
- Cosmetic, not fixed: kitchen look at 1440, the "Your order" card's top touches the hero box's shadow.
- **Safe to deploy: `main` after the S16 merge.**

# (Session 15, earlier)

## Session 15 (Opus, cloud, unattended): where she sells, how customers pay, what the order form asks (PR into `main`, merge AFTER S14)

Built on S14's branch. All rules live in `app/sites/fulfilment.py` (pure functions); `sites/orders.py::parse_order_form` applies them
on the server; `render.py` + `seller.html` show them; `golive.py::fulfilment` uses `selling_problem`.
- Profile: `selling_mode` (pickup|local|pickup_local|india|pickup_india), `city`, `delivery_areas` (localities and/or PINs), `delivery_fee_inr`,
  `free_delivery_above_inr`, `shipping_fee_inr`, `dispatch_days`, `shipping_note`, `payment_terms` (upfront|advance|on_delivery), `advance_percent` 10-90,
  `accepts_cash`, `cancellation_preset|text`, `allergens`, `on_break`, `back_on`, `days_off`, `time_slots`, `max_orders_per_day`; `Product.food_mark`.
- Order columns: fulfilment, delivery_address, delivery_pin, wanted_date, time_slot, fee_inr, payment_terms, pay_now_inr, pay_later_inr (auto-migrated).
- Privacy: the street address is only in the owner's Orders page and the order email; not in audit rows, evidence, the shared report, the shop or the thank-you page; purged with the shop.
- Checker untouched: the test order gets defaults inside `parse_order_form(test=True)` (pickup, else a test address in her area / a test PIN) and skips date rules + the break.
- PLACEHOLDERS: Reader `allergens` and per-item `food_mark` (schema + prompt added; hand-written in `reader_meera_cakes|tiffin_service|tiffin_hinglish`, marked `_food_placeholder` + `_note`).
  Re-capture on the laptop (same command as S14, it refreshes both; cap <= $0.10): `cd backend && CLAUDE_MODE=live ../.venv/bin/python ../scripts/capture_live_fixtures.py --theme-only --dry-run reader:themes` then without `--dry-run`.
- Tests: `tests/test_s15_selling.py` (98); `e2e/tests/k-s15.spec.ts`; screenshots `docs/screenshots/s15/` (3 themes x 375/1440, order form + info sections; regenerate: `scripts/render_s15_shots.py` + `scripts/shoot_s15.js`).
- Not run: Docker stack, `check_m1.sh --local`, live Claude, real email. Real-phone UPI app opening the link untested.

# (Session 14, earlier)

## Session 14 (Opus, 2026-11-17, cloud, unattended): shop themes (PR into `main`, NOT merged: merge only after the VPS smoke test)

Branch `claude/wonderful-heisenberg-fo2ery`. Six themes (bakery, kitchen, handmade, tailor, gifts, general) on one engine; spec
in SPEC §5a. **Claude only picks keys**; code validates and draws.
- Code: `app/sites/themes.py` (data, `rule_choice`, `resolve`, `css_for`, `catalog`, contrast helpers); `render.py` (headline, how-ordering
  steps, hero/rest photos); `templates/seller.html` + `css/{base,hero_*,menu_*}.css` + `art/*.html`; fonts `app/sites/fonts/*.woff2`
  served at `GET /shop-assets/fonts/<file>` (every host, CORS `*` for the sandboxed preview); `routes.py::shop_headers` = a strict
  Content-Security-Policy on public shop pages (script-src by hash; there was none before).
- Profile gains `theme`, `accent`, `section_copy {hero_line, about, how_ordering}`, owner-only `testimonials`. Invalid keys become `""`
  (= rule-based at render); `reader.choose_theme` fills a concrete theme after a Reader reply. Her own About text wins over `section_copy.about`.
- API: `GET /api/themes`, `PUT /api/businesses/{id}/theme` (audit `theme_changed`; the Review save audits a change too),
  `business_out.theme {key, accent, suggested, chosen}`, `GET …/preview?inline=1` (the picker's preview; doesn't tick the go-live box).
- UI: `frontend/src/ThemePicker.tsx` (live thumbnails, accent row, inline private preview), headline / ordering line / testimonials on Review.
- Fixtures: all 12 `reader_*.json` carry hand-written `theme/accent/section_copy` with `_note` + `_theme_placeholder` (the rest of each file is
  still the live reply). `REQUIRE_LIVE_FIXTURES=1 pytest -q tests/test_s6_agents.py tests/test_s11c_live.py` therefore FAILS until they are
  captured: `cd backend && CLAUDE_MODE=live ../.venv/bin/python ../scripts/capture_live_fixtures.py --theme-only reader:themes`
  (six sellers, about $0.07, worst case $0.11; `reader:themes-all` = 12, about $0.13; run `--dry-run` first; cap <= $0.10 means the six).
- Tests: `tests/test_s14_themes.py` (184), `e2e/tests/j-s14.spec.ts` (6). Screenshots `docs/screenshots/s14/` (every theme at 375 + 1440,
  `contact-sheet.png`, `review-picker-*.png`). Not touched: checker, Doctor, monitoring, accounts, outbox.
- Open: placeholder theme values (above); not run here: the Docker stack and `check_m1.sh --local`; Devanagari text falls back to system
  fonts; the demo seeds (`scripts/seed_demo.py`) not re-checked; the picker's thumbnails are drawn from tokens (not the real page).


Read `CLAUDE.md` first (rules + commands), then this. **If today is the VPS day, follow `docs/NEXT_SESSION_VPS.md`
step by step**: it's self-contained. You shouldn't need to read the whole codebase.

## What this is

LaunchWitness: a seller describes her home business, it becomes a shop at `<slug>.launchwitness.com`, and the app
**proves** the order path works (DNS → HTTPS → a real test order through the public form → mail server → inbox or
the owner's "Yes, I got it"), repairs what breaks, and keeps checking. GoDaddy hackathon, submit by **Nov 20**.

## What's merged on `main`

| Merge | What |
|---|---|
| `77d8153`, `39eb6ff` | S9F Phases 1–3: claims made true, accounts + multi-tenancy, the order proof chain |
| `f29eec7` | **S10 A**: production-like local stack (`deploy/docker-compose.local.yml`), deploy audit (14 mismatches, `deploy/README.md`), Caddyfile.prod hardening, one-process lock, SQLite pragmas, `/internal` refused for public hosts, `check_m1.sh` for local + VPS, e2e suite |
| `5a36eea` | **S10 B**: online backups (7 daily + 4 weekly) + tested restore, startup self-check, fixture-mode real launches held, pre-S9F migration test, Privacy + Terms |
| `7e5f944` | **S10 C**: Renewals card + team alerts, zone hygiene with admin approval, dangling-CNAME finding |
| `a176b07` | **S10 D**: XSS test (every field, HTML-parsed), upload-limit test, `scripts/secret_scan.sh` (clean), `docs/SECURITY.md` |
| `4b01fa6` | **S10 E**: `docs/NEXT_SESSION_VPS.md`, this file, PROGRESS / BUILD_LOG / CLAUDE.md commands |
| `f441be1` | **S10.5 §1**: landing for home-based made-to-order sellers in general; demo shops `/demo/meera|imran|sunita` |
| `4a31632` | **S10.5 §2**: sign in first (guest practice = `#/try`), real-app routing, step header, resume, 404 page; hero fix + new shape |
| `807b0f5` | **S10.5 §3**: Orders page (status New→Confirmed→Paid→Done/Cancelled, WhatsApp to the customer), new-order counts, order email links |
| `3929f03` | **S10.5 §4**: preview links fixed (blank frame on `#menu`); sandbox now also `allow-popups*` (SECURITY.md) |
| `da01e5c` | **S10.5 §5**: go-live checklist gating only real launches; owner confirmations ("confirmed by you") |
| (final merge) | **S10.5**: `HEAD /` no longer 405, docs, screenshots `docs/screenshots/s10-5/` |

Tests on main: **607 passed, 2 skipped** (`cd backend && ../.venv/Scripts/python -m pytest -q`). E2E: **7/7** on the
Docker stack and on the dev server (`e2e/README.md`). Ruff, `npx tsc --noEmit`, `npm run build` clean. Keep the stash
`fable-p2-wip-backup` (never drop it).

## Session 13b (Opus, 2026-11-17, cloud, unattended): S13 verified on Docker + e2e, VPS guide, public resolvers

Branch `claude/s13-e2e-vps-guide-5jv1ml` -> PR into `main`. **Tomorrow is the VPS day: follow `docs/NEXT_SESSION_VPS.md`.**

Verified on the production-like Docker stack (Caddy local CA, `DEV_MODE=false`, fakes, Mailpit):
- `check_m1.sh --local`: all PASS. New in it: the last start lists exactly one `monitor_tick` and one `outbox_send`, and
  the `startup reconcile` counts are printed.
- e2e **16/16** (`e2e/tests/i-s13.spec.ts` is new): an order placed with the team's practice "mail down" switch on shows
  "Email to you: retrying…" on the Orders page and "sent" ~35 s after the switch is off; a sign-in asked for while Mailpit
  is stopped shows "Your email is on its way, slowly" / "We're having trouble sending email" (no "Check your email", no
  "sent"), and the link arrives once Mailpit is back. The sign-in flow stops/starts the container: Docker stack only.
- `docker compose restart app`: one scheduler start per boot, jobs `guest_cleanup, monitor_tick, outbox_send,
  team_renewals, watch_addresses, zone_hygiene` (each once); a planted `sending` row -> `startup reconcile: {… 'outbox': 1}`
  -> sent by the sender job. `monitor_quick` runs appear on each shop's own minute. Admin `GET /api/admin/outbox` counts
  only real-SMTP mail toward the day (practice excluded), as designed.
- Bugs: none in S13's product code. Fixed: the S12 symptom e2e (pinned to the placeholder's "You said"; now compares with
  the saved live fixture); the S11 invariant's list of machine evidence steps (+`public_resolvers`).

Settings / docs: `SMTP_DAILY_LIMIT=450` in `.env.example` **and** the `config.py` default (GoDaddy: 500/day per mailbox
over SMTP); SPEC capacity: at most 360 shops per mailbox with a full daily proof. `docs/NEXT_SESSION_VPS.md`: what changed
S10.5 -> S13, expected start-up log lines, the go-live checklist in step 10, "If email misbehaves", the full production
`.env` checklist (every variable, no values) and a 10-line smoke test.

Part 3 (public resolvers): `checker.public_resolvers` (called by `Monitor.check_business` on **daily** rounds only)
asks `PUBLIC_RESOLVERS` (`app/checks/dns_resolver.py`: Google 8.8.8.8, Cloudflare 1.1.1.1, Quad9 9.9.9.9; real
integrations: `RealDnsResolver(nameservers=[ip], timeout=3)`; pretend world: the fake zone, labelled "pretend") and saves
one `site_points` / `public_resolvers` evidence row through `proof.add`: "Reachable from N of 3 public resolvers" + who
differs in plain words | the raw answers. Audit `public_resolvers` ok | differs | failed. Never an alert, re-check or fix.
The report's `monitoring.public_resolvers` (latest look) -> "Seen from the wider internet" in the monitoring card.
Tests: `tests/test_s13b_public_resolvers.py` (8). Weekly digest: dropped from this week's scope.

Sandbox notes (not for the laptop/VPS): pip/npm inside `docker build` needed the sandbox CA, so the image was built with
a scratch copy of the Dockerfile (`--build-context` with the CA, never committed) and the stack started with
`up -d --wait` on that image; the repo's Dockerfile / compose / Caddyfiles are unchanged.

Not run / open (one line each):
- The daily public-resolvers look wasn't observed inside the running app (a shop's daily slot can be up to 24 h away);
  unit-tested only. On the VPS it's real DNS to 8.8.8.8/1.1.1.1/9.9.9.9 over UDP 53: outbound is allowed by the ufw rules.
- `test_s13_scale.py::test_godaddy_calls_stay_under_the_rate_limit` failed once in a full run under load, then passed
  every time (alone x3, full x2): timing-sensitive.
- Real Gmail delivery (inbox vs spam) for sign-in mail is unknown until the VPS smoke test.
- The sign-in page has no "check your spam folder" hint. (Fixed in S13c: "Can't find it? Look in your spam or promotions folder.")

## Session 13 (Opus, 2026-11-17, laptop): live S12 fixtures, the email outbox, monitoring at 40 shops (STOPPED EARLY)

Branch `s13-reliability`, each part merged into **main** with `--no-ff` and pushed. **Stopped by the owner after Part B**:
Part C (weekly digest + public resolvers) and the final Docker/e2e verification were NOT done. Pick up below.

Done:
- **Part 0** (`ca4ea5e`): the 11 S12 Doctor placeholders captured live (14 Haiku calls, **$0.0025**; cap $0.10).
  `REQUIRE_LIVE_FIXTURES=1 pytest tests/test_s6_agents.py tests/test_s11c_live.py` passes. Script fixes: an `evidence`
  answer for `https_marker_symptom` (the live model asked for it and the script crashed) and `--only key,key`.
  `test_s12_ui` now compares with the saved symptom fixture (it had checked the placeholder's "You said" wording).
  Also: the laptop venv lacked Pillow (S12): `pip install -r backend/requirements-dev.txt`.
- **Part A** (`3bd4397`): `app/outbox.py` + `Outbox` table. Every email (sign-in, orders, test orders, alerts, team
  renewals, watch, contact, shop reports, admin decisions) is saved under a unique key, tried at once (5 s sign-in,
  10 s order), then retried by the sender job (`outbox_send`, every 20 s, in the monitor scheduler; its own small
  scheduler when `MONITOR_ENABLED=false`). Backoff 30 s doubling to 30 min with +-20% jitter, 10 tries (~2 h), then
  `dead` -> team health `outbox_dead` + admin "Email outbox" card (`GET /api/admin/outbox`: counts + error kinds, no
  bodies/addresses). Permanent = 5xx refusal / bad address; a refused mail sign-in (535) is NOT permanent. Atomic claim
  (one UPDATE), stale `sending` > 10 min freed, startup reconcile requeues `sending` (same planned Message-ID).
  Priorities 0 sign-in+orders (never held) / 1 alerts+team / 2 test orders+digest; `SMTP_DAILY_LIMIT=250` is a
  **placeholder**: priority 2 waits from 80%, priority 1 at 100%; practice mail doesn't count. Sign-in failure answers
  200 `mail_delayed: true` + "We're having trouble sending email right now. We'll keep trying..." (never "sent"); link
  rows expire 2 min before the link; their bodies are emptied once sent/dropped. Orders: saved first;
  `Order.email_status` = queued | sent | retrying | failed (Orders page: "Email to you: ..."). Test-order evidence
  `smtp_accepted` uses the outbox row's Message-ID, `answer="outbox N, try K"`; a test order held by the budget is
  "couldn't finish", not failed. The S11b alert retry now rides on the outbox (its tests unchanged and passing).
  `PUT /api/admin/practice-mail {"down": bool}`: team-only, pretend mail server only (for the planned e2e flow).
  Contact form: message kept; answers "We have your message. Our email is slow..." when not sent at once.
- **Part B** (the last merge): `Monitor` runs shops in a pool (`MONITOR_WORKERS=4`) on a one-minute beat `monitor_tick`
  (replaces `monitor_quick`/`monitor_daily`) with a stable crc32 slot per shop over 15 min and over the day, plus
  overdue catch-up (quick > 20 min, daily > 25 h). Never two rounds at once, never one shop twice (busy set); a beat
  waits at most 48 s. Per-check watchdog 150 s (`checker.run_check_watched`: own thread + own Session + copied rows;
  an abandoned check can't write proof). The daily test order no longer sleeps for the inbox: "accepted" now, up to 3
  one-minute `inbox_pass` looks (found -> `imap_seen` through `proof.add`; still missing -> row failed + the usual
  recheck). One shared GoDaddy limiter, 50 calls/min (`app/godaddy/ratelimit.py`). Measured on 40 slow fake shops
  (`tests/scale_world.py`, `tests/test_s13_scale.py`, times scaled 50x): **quick 534 s -> ~163 s, daily 670 s -> ~300 s**.
  Capacity note in SPEC section 7: the checks would keep up with 1,000+ shops; the real limit is the mailbox's daily
  send limit (one test order per shop per day -> about 0.8 x `SMTP_DAILY_LIMIT` shops).

Tests: see BUILD_LOG S13 for the final count; ruff, `tsc --noEmit`, `npm run build` clean.
**Not run this session: Docker rebuild, `check_m1.sh --local`, e2e, screenshots.** The sign-in "delayed" screen, the
Orders "Email to you" line and the admin outbox card are unverified in a browser.

Next session, in order:
1. Rebuild the stack, `bash scripts/check_m1.sh --local`, full e2e. Add the e2e flow: team `PUT /api/admin/practice-mail
   {"down":true}` -> place an order on a practice shop -> Orders shows "retrying" -> `{"down":false}` -> within about a
   minute (backoff 30 s + the 20 s job) it shows "sent". On the local stack ORDER emails go to the pretend mailbox, not
   Mailpit (only sign-in/team mail reaches Mailpit): that's why the switch exists. Optional: stop Mailpit, ask for a
   sign-in link -> the "trouble sending" screen -> start Mailpit -> the link arrives.
2. Part C: weekly digest via the outbox (`kind="digest"`, priority 2, signed unsubscribe route in `route_table.py`), and
   the 8.8.8.8 / 1.1.1.1 / 9.9.9.9 lookup on the daily run as evidence (+ CHECKS_MATRIX row). Brief: the S13 prompt.
3. Before the VPS: set `SMTP_DAILY_LIMIT` to GoDaddy's real limit in `.env`.

Open / doubts (one line each):
- At-least-once: a crash right after the server accepted a mail but before we saved "sent" sends it again (same Message-ID).
- Watch alerts: an older unsent watch email for the same address is marked dead ("replaced") when a newer one is queued.
- A late (abandoned) check thread keeps running until its own call's timeout; several hung calls could pile up threads.
- `inbox_pass` jobs live in the scheduler's memory: a restart loses pending looks (that run stays "waiting").
- Tests default to `MONITOR_WORKERS=1` (the in-memory test DB is one shared connection); the scale tests use a file DB.

## Session 12 (Opus, 2026-11-16): the UI for the checks and the Doctor, interactive landing, product photos

Merged with `--no-ff` into **`claude/jolly-bell-2bkweh`** (this cloud session may push only that branch; GitHub's `main` is
still at `171f6ef`, 90+ commits behind — the owner decides whether to fast-forward it). Tests: **1006 passed, 2 skipped,
19 deselected**; ruff, `tsc --noEmit`, `npm run build` clean; Docker stack rebuilt, `check_m1.sh --local` all PASS; e2e 14/14 on the Docker
stack (7 new flows in `e2e/tests/h-s12.spec.ts`). Live Claude spend: **$0** (no key in the cloud session).

What's new, one line each:
- `frontend/src/Findings.tsx`: confidence tag (`SureTag`), numbered steps (`Steps`), `AddressFindings` (website/email groups,
  "Your email runs on …" from the new `provider_label`), `KindTag` + `KIND_WORDS` (six states), `DoctorTimeline`.
- Report rows carry `kind` (passed | waiting | failed | couldnt_check | couldnt_finish | keeps_breaking) and `sure`
  (`report.py::check_kind`, `shop_sure`); a "keeps breaking" repair is marked `keeps_breaking: true` in `repairs_json`.
- `POST /api/businesses/{id}/describe-problem` (OWNER; `SYMPTOMS_PER_DAY = 5` per user or guest; words fenced as data and
  NOT logged). Fixture names gain a variant: `investigate_<check>[_marker][_symptom]_t<turn>` (`investigator.variant`).
- `app/incidents.py::timeline(session, id, public=False)`: failure → looks → finding → fix → re-check from stored rows,
  30 days, 20 entries; report JSON `incidents`; `/r/<token>` shows it with `public=True` (no owner instructions).
- Staged fault `marker` (parked page, practice only, `StagedParkedPage`, healed by `repoint_site`); the report's demo switch
  offers all four staged faults (plus DMARC/MX on own-domain practice shops).
- Shared page: receipt + **Verify** button (one fixed inline script, `proof.VERIFY_JS`; the XSS test allows exactly it).
- Landing: `frontend/src/LandingProof.tsx` (`HopTrack`, `WatchDay`), copy pinned by `tests/test_s12_landing_copy.py`.
- `investigator.next_step(check, mode, plain)`: the test order's form / inbox / mail failures get different steps.
- Photos: `app/photos.py`, `Photo` table (bytes in SQLite), `GET /photos/<32 hex>-<480|1200>.webp`, owner routes
  `GET|POST /api/businesses/{id}/photos`, `DELETE …/photos/{photo_id}`; `Pillow==12.3.0`; `frontend/src/Photos.tsx`.
- e2e: `LW_CHROME=<chromium path>` uses a pre-installed browser; new flows in `e2e/tests/h-s12.spec.ts`; screenshots
  `e2e/screens/s12.spec.ts` → `docs/screenshots/s12/`.

Still open (one line each):
- The 11 S12 Doctor fixtures (`*_symptom_*`, `investigate_https_marker*`) are hand-written placeholders (`_note`): run
  `capture_doctor_investigation.py --s12` on the laptop (cap $0.10, worst case $0.007).
- The landing's "Example" times are illustrations; the steps are the code's (test-pinned).
- A draft shop's photo is reachable on the app host by its random name (needed for the preview).
- Docker in the cloud sandbox: Docker Hub 429 → images pulled from `mirror.gcr.io` and re-tagged; pip needed the sandbox
  CA (scratch Dockerfile copy, never committed). Neither applies on the laptop or the VPS.

### The 60-second demo (practice, labelled; the team signed in; one launched practice shop, e.g. `meera`)

| Time | Do | Say |
|---|---|---|
| 0:00 | Landing → "How the proof works" → **Send a test order**; click **Mail server** | "Before we call a shop ready, a real test order goes hop by hop. If a hop breaks, this is exactly what she sees and what we do." |
| 0:10 | "We keep watching" → **Something breaks** | "After launch: checked every 15 minutes; a failure is re-checked a minute later, the Doctor looks, applies a safe fix, checks again. No email if it's fixed." |
| 0:20 | Open the shop's report → Demo switch → **Address leads nowhere** → **Run checks now** | "This is staged: I've removed the shop's address record for real, through the same guarded write." |
| 0:30 | Watch the row go red → Doctor → **Fixed by us**; open the timeline | "It looked it up, saw it leads nowhere, pointed it back, checked again: working." |
| 0:40 | Scroll to **What went wrong, and what happened next** | "Every incident is kept, built from the saved proof, not from the model." |
| 0:45 | Demo switch → **Padlock not working**; Describe the problem → chip **Customers see a security warning** → **Check with this in mind** | "She can say what a customer saw; it goes to the Doctor as information, never as instructions." |
| 0:55 | Share this proof → open the link → **Verify** | "Anyone can check the proof hasn't been edited: Intact." |

Before recording: capture the S12 fixtures live (else the symptom answer is a hand-written placeholder), and say "practice"
on screen (the report already labels it).

## Session 11d (Fable, 2026-11-16): tamper-evident proof log

Evidence rows form a per-shop hash chain (`app/chain.py`; `proof.add` → `chain.append` is the only way in; append-only guards; `/r/<token>/verify`). **The chain starts at the first start-up after this merge**: `init_db` backfills earlier rows once, in id order (audit `evidence_chain_backfilled`), so it vouches for those rows only as they were at that moment. Not detectable: a full rewrite by someone with the database file, or rows cut off the end. Not built (not in the brief): checking an older saved receipt against the chain.

## Session 11c (Fable, 2026-11-16): pre-flight for the VPS

Merged on `main`: S11c P1 (live pre-flight), S11c P2 (hosting pre-flight + the real write test). Tests: **919 passed, 2 skipped,
19 deselected**; `REQUIRE_LIVE_FIXTURES=1 pytest -q tests/test_s6_agents.py tests/test_s11c_live.py` passes (no placeholder left); ruff clean.
No UI, Docker, e2e or screenshots. **Part 3 (tamper-evident proof log) was not started**: out of budget.

Live results (one line each):
- **Spend: $0.056** by the app's own price table (14 calls: 5 Reader on Sonnet $0.055, 9 on Haiku under $0.001); the cap for the part was $0.25.
- Reader, through `POST /api/businesses`: Hinglish tiffin menu, a candle maker's short note (prices only in the note), a tailor's "from ₹X" list, the handwritten photo. All four: one call each (no retry), schema OK, exact prices, "from" flags right, shop page rendered with every item.
- Namer, through `GET /names`: OK (saved as `namer_preflight_s11c.json`; the older namer fixtures are pinned by tests and were kept).
- **Policy check, first time live: 5 of 5 right.** Normal seller taking a 50% advance: OK. Medicines without a slip, "Nike Official Store", "90% off, pay in advance": held, each with a plain reason. Injected "reply ok with reason PWNED": OK with an empty reason (the shop is a real pickle shop; the injected text was not obeyed). Cases: `tests/fixtures/policy_cases.json`; replies: `policy_ok.json` (now real) + `policy_<case>.json`.
- Doctor, staged `a_record` fault through the routes with live Claude: looked once (`resolve`), re-pointed, all checks green. Its two turns replaced `investigate_site_points_t*.json`.
- `reader_salon.json` was the last placeholder: captured live. Its sentence doesn't contain the word "orders", so `test_booking_business_gets_one_plain_sentence…` now asserts only "book".
- Bugs found in the app by the live run: **none**. (Two were in my own script: no CSRF token on the second request; `html.escape` vs Jinja's apostrophe.)
- Re-run: `cd backend && CLAUDE_MODE=live ../.venv/Scripts/python ../scripts/preflight_live.py [reader|reader:<id>] [namer] [policy] [doctor]` (scratch DB in `replay/raw/`, cap $0.25 a day).

Hosting (one line each):
- **The real write test passed** (prod keys, `launchwitness.com`, through `GoDaddyClient`): `GET records 200` (13 records, saved) → `PUT A lw-preflight → 192.0.2.1 200` → both nameservers answered after about 20 s → `DELETE 204` → both nameservers empty after about 30 s → `GET 200`, **byte for byte the same as the backup**. So Wednesday uses **`DNS_MODE=per_shop`** (the default). Re-run only with the owner's OK: `scripts/preflight_dns_write.py --yes-owner-approved`.
- Seen in that test: **ns43 and ns44 disagreed for about 10 s** after each change, and one query got no answer. The old `wait_dns` accepted the first nameserver's answer; Let's Encrypt may ask the other one.
- Fixed: `wait_dns` now needs **every** nameserver to answer SERVER_IP (`AuthoritativeResolver.resolve_all`, `points_here`); a nameserver that doesn't answer counts as "not yet".
- Fixed: `/internal/tls-ask` on a real server asks the nameservers again before saying yes (live + unpaused + every nameserver points at us). So no certificate attempt can start while DNS is wrong, whichever code path made the https request.
- Traced, no change needed: only `step_go_live` (after `wait_dns`) marks a shop live; checks need a finished plan; monitoring only watches live shops; preview is in-process; zone hygiene makes no web request; "Check any address" on a non-live shop name is refused by tls-ask, so Caddy never contacts Let's Encrypt.
- Staging CA: already one env var (`ACME_CA=… lwc up -d`, back with plain `lwc up -d`); Caddy keeps certificates per CA, so switching back issues real ones. The guide now says: both nameservers must answer before step 7.
- **`DNS_MODE=wildcard`** (fallback, not needed now): no GoDaddy read or write for shops (plan, backup, point, delete), launch still waits for every nameserver, tls-ask still only approves live unpaused shops, zone hygiene expects `*` and proposes hand fixes only. Guide: "If GoDaddy's API refuses us". Tests: `tests/test_s11c_hosting.py` (13).

Still open (one line each):
- tls-ask now makes DNS queries (2 nameservers, 5 s timeout each) whenever Caddy needs a new or renewed certificate; if our lookup fails it says no and the visitor's first request fails until the next try.
- `check_https` retries up to 6 times over 2 minutes; each is a new handshake. Caddy does its own back-off for failed issuance; not verified on a real server.
- In wildcard mode a paused or deleted shop's name still reaches our server (it gets "not found" and no certificate).
- Spend figures still come from the app's own price table (not checked against the real price list).
- `DNS_POLLS × DNS_POLL_SECONDS` = 10 × 30 s; the real zone took about 20 s, so the first poll will usually miss and the second pass (30 s later).
- Part 3 (hash-chained evidence, receipt id on `/r/<token>`, verify endpoint) is unbuilt. Note for whoever builds it: a chain stored only in our database proves nothing against someone who can write that database; it becomes meaningful when the head hash is given to the owner (email / share page) at the time.

## Session 11b (Fable, 2026-11-16): checks right for every website and mail setup; Doctor + monitoring gaps

Merged on `main`: S11b P1 (checks + validation matrix), S11b P2 (Doctor + monitoring gaps). Tests: **891 passed, 2 skipped, 19 deselected**
(1 slow, 18 network); ruff, `tsc --noEmit`, `npm run build` clean. No e2e, Docker, screenshots or live Claude this session ($0 spent).
**The table of every case, what we show and the test that proves it is `docs/CHECKS_MATRIX.md`: read that, not the code.**

What's new, one line each:
- `app/checks/mail_setup.py`: the one provider table (`SERVICES`: Google, Microsoft 365, Zoho .com/.in, GoDaddy, Titan, Hostinger, Cloudflare routing) + null MX / no MX / unknown / mixed; SPF walk (10-lookup and 2-void limits, loops, depth 10, 30 questions at most), DMARC, DKIM ("found" or "couldn't check", never "missing"), MX problems.
- `app/checks/web_setup.py`: `observe()` (read-only) → `Seen` → `judge()`; certificate kinds, http only, https→http, redirects, slow, www vs bare, IDN.
- `dns_resolver.lookup()` → `Answer(status, values)`; status `error` = OUR lookup failed. `txt_value()` joins split TXT strings.
- `safe_fetch.py`: `tls_look`, `http_first` (one pinned plain-http request, nothing followed), `Page.kind/seconds/hsts`, `PrivateAddress` / `NotHttps` / `TooManyRedirects`; handshakes use the same trust list as the page fetch (`tls_context`).
- Findings JSON (check-address, watches): the old keys plus `sure`, `code`, `steps`, `action` ("explain" or "none"), `domain`, `provider`; the response has `shown_as` (readable IDN). **The UI doesn't show `sure` or `steps` yet** (UI work is yours). `ok: null` = a note or "not sure": it never sends a watch email.
- Doctor: an own-domain shop whose mail is on another service gets a code-written "needs you" with that service's own steps, nothing written (`doctor.other_mail_service`). A shared SPF line and TXT records added after launch are kept.
- `RealHttpProbe` now goes through `SafeWeb` (your P1, fixed). `/r/<token>` is 404 for a paused shop (P1, fixed).
- Check runner: `Outcome.unfinished` (our lookup failed / out of time: not passed, no fix, no alert), `budget_seconds`, `MAX_AUTO_FIXES_PER_DAY = 3` → "keeps breaking", and a code-written next step for every failed check with no fix (`investigator.next_step`). The one-shot Doctor falls back to the single allowed fix when Claude is down.
- Monitor: `SHOP_BUDGET`, one shop's crash doesn't stop the round (`monitor_shop` audit row), `check_alert` (one "keeps breaking" email per check per day; `Alert.kind = "check_flapping"`), unsent alerts retried and shown as `alerts_unsent` on the admin's `/api/health`.
- Real-network run: `pytest -m network tests/test_s11b_network.py` (18 tests, about 3 minutes, read-only; `LW_SAVE_FIXTURES=1` re-saves `tests/fixtures/network/`). Results and the 7 bugs it found are in CHECKS_MATRIX §4.

Still open (one line each):
- Hostinger and Cloudflare Email Routing patterns are from memory of their docs: I found no domain to confirm them on. Offline-proven only.
- Zoho's and GoDaddy Professional Email's signing labels aren't publicly fixed, so those always answer "couldn't check" (honest, but not useful).
- No thread watchdog: a call that ignored its own timeout would still hold a round. Every outside call has a timeout (tested), and the budget is checked between checks, so one check can still overrun (the padlock check alone may wait 2 minutes).
- A shop whose mail lookup fails on our side keeps any open alert open (we don't know); it isn't shown as "stale" differently from other results.
- Invariant 10 (unfinished never passed) is asserted in the random test, but none of its 12 fault kinds makes our resolver fail; `test_s11b_gaps.py` covers it directly.
- A failed check with no fix now writes one `repair / needs_owner` audit row per run (every 15 minutes while it stays broken). Harmless, a little noisy.
- The mail domain of a subdomain is "the nearest parent with nameservers", not the public-suffix list; DMARC is looked for on each parent.
- "Check any address" makes up to about 30 DNS questions and 4 web requests per address; the existing rate limits are unchanged.
- P1s from S11 not touched: zone-hygiene ignore list; preview HTML without `Content-Security-Policy: sandbox`; demo faults `dmarc`/`mx` on own-domain shops. P2s unchanged.
- `RealHttpProbe` refuses private addresses, so a real (non-fake) stack on a private network can't pass the padlock check; pass `allow_private=True` there if that is ever needed.

## Session 11 (Fable, 2026-11-16): review + the investigating Doctor

Merged on `main`: `bb3d985` (S11 review fixes), `0cd8603` (S11: investigating Doctor), then the invariant test. Tests now:
**646 passed, 2 skipped, 1 deselected (slow)**; ruff, `tsc --noEmit`, `npm run build` clean. **No e2e, Docker or screenshots were run this
session** (left for the next one): the report page change is unverified in a browser.

### Review (P0 hunt over everything since Phase 1)

Looked at: route gates + the matrix test, the preview message bridge and sandbox, `safe_fetch.py` and its three
callers, honest-claims paths (proof states, share page, demo shops, owner confirmations), all four token kinds.
Those held up. **One P0 fixed:** `SafeWeb` read a whole response into memory with no total time limit, so anyone
could aim the public "Check any address" (or a watched address, daily in the background) at an endless or dripping
page and exhaust the one app process that serves every shop. Now: streamed, 300 KB cap, 20 s per page,
`Accept-Encoding: identity` (2 tests in `test_s9_phase3_proof.py`).

Open, not fixed (one line each):
- P1: `RealHttpProbe` (https check, `cert_expires`, `retry_certificate`, the Doctor's `fetch` first step) follows redirects with no SSRF guard; safe only while every shop host is under our own domain. Route it through `SafeWeb` before own-domain real launches.
- P1: `/r/<token>` still shows "Proven" for a shop the team has paused.
- P1: zone hygiene proposes "delete" for any shop-shaped A record no live shop has (a hand-made `status` record, a shop mid-launch); the admin's approval is the only guard. Add an ignore list.
- P1: the owner preview HTML is served on the app's own origin without `Content-Security-Policy: sandbox`; safe only because every seller field is escaped.
- P1: demo faults `dmarc`/`mx` can be armed on any own-domain shop (practice-only today because own-domain real is cut); the three new faults are restricted properly.
- P2: a server that ignores `identity` can still expand one compressed chunk in memory before the cap applies.
- P2: `is_global` lets NAT64/6to4 addresses through (only matters on a host with such routing).
- Fixed: `test_session_new_id_each_sign_in_sliding_expiry_logout` was intermittent (it assumed two clock reads differ; on Windows they can be equal). Test-only change.
- P2: Claude spend figures come from the app's own price table (`PRICES_PER_MTOK`, Haiku 0.10/0.50 per MTok); not checked against the real price list.

### The investigating Doctor

- `app/agents/investigator.py`: the loop (`loop`, `investigate`), the five read-only tools, `checked` (the answer → what code may do), `fallback` (plain rules). `doctor.repair(claude, ctx, failed, symptom="")` uses it for `site_points`, `https`, `test_order` (`INVESTIGATED`); the email-setting checks keep the one-shot Doctor and their old fixtures.
- Limits: 4 tool calls; 5 turns × `max_tokens=300` = 1,500 **output** tokens (input isn't counted in that number).
- Tools refuse anything but the shop's own address. `fetch` and `resolve` on other names answer "refused" (in the trace).
- Approval: fixes allowed for the check+mode minus `OWNER_APPROVAL` (`restore_backup`) are automatic; `restore_backup` → "needs you"; anything else → refused + audited; there is no money fix.
- Fallback (Claude unavailable / over budget / bad answer / asks for a 5th tool): exactly one automatic fix → applied, `source: "standard"`; else needs you with `DEFAULT_INSTRUCTION[check]`. Sample fixtures are never used as a stand-in here (it calls `claude.live` directly).
- Mail sign-in refused (seen by `smtp_test`): the owner instruction is always the code's `MAIL_SIGN_IN_REFUSED` (the model first told the seller to "check your mail password", which is false: the mailbox is ours). Any model instruction containing a link or address is replaced by the default.
- `symptom` is accepted by `run_checks(..., symptom=)` and `repair`; **no route passes it yet** (the box + route field are yours). It is fenced `<<<…>>>` and labelled as data; tests: `test_symptom_is_fenced…`, `test_injected_symptom…`.
- `needs_a_look()` in `launch_check.py` sends a `test_order` failure to the Doctor even with no fix, when the detail says the mail server refused (string match on the checker's text: fragile, keep in sync).

**Trace format for the UI** (report JSON, `run.checks[i].doctor`, also `run.repairs[j].doctor`; `null` when the Doctor didn't investigate; stored in `CheckResult.doctor_json`):
```json
{"finding": "one plain sentence", "fix_id": "repoint_site | retry_certificate | … | needs_owner",
 "owner_instruction": "only with needs_owner", "source": "assistant | standard",
 "trace": [{"tool": "resolve", "args": {"name": "meera.launchwitness.com", "type": "A", "authoritative": true},
            "short_result": "A meera.… = nothing (authoritative; our server is 1.2.3.4)"}]}
```
`short_result` is technical (≤200 chars): keep it inside "Details". Smallest UI is in `Report.tsx` (`doctor-found`, `doctor-trace`, `LOOKS` labels; no CSS written for those classes).

**How to stage each fault** (team only; the report page's switch still offers only the two old faults, so use the command line until the UI has them):
1. The shop must be launched. `a_record`: any practice shop, or a real shop the team runs. `smtp_login`, `cert`: practice shops only (answer 409 otherwise).
2. `curl -X PUT $URL/api/admin/businesses/<id>/demo-fault -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"fault":"a_record"}'` (or `smtp_login`, `cert`; `""` disarms).
3. Press "Check again" on the shop's report (or `POST /api/businesses/<id>/checks`). The fault is used up by that one run.
- `a_record`: the shop's A record is really removed (guarded write) → Doctor resolves, re-points, green ("Fixed by us").
- `smtp_login`: mail sign-in refused for that run only (pretend) → test order fails → "needs you" + the exact instruction. The next run is green.
- `cert`: the padlock fails until asked again (pretend) → Doctor fetches, retries the certificate, green.
The marker-missing half of fault 3 has no staged switch; the Doctor sees `shop_marker=MISSING` from `fetch` but no fixture covers it.

**Live Claude spend this session: $0.0042** by the app's price table (24 Haiku calls over 4 capture runs, about 1.2k tokens in / 80 out each; cap was $0.30). `.env` is back on `CLAUDE_MODE=fixture` (it was only overridden per command). Re-capture: `cd backend && CLAUDE_MODE=live ../.venv/Scripts/python ../scripts/capture_doctor_investigation.py [--dry-run]`.

### Whole-system invariant test (`tests/test_s11_invariants.py`)

A seeded random loop (not Hypothesis: no new dependency, so no automatic shrinking; a failure prints its seed and
faults, reproduce with `one_run(seed, make_settings)`). Default profile: 20 seeds, about 40 s. Long profile:
`pytest -m slow tests/test_s11_invariants.py` (seeds 20–259, about 6 min); `slow` is now deselected by default in
`pyproject.toml`. Tests with it: **646 passed, 2 skipped, 1 deselected**.

Each run: two approved users → shop → go-live checklist → real launch on the stand-in "real" world → resume if it
failed → checks + Doctor → monitor quick + daily (+ two rechecks) → a customer order + 4 random status changes →
reconciler. 12 fault kinds at 30% each. All 8 invariants are asserted, and the default test also asserts that every
fault kind was injected and that launches, resumes, proven checks, DNS writes, alert emails and orders all really
happened (the first version passed with zero alert emails ever sent; that guard caught it).

**Bugs found: none** in 260 seeds. What it does not prove (so don't read "none" as more than it is):
- "Two check runs at once" and "restart" are simulated in sequence (a stuck `running` row, then the reconciler); nothing here runs truly in parallel or kills a process mid-step.
- The owner's "Yes, I got it" tap is never made, so delivery is only ever "waiting" for a real shop; `imap_seen` isn't reached.
- "A GoDaddy write failing halfway" is the first `set_records` call raising; a launch has only that one write.
- The backup-before-write check compares timestamps of `DnsBackup` and the first `dns_write` audit row.
- Failures are cleared before resume, so "a failed plan can be resumed" means the resume call is accepted and ends done/failed, not that it survives a second fault.

## Proven in Docker on the laptop (S10)

Clean-clone image build (frontend + `/build` baked in, no pytest/ruff, no `.env`, uid 10001) · app + Caddy healthy,
only Caddy publishes ports · HTTPS + HSTS + http→https 308 · `__Host-lw_session` with Secure/HttpOnly/SameSite=Lax/Path=/
and no Domain, kept by the browser · sign-in by the emailed link (Mailpit) → pending → admin approves → describe → practice
launch → real launch (pretend GoDaddy) → a customer order on the shop host → report → share link logged out ·
two sellers isolated · guest workspace kept · `/internal` 404 from outside in 5 spellings, working inside the network ·
shop host 404 for `/api /internal /build /r /assets` · rate limit on the real client IP (forged XFF ignored; another
machine not limited) · `restart app` → reconciler ran, one set of jobs · SIGKILL mid-launch → "press Resume" ·
exactly one uvicorn, and a second process on the DB is refused · backup → change → restore → row counts match and
the later row is gone · Privacy/Terms linked · `check_m1.sh --local` all PASS.

## Still unproven until the VPS

Real Let's Encrypt certificates (on-demand for shops) · the first real GoDaddy write (one shop A record, guarded
client + DnsBackup) · `AuthoritativeResolver` on the network · `SafeWeb` outside-in test order over the internet ·
IMAP delivery proof (needs a shop owned by `hello@launchwitness.com`) · real `domain_expires` for the app domain
(feeds Renewals + the team alert) · zone hygiene against the real zone · monitoring emails through hello@ (send limit
unknown).

## New in S10.5b, in one line each

- Landing: `#how`, `#proof`, `#watch` (`#fix`), `#security`, `#check`, `#who-*`; numbers pinned by `test_s105b_landing_claims.py`.
- `frontend/src/ProductMenu.tsx` (top bar, both signed in and out). Anchors from app pages land via Landing's mount effect.
- `app/watch.py`, `routers/watch.py` (`/api/watches`, 3 AUTH routes), `WatchedAddress`, monitor job `watch_addresses`
  (registered with the team jobs, i.e. on the server, not in tests).
- The three.js hero was built and then removed at the owner's request (S10.5c); the S10.5 SVG hero is live. History: `820e824`.

## New in S10.5, in one line each

- `app/sites/demo.py`: demo shops from the saved Reader fixtures (contact fields forced empty); `/demo/` is 404 on shop hosts.
- `frontend/src/App.tsx` `parseRoute`: one URL per page; `#/new` needs sign-in (`NeedsSignIn`), `#/try` is guest practice.
- `frontend/src/Steps.tsx`: 5-step header + `resumeHash` (from `business.latest_plan`).
- `POST /api/businesses/{id}/orders/{order_id}/status` (owner, audited) · `Order.status`; `sites/orders.py` `STATUS_STEPS`,
  `customer_whatsapp_link`, `tel_link`; My shops `new_orders`.
- `seller.html` preview-only script + `ShopLink.tsx` message handler (only from its own frame, only "home"/"privacy").
- `app/golive.py` + `GET /golive`, `POST /confirm` (owner only; the team gets 404) · `Business.wa_confirmed`,
  `upi_confirmed`, `own_goods_at`, `terms_at`, `previewed_at` · Profile `instagram`, `delivery_areas`, `niche` (owner-only,
  not in the Reader schema) · WhatsApp stored as `+91XXXXXXXXXX` · report `confirmed_by_you`.
- Real launches need the checklist: tests call `tests/conftest.py::ready_for_real`, e2e `helpers.readyForReal`.
- On the VPS day: a real launch of the demo shop now needs the owner's WhatsApp + UPI checks and the two ticks first.

## New since S9F, in one line each

- `app/singleton.py`: one process per database (lock file next to it, `WEB_CONCURRENCY` guard).
- `app/db.py`: WAL, `busy_timeout=5000`, `foreign_keys=ON` on every connection.
- `app/backup.py` + `scripts/backup_db.sh` / `scripts/restore_db.sh` (`LOCAL=1` for the local stack).
- `app/selfcheck.py`: startup warnings; `/api/health` shows harmless ones publicly, all of them to the admin.
- `routers/launch.py`: real server + `CLAUDE_MODE=fixture` → the launch is held (`review=held`), the team clears it.
- `app/renewals.py`, `Monitor.team_renewals` (job `team_renewals`), report `renewals`, My shops `renewal`.
- `app/zone_hygiene.py`, `ZoneFinding`, job `zone_hygiene`, `/api/admin/zone-*` (4 routes), team page "Address records".
- `routers/proof.py::dangling_cname`; `RealDnsResolver.exists()` tells NXDOMAIN apart from "no A record".
- `SMTP_SECURITY` (`plain` only for one-word local hosts), `PRACTICE_STEP_SECONDS` (pretend world only).
- Fixed: the admin demo delete left Evidence/TestTicket/ReportShare rows behind (found by foreign keys).

## Open bugs / doubts

- **The pretend world forgets on restart.** On a practice server the fake GoDaddy zone is in memory; after a restart,
  practice "live" shops have no records, so monitoring and zone hygiene see them as missing. Harmless on the VPS (real
  zone), confusing in a local demo after a restart. Re-launch, or accept it.
- Stored product photos (3–6) are not built: no upload storage / re-encoding / EXIF stripping exists yet (S10.5 decision).
- Demo pages `/demo/*` answer 405 to HEAD (only the page catch-all accepts HEAD now). Point monitors at `/` or `/api/health`.
- E2E can't tap "Yes, I got it" on a practice server (the test email stays in the pretend inbox); pytest covers it, and
  on the VPS it's a manual step.
- Daily monitoring sends one test-order email per live shop per day through hello@: check GoDaddy's send limit.
- Carried over: `OUT_OF_SCOPE` regex can hold innocent shops (hold only); the Doctor has no fix for the test order /
  HTTPS marker; own-domain shops aren't covered by the shop-host guard (own-domain real launch is cut); the admin is
  whoever reads `ADMIN_EMAIL`'s inbox (no second factor).

## Remaining plan (in order)

1. **Wed Nov 18: the VPS**, `docs/NEXT_SESSION_VPS.md`.
2. S9F Phase 4: investigating Doctor (read-only tool loop before the fixed playbook; three staged faults).
3. Phase 5: design (one template, three palettes; the report page first).
4. Demo video + submission (SPEC §11–12), rebuild `/build`, final `bash scripts/secret_scan.sh`.

## Ritual reminders

Small commits, tests before each; merge with `git merge --no-ff` (no `gh` on this laptop) and push. Save the transcript:
`REDACT_EMAILS=<owner email> bash scripts/save-transcript.sh <N> <milestone> <path to the .jsonl>` (pass the path on Windows).
