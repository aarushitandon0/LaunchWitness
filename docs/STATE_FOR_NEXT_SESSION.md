# State for the next session (written 2026-11-16 IST, end of Session 10.5)

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
- `frontend/src/hero/scene.ts` (three@0.169.0, lazy chunk), `HeroScene.tsx`, `still.webp` (re-render: open `/?hero-still`
  and save `window.__lwHeroStill`, see `e2e/screens/s105b.spec.ts` notes). Real GPU only.

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
