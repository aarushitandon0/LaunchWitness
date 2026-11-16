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
