# S9F Phase 2 checkpoint: accounts and multi-tenancy

As of 2026-11-16 (IST). Design by Fable (session 9F); finished, tested and wired to the frontend in the Opus continuation.

## What changed for a seller

- **Try it without signing in.** "Describe" makes a *guest practice* shop owned by an anonymous cookie. It is practice only (pretend GoDaddy), never public, and deleted after 24 hours. A banner says "Practice. Sign in to keep this shop."
- **Sign in by email link** (no passwords). Signing in keeps the guest shops (up to the 3-shop limit).
- **New accounts are pending** until the team approves them: they can practise, but not launch for real ("You can practise now; we'll email you when you can launch for real").
- **Approved owners** get a "Launch for real" button (a subdomain of launchwitness.com, $0). The server checks again at approval: the account is approved, the shop isn't a guest shop or paused, the live-shop cap, and the go-live policy check.
- **Orders, test orders and alerts go to the owner's verified sign-in address.** The personal-email field is gone.
- **Account page:** log out, log out on every device, and delete the account (emailed link *and* signed in).
- **Team page:** approval queue (approve / reject with reason), visitor reports (pause, close), every shop (pause / unpause / clear a policy hold), every account (suspend).

## Route classification (`backend/app/safety/route_table.py`)

45 routes: 15 owner, 13 public, 13 admin, 3 auth, 1 internal. A test walks the real app and fails on any unlisted or stale route, and checks that each class uses its gate (owner → `require_business_access`/`require_plan_access`, admin → `require_admin`, auth → `require_user`).

| Method | Path | Class |
|---|---|---|
| GET | `/{path:path}` (landing, built app, `/build`; shop pages on a shop host) | public |
| MOUNT | `/assets` | public |
| GET | `/api/health`, `/api/samples`, `/api/auth/me` | public |
| POST | `/api/contact`, `/order`, `/report-shop` | public |
| POST | `/api/auth/request-link`, `/api/auth/confirm`, `/api/auth/logout` | public |
| POST, GET | `/api/businesses` (create / list: only ever the caller's own) | public |
| POST | `/api/auth/logout-all`, `/api/account/delete-request`, `/api/account/delete` | auth |
| GET, PUT, DELETE | `/api/businesses/{id}` | owner |
| GET | `/api/businesses/{id}/preview`, `/orders`, `/export`, `/names`, `/plans`, `/report` | owner |
| POST | `/api/businesses/{id}/plans`, `/api/businesses/{id}/checks` | owner |
| GET | `/api/plans/{id}` | owner |
| POST | `/api/plans/{id}/approve`, `/resume`, `/practice-buy` | owner |
| GET | `/api/admin/check`, `/users`, `/businesses`, `/reports` | admin |
| POST | `/api/admin/users/{id}/approve`, `/reject`, `/suspend` | admin |
| POST | `/api/admin/businesses/{id}/pause`, `/unpause`, `/clear-review` | admin |
| PUT | `/api/admin/businesses/{id}/demo-fault` | admin |
| DELETE | `/api/admin/practice-businesses/{id}` | admin |
| POST | `/api/admin/reports/{id}/close` | admin |
| GET | `/internal/tls-ask` (Caddy only; 404 from outside) | internal |

`/docs`, `/redoc` and `/openapi.json` are switched off.

## Authorization matrix (`backend/tests/test_s9_phase2_access.py`, 52 tests)

Generated from `ROUTES` for all 15 owner routes:

| Actor | Result | Cases |
|---|---|---|
| User A on A's shop | 200 on every GET | 10 |
| User B on A's shop | 404 "We couldn't find that shop." | 15 / 15 |
| Anonymous (no cookie) | 401 | 15 / 15 |
| Guest with its own workspace | 404 | 15 / 15 |
| Suspended | session ends at once; 401; no sign-in link is made | 1 flow |
| Pending | `real: true` → 403; practice launch works | 1 flow |
| Admin signed in | 200 on every GET, each written as `admin_access` in the audit log | 10 |
| Admin token (command line, no cookie) | 200 on every GET; same URLs without it → 401 | 10 |

Plus sign-in (same answer for known/unknown/suspended; SHA-256 only; single use; 15 minutes; only the POST uses the token; `next=` refuses 8 kinds of bad value; per-email and per-IP limits; SMTP down → 503 with a plain message), sessions, CSRF/Origin, shop hosts, and the multi-seller rules (adoption up to the limit, 24 h purge, 3 shops, daily describe cap, slugs, reports, pause, live-shop cap, policy hold, account deletion, admin audit).

**Routes that needed a fix:** none in the gate wiring. Three bugs were found and fixed behind the routes:

1. **Policy check failed open in live mode (security).** `FallbackClaudeClient` answers from saved fixtures when Claude is down or the daily cap is reached, so the go-live check returned the saved `policy_ok` and a shop went live with no review. The policy check now asks live Claude directly and holds the shop if it can't (`agents/policy.py`), with a test for each case.
2. **Deleting a shop reset the per-user daily Claude cap.** The cap counted `read_business` audit rows, and deleting a shop purges its audit rows. Each describe now also writes a `describe_used` row that isn't tied to a shop, and the cap counts those.
3. **Someone else could burn your delete-account link.** The token was used up before checking it belonged to the signed-in user. `consume_token(..., email=)` now refuses another address's token without using it.

## Why the cookie is host-only

The session cookie is `__Host-lw_session` (guest: `__Host-lw_guest`): `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and **no `Domain` attribute**. The `__Host-` prefix makes the browser refuse the cookie unless it has exactly these properties. Without a `Domain`, the browser sends it only to `launchwitness.com` itself, **never to `<shop>.launchwitness.com`**. Seller pages live on those subdomains, so a page on a shop host can never see or ride on an owner's session. As a second wall, the request guard answers 404 for `/api/*`, `/internal/*`, `/assets/*`, `/build` and `/r/*` on any shop host. In local development (`DEV_MODE=true`, refused on https) the names are `lw_session` / `lw_guest` without `Secure`.

## Screenshots (`docs/screenshots/s9f/`, 375 px phone and 1440 px laptop)

| File prefix | What it shows |
|---|---|
| `01-a-1-sign-in` | Sign in by email |
| `01-a-2-check-email` | "Check your email" (DEV_MODE shows the link) |
| `01-a-3-confirm` | The confirm page: a button, so opening the link uses nothing up |
| `01-a-4-pending-no-shops` | Pending account: "You can practise now…" |
| `01-a-5-shop-under-account` | A's shop, made while signed in; orders go to the sign-in address |
| `01-a-6-my-shops-pending` | My shops (pending) |
| `02-team-1-queue` | Team page: A waiting for approval |
| `02-team-2-approved` | After Approve |
| `03-a-1-account-approved` | A's account: Approved |
| `03-a-2-launch-for-real` | "Launch for real" (approved only) above the practice options |
| `04-b-1-my-shops-empty` | User B's shops: none of A's |
| `04-b-2-cannot-open-a-shop` | B opens A's shop URL: "We couldn't find that shop." |
| `05-guest-practice-banner` | Guest: "Practice. Sign in to keep this shop." |

No sideways scrolling at 375 px on any of them.
