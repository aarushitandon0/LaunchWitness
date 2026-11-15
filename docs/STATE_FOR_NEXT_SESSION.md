# State for the next session (written 2026-11-16 IST, end of S9F Phase 3)

Read `CLAUDE.md` first (rules + commands), then this. You should not need to read the whole codebase.

## What this is

LaunchWitness: a seller describes her home business, it becomes a shop at `<slug>.launchwitness.com`, and the app
**proves** the order path works (DNS → HTTPS → a real test order through the public form → mail server → inbox or
the owner's "Yes, I got it"), repairs what breaks, and keeps checking. GoDaddy hackathon, submit by **Nov 20**.

## What's merged on `main`

| Merge / commit | What |
|---|---|
| `d02a430` | S9F Phase 1 (Fable): claims made true (audit B1–B9, S2, S5–S8, app-zone write guard) |
| `77d8153` (merge) | Phase 1 + **Phase 2: accounts and multi-tenancy** (`c8bdbb3`, `0392cc6`, `50bb7a2`, `1a85b1b`) |
| merge of `s9f-p3-proof` | **Phase 3: order proof chain + check any address** (`edc46ba` backend, then frontend + docs) |

Tests on main: **477 passed, 2 skipped** (`cd backend && ../.venv/Scripts/python -m pytest -q`). Ruff (`backend/pyproject.toml`
pins E4/E7/E9/F/I), `npx tsc --noEmit` and `npm run build` clean. Backup of Fable's unfinished work: `git stash list` →
`fable-p2-wip-backup` (keep it; never drop it).

## Map of the important code

- Access: `app/safety/access.py` (one gate `require_business_access` / `require_plan_access`; 404 for others' shops),
  `app/safety/route_table.py` (**every route must be listed**; `tests/test_s9_phase2_access.py` enforces it and generates
  an owner-route matrix), `app/safety/request_guard.py` (shop hosts get no `/api`, `/internal`, `/assets`, `/build`, `/r`;
  Origin + CSRF on changes), `app/accounts.py` (email links, sessions, guest adoption), `app/tenancy.py` (unpublish/purge).
- Proof: `app/proof.py` (Evidence, TestTicket, "Yes, I got it", in-process shop web, summary), `app/checks/safe_fetch.py`
  (SSRF guard), `app/agents/checker.py` (checks write evidence), `app/routers/proof.py` (`/api/proof/confirm`,
  `/r/<token>`, share routes, `/api/check-address`), `app/sites/orders.py::accept_order_form` (ONE form handler for
  customers and the checker).
- Agents: Reader/Namer/Doctor/Policy use Claude (`app/agents/*`), Planner/Executor/Checker are code.
- Frontend: `src/api.ts` (cookies + `X-CSRF-Token`), `Account.tsx`, `Admin.tsx`, `Report.tsx` (hop trace, share, got-it),
  `Landing.tsx` (`#check`).

## Real vs faked vs manual

| Piece | State |
|---|---|
| Sign-in emails, order emails, alerts | Real SMTP via hello@launchwitness.com (sent once for real in S8.5); `DEV_MODE` shows links instead |
| GoDaddy DNS writes | Code real (`GoDaddyClient`, app-zone guard: shop A records only); **no real write yet — first on the VPS Wed Nov 18** |
| Authoritative DNS (`AuthoritativeResolver`) | Code real, unit-tested with stubs; **unproven on the network** |
| Outside-in test order over https (`SafeWeb`) | Code real, unit-tested with a mock transport; **unproven until a shop is live on the VPS** |
| IMAP inbox check | Code real (`ImapInboxReader`, SINCE + exact time); only proves delivery for mailboxes we hold |
| Practice (guests, pending users, `USE_FAKES=true`) | Pretend GoDaddy/DNS/inbox, in-process shop page + form; always labelled "Practice" |
| Purchases | Off (`ALLOW_PURCHASE=false`); own-domain real launch is cut |
| Policy check | Live Claude when `CLAUDE_MODE=live` (fails closed); in fixture mode it always says OK (see doubts) |

## Env vars added in S9F (all in `.env.example`; the owner fills `.env`, never read it)

`APP_ORIGIN`, `ADMIN_EMAIL`, `DEV_MODE` (local only, refuses https), `SESSION_DAYS`, `SIGNIN_LINKS_PER_EMAIL_PER_DAY`,
`SIGNIN_LINKS_PER_IP_PER_HOUR`, `MAX_SHOPS_PER_USER`, `USER_DESCRIBES_PER_DAY`, `MAX_LIVE_SHOPS` (40, certificate limit),
`SHOP_REPORTS_PER_VISITOR_PER_DAY`, `ADDRESS_CHECKS_PER_HOUR`, `ADDRESS_CHECKS_PER_DAY`, `MAILBOX_EXPIRES_ON` (hello@
lapses ~Dec 15). Shell-only for `npm run dev`: `LW_APP_ORIGIN` (default `http://localhost`). On the VPS set
`ADMIN_EMAIL`, a fresh 16+ char `ADMIN_TOKEN`, `MAILBOX_EXPIRES_ON`; `DEV_MODE` must stay false.

## Security fixes made in this session (to Fable's Phase 2)

1. Policy check failed **open** in live mode (fixture fallback answered "ok") → now asks live Claude directly, holds on failure.
2. Deleting a shop reset the per-user daily Claude cap → counted from `describe_used` rows that survive deletion.
3. Anyone signed in could burn another user's delete-account link → token checked against the signed-in email first.

## Open bugs / doubts

- **Fixture-mode policy check always passes.** If the VPS runs `CLAUDE_MODE=fixture`, real launches get no policy review
  (team approval of accounts is the only gate). Decide: live mode on the VPS, or hold every real launch in fixture mode.
- `visitor_id` trusts the LAST `X-Forwarded-For` entry (right behind Caddy). If the app port is ever exposed directly,
  limits can be dodged. Keep the app port private (compose: only Caddy publishes 80/443).
- Daily monitoring sends one test-order email per live shop per day through hello@ — check the send limit (PROGRESS TODO).
- `OUT_OF_SCOPE` regex in `agents/policy.py` can hold innocent shops ("wine-coloured cake"); it only holds for review.
- The Doctor has no fix for the test order or the HTTPS marker; those fail and explain only (Phase 4).
- Own-domain shops (practice `full` mode) aren't covered by the request guard's shop-host rule; real own-domain is cut.
- Report's "needs you" state lives in CheckResult `detail.waiting`; the shared page reads the same summary.

## Where I disagreed with Fable (left as designed, not security holes)

- The guest cookie also authorises CSRF for guests; fine, but a guest workspace can't be recovered on another device
  (by design: sign in to keep it).
- The admin is "whoever signs in as `ADMIN_EMAIL`": a compromise of that inbox is a compromise of the team page.
  Acceptable for a beta; consider a second factor later.

## Remaining plan (in order)

1. **Phase 4: investigating Doctor.** A read-only tool loop (Claude may call: read DNS answer, fetch shop page via
   `shop_web`, read evidence rows) before choosing from the fixed playbook; three staged faults for the demo
   (DMARC missing, MX missing, site not pointing). Keep "Claude decides, code acts"; tool calls are read-only and
   audited; `max_tokens` tight; fixtures first (live cap per session as the owner says).
2. **Phase 5: design.** One template, three palettes; the trace/report page first (hop trace is in `Report.tsx`).
   Reference frames stay out of the repo.
3. **Phase 6: verification and handover.** Playwright end-to-end suite (reuse the flows in `docs/S9F_PHASE2_CHECKPOINT.md`),
   security write-up, a seeded read-only demo seller for judges, and `docs/NEXT_SESSION_VPS.md` for **Wed Nov 18**:
   VPS up (`docs/RUNBOOK_M1.md`), first real shop A record, real HTTPS + marker, outside-in test order over the internet,
   authoritative DNS answer recorded, IMAP proof for a team shop, "Yes, I got it" from the real seller.
4. Then session 10: demo video + submission (SPEC §11–12), rebuild `/build`, final secret scan.

## Ritual reminders

Small commits, tests before each; merge with a merge commit (not squash); `gh` isn't installed on this laptop, so
merges have been done locally with `git merge --no-ff` and pushed. Save the transcript with
`REDACT_EMAILS=<owner email> bash scripts/save-transcript.sh <N> <milestone>`.
