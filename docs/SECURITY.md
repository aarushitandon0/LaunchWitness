# LaunchWitness security, on one page (S10, 2026-11-16 IST)

Each topic names the code, the test that proves it, and what's still open. "Docker" means it was also proven on the
production-like local stack (`deploy/README.md`, `scripts/check_m1.sh --local`, `e2e/`).

| Topic | How it's handled | Proof |
|---|---|---|
| **IDOR** (someone else's shop by URL) | One gate (`safety/access.py`: `require_business_access` / `require_plan_access`). The ownership filter is part of the query, so another owner's id answers **404**, the same as an id that doesn't exist. Every route is classified in `safety/route_table.py` (19 public, 3 auth, 21 owner, 17 admin, 1 internal; S10.5 added the 3 demo-shop routes and order status, go-live checklist, owner confirmations); a test fails on any unlisted route. | `test_s9_phase2_access.py::test_matrix_owner_routes`: all 21 owner routes × {owner 200, other seller 404, guest 404, logged-out 401/404, admin 200 + audited}. e2e `b-two-sellers` (Docker): seller B gets 404 on A's shop, preview, orders, export, names, plans, report and share, and on PUT / plans / checks / share / DELETE. |
| **CSRF** | `safety/request_guard.py`: every POST/PUT/PATCH/DELETE on `/api` needs an Origin (or Referer) equal to the app's origin. A request that carries a cookie also needs `X-CSRF-Token`, an HMAC of that cookie that only our pages can read (from `/api/auth/me`). `SameSite=Lax` cookies. | Phase 2 tests (wrong Origin, missing token, a token from another cookie). The e2e suite sends real browser fetches through Caddy. |
| **XSS in seller content** | Seller sites: Jinja2 with autoescape; profile values sit only in text and quoted attributes, never in a script. Phone, WhatsApp, UPI ID and the food licence number are validated (digits / `name@bank`), so markup is refused outright. The shared report escapes every value. The React app never uses `dangerouslySetInnerHTML`. | `test_s10_xss.py`: a hostile string in **every** free-text profile field, every product field, the customer's order fields and the refused-order form. Pages are parsed with an HTML parser: no injected element, no `on*` attribute, no `javascript:` URL, at most the template's own script. Plus the shared `/r/` page with a hostile shop name. |
| **Open redirect** | After sign-in, `next=` may only be a `#/…` page of this app (`accounts.safe_next`); full URLs, `//host` and the like fall back to the default. There are no server-side redirects to user-given URLs. | Phase 2: 8 kinds of bad `next=`. |
| **SSRF** | The checker reaches shops only through `shop_web`: in-process for practice, and `SafeWeb` otherwise (`checks/safe_fetch.py`). `SafeWeb` resolves the host once, refuses private / loopback / link-local / metadata addresses, pins the checked IP for the connection, and re-checks every redirect. "Check any address" uses the same guard, rejects IP literals and `.local`, looks up only the typed name and its `www` (no scanning), and is rate-limited. | Phase 3 SSRF tests (refused ranges, redirect re-check, loops, pinning). `test_s10_watchdog.py`: the dangling-CNAME finding asks only the two typed names. |
| **Uploads** | The price-list photo is read in memory, capped at 5 MB (`agents/reader.py`), restricted to JPG/PNG/WebP, sent to the Reader and **never stored**. Caddy caps request bodies at 8 MB. | `test_s10_production.py::test_photo_upload_type_and_size_are_limited` (an SVG and a 5 MB+ JPEG are refused). The Caddy limit is in `deploy/Caddyfile.prod`. |
| **Rate limits** | Sign-in links per address per day and per IP per hour; describes per visitor and per user (deleting a shop doesn't reset it); launches, orders, contact messages, shop reports and address checks. The visitor id is a hash of the **last** `X-Forwarded-For` entry, which Caddy sets and clients can't forge. Only Caddy publishes ports. | Docker: 11 address checks from the laptop, each with a forged `X-Forwarded-For`, get 200×10 then **429**; a second machine (a container) still gets 200. |
| **Cookie scope** | `__Host-lw_session` / `__Host-lw_guest`: Secure, HttpOnly, SameSite=Lax, Path=/, **no Domain**, so the browser never sends them to `<shop>.launchwitness.com`. Shop hosts also get 404 for `/api`, `/internal`, `/assets`, `/build` and `/r` (request guard). `DEV_MODE` (plain-http names) refuses to start on an https base URL. | Docker: `check_m1.sh --local` reads the real `Set-Cookie` over https; e2e `a-seller-journey` checks the browser's cookie jar and gets 404 on 5 app paths on a live shop host. |
| **Token storage** | Sign-in, delete-account, share and "Yes, I got it" tokens: 32 random bytes, **only SHA-256 stored**, single use where it matters, 15 minutes for sign-in links. Sessions: random id, SHA-256 stored, new id at each sign-in, revoked on log-out-everywhere and on suspension. No passwords anywhere. | Phase 2/3 tests (single use, expiry, hash-only). |
| **Internal endpoints** | `/internal/tls-ask` (Caddy's "may I issue a certificate?") is closed twice: Caddy answers 404 for `/internal` and `/internal/*` on every host, and the app answers only to private host names (`app:8000`, an IP, a one-word name). | Docker: 5 spellings (`/internal`, `/INTERNAL/…`, `%2f`, `//internal`) all get 404 from outside; it works inside the network; the ask is refused for an unknown shop. `test_s10_production.py`. |
| **Secrets** | Only in the server's `.env` (chmod 600), never in the image (`.dockerignore`), never on a command line (`check_m1.sh` passes values to grep through a file descriptor). The local Docker stack doesn't read `.env` at all. The startup self-check never prints a value; `/api/health` shows only harmless warnings publicly. | `scripts/secret_scan.sh` (below). `test_s10_production.py::test_selfcheck_never_contains_a_secret`. |

## Secret scan of the repo and the whole git history (run 2026-11-16)

`bash scripts/secret_scan.sh`, result: **clean.**
- **The 7 real secret values in the owner's `.env`** (keys, secrets, passwords, tokens of 8+ characters) were searched
  for literally in every tracked file and in `git log -p --all`: **found nowhere.**
- **Key-shaped patterns** (Anthropic, private keys, GitHub, AWS): no hit in tracked files or history.
- **For review only, all checked by hand:** `password=` hits in tests (`from-env-only`, `pw-for-test-only`), in docs
  ("no password needed", `adduser --disabled-password`) and in the scrubber's own patterns, plus 15 webmail-shaped
  addresses in the history from test fixtures. The owner's personal address isn't in any commit, author line or file.
- During the scan one tool call briefly put a placeholder value on a local command line (`git log -S`). It turned out to
  be the default `change-me`; the script has passed values through files ever since.

## The owner's private preview (changed in S10.5)

A draft or practice shop is shown to its owner in an `<iframe srcdoc>` with `sandbox="allow-scripts allow-popups
allow-popups-to-escape-sandbox"`. There is still **no `allow-same-origin`**, so the shop page runs with an opaque
origin: it can't read the app's DOM, cookies (the session cookie is HttpOnly anyway), storage or API with the owner's
rights, and seller text stays HTML-escaped by Jinja as before. There is no `allow-forms` (the order form can't post)
and no `allow-top-navigation` (the shop can't move the app). What changed: a `srcdoc` page resolves links against the
app's URL, so `#menu` loaded the app into the frame (blank page). The preview-only script in `seller.html` now scrolls
in-page anchors itself, opens outside links (WhatsApp, Instagram, `tel:`, UPI) in a new tab with
`noopener noreferrer` (that's why `allow-popups` and `allow-popups-to-escape-sandbox` were added: the new tab is an
ordinary page with no link back), and asks the app for the shop's own pages with `postMessage({lwPreview: "home" |
"privacy"})`. The app accepts that message only when `event.source` is its own preview frame and the value is one of
those two words, then fetches `/api/businesses/<id>/preview?page=…` itself through the owner gate. Tests:
`test_s105_preview.py`, e2e `f-preview-links`.

## Still open (honest list)

- **The admin is whoever reads `ADMIN_EMAIL`'s inbox.** No second factor in the beta.
- **Fixture-mode policy check:** a real server with `CLAUDE_MODE=fixture` now holds **every** real launch for the team
  (fail closed). Live mode on the VPS is the intended setting.
- **Own-domain shops** aren't covered by the shop-host rule of the request guard (own-domain real launch is cut).
- **Not proven until the VPS:** real Let's Encrypt certificates, the authoritative DNS answer, the outside-in test order
  over the internet, IMAP delivery proof, and the real GoDaddy write guard (unit-tested against a mock transport).
- `HEAD /` answers 405 (harmless; point monitors at `GET /api/health`).
