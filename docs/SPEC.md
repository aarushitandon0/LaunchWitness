# LaunchWitness — Final Build Spec

As of 2026-11-14 · GoDaddy Inclusive Innovation Hackathon 2026 (HackerEarth) · Round 2 build Nov 13–20 · submit by Nov 20 · Top 10 announced Nov 30 · onsite finale Pune, Dec 11.

LaunchWitness is a working name.

---

## 1. Pitch

**One line for judges:** "Describe your business. LaunchWitness launches it on GoDaddy and proves everything works before your first customer arrives."

LaunchWitness takes a small seller from a few lines of description to a live business on her own domain: website, business email, and an order form that reaches her inbox. Then it checks every part for real, fixes or undoes anything that fails during launch, and keeps checking lightly afterwards.

**What makes it different.** Most AI builders stop at "your site is ready." LaunchWitness shows the proof: a real test order arriving in her inbox, every check green, and a report with the time each one passed. The safety rules (approve before spending, preview before changing, undo on failure) are what let an AI be trusted to spend money and change settings for a non-technical owner.

**Why it fits GoDaddy.** Small businesses buying a domain, a website and an email is GoDaddy's core business. LaunchWitness uses GoDaddy's Domains, DNS and Email as the engine, not decoration. GoDaddy's own AI tools already help people get online; LaunchWitness adds the missing piece: proof that it all works, before customers find out it doesn't.

---

## 2. Problem and the story

Small sellers either never get their own online presence, or they get one that is quietly broken.

1. **They don't start, because setup is technical.** A GoDaddy survey found 63% of India's small businesses had no website; of those planning one, only 15% owned a domain, and 30% wanted someone to build and manage it for them (DNA India). The survey is several years old: present it as background, not today's figure.
2. **When they do start, it's often half-working.** A March 2026 analysis put DMARC adoption at 44.9% for small businesses vs 75.3% for large enterprises (Cross-Sector DNS & Email Security). A scan of 200 small and mid-size business domains found 36% missing SPF and over two-thirds with no DMARC record (DEV). Result: order emails land in spam, and the owner never knows — she just thinks business is slow.
3. **AI could do the setup, but isn't trusted to.** Buying a domain and changing settings means spending money and risking email. An owner who can't read a DNS record can't check an agent's work.

Open question: find one current (2025–26) India-specific figure on small businesses without websites before the deck.

**Demo persona: Meera.** Meera sells custom cakes from home and takes orders over Instagram DMs. No website, no business email, never touched DNS. She types two lines and pastes her price list. A few minutes later she has meerabakes.in with her real menu and prices, hello@meerabakes.in, and an order form that lands in that inbox. Before she shares the link with a single customer, LaunchWitness places a test order, watches it arrive, and shows her: **"Your business is ready for customers."**

---

## 3. How it works (user flow)

Seven steps from description to proof; Meera does four of them, and only one costs money.

1. **Describe.** A few lines + price list (typed, pasted or photo). No WhatsApp/Instagram API.
   - Claude (one call) returns the business profile (name, products, prices, hours, area, tone) **plus** the site copy (tagline, about, item descriptions) **plus** how customers order: selling point, days of notice, pickup / delivery and delivery charge, whether customers may add a message for an item, the name the seller's UPI app shows, and her food licence (FSSAI) number if given. Plain code then tidies the reply (delivery is never a menu item; extras such as toppers are marked as extras; ordering rules leave the hours line).
   - **Scope guard (v1 = sellers who take orders).** If the business needs bookings rather than orders (salon, tuition, clinic, classes), the Reader says so in one plain sentence and no shop is built.
2. **Review.** She sees the profile as a form and fixes anything wrong. No AI.
3. **Pick a name.** Claude (one small call) suggests ~10 domain names; code checks real availability + price; shows the best 3.
4. **Preview and approve.** Code fills the ONE fixed template, the same for every seller (no per-business code or CSS; category colours come from a fixed palette by position): header with short badges taken only from her data, menu with prices and an Add button per item (a basket that also works without JavaScript; long menus get two columns and a search box), extras listed apart, about, hours, pickup/delivery, "Order on WhatsApp" link (`wa.me`), UPI QR with "Your UPI app should show: <name>", optional FSSAI number in the footer, privacy page. No "Verified" label anywhere. One approval card lists the domain, total cost and every setting to be made. **Nothing is bought or changed until she taps Approve.**
5. **Launch.** Code only: back up DNS, buy the domain (or use a free sandbox subdomain), point it at the server, set up email, put the site live with HTTPS. Each step streams on screen.
6. **Launch check.** Code checks the site opens, HTTPS is valid, email settings are correct, then places a real test order through her form. If anything fails, the Doctor explains it in one sentence, applies a safe fix or undoes the change, and re-checks until green.
7. **Report and watch.** Report headed **"Your business is ready for customers"**: every check, result, time passed. After launch, the same checks re-run lightly on a timer and alert her if something breaks.

**Two launch modes, same code (updated session 9F):**
- **Practice launch** (everyone, the default; guests too): every step against a pretend GoDaddy. Nothing goes on the internet; always labelled "Practice".
- **Real launch** at `<slug>.launchwitness.com`, for **approved accounts only**: $0, one A record per shop written through the GoDaddy API (no wildcard), real checks. **Own-domain launch is cut** for this round (practice only); the product says so. Unproven on real infrastructure until the VPS (Wed Nov 18).

---

## 4. Features

Eight core features first; no stretch item starts until all eight run end to end.

| # | Feature | Tier | What it does |
|---|---|---|---|
| 1 | Business reader | Core | Description + price list (text or photo) → editable profile + site copy, one Claude call |
| 2 | Name finder | Core | Claude suggests names; code checks real availability and price; shows 3 |
| 3 | Site builder | Core | One fixed template for every seller: badges from data, menu + basket, extras, about, hours, pickup/delivery, order form, WhatsApp link, UPI QR, privacy page |
| 3a | Orders and payment (session 9) | Core | Order date (min notice enforced), pickup/delivery, quantities, totals worked out on the server; per-order UPI pay link + QR (no gateway, no money passes through us); order ID + status page (Received → Confirmed → Paid → Preparing → Ready / Out for delivery → Delivered / Picked up, or Cancelled); seller's order list on her private link; WhatsApp hand-offs via `wa.me` links |
| 3b | Trust and safety (session 9) | Core | Email-link sign-in (the owner's address is proven) + team approval before any real launch; Claude policy check that can only hold a shop for team review (never launches; fails closed); "Report this shop" link + admin pause switch |
| 3c | Accounts and tenancy (session 9F) | Core | Guest practice → sign in to keep it; sessions; My shops (max 3); each owner sees only their own shops; team page; account deletion. See §9a |
| 4 | Launch engine | Core | Plan → preview of changes → approval card → execute (GoDaddy Domains, DNS, Email); sandbox + full modes |
| 5 | Launch check | Core | Site resolves, HTTPS valid, email settings present, real test order arrives |
| 6 | Repair during launch | Core | Doctor explains a failed check, applies a playbook fix or undoes from backup, re-checks |
| 7 | Launch report | Core | One page per business: every check, result, timestamp, plus audit log |
| 8 | Light monitoring | Core (light) | Timer re-checks, domain/cert expiry warnings, alert to personal email, "Run checks now" |
| 9 | Full monitoring | Stretch | Daily test order, change detection ("Was this you?"), incident history |
| 10 | /verify page | Stretch | Official Instagram/WhatsApp listed, backed by a DNS TXT record, so buyers spot fakes |
| 11 | MCP server | Stretch | Engine tools over MCP behind the same safety gates |
| 12 | Fleet view | Stretch | Dashboard of all launched businesses |

Out of scope: payment gateways or holding money (UPI pay links only; "Connect Razorpay (after seller KYC)" is future work), appointments/booking, inventory, SMS, WhatsApp Business / Instagram APIs, multiple templates, custom code generation.

---

## 5. Agents

Claude decides and explains; plain code acts and checks. Three steps use Claude; nothing that spends money or changes settings is left to the model alone.

| Agent | Job | Claude or code | Model | Output |
|---|---|---|---|---|
| Reader | Profile + site copy + ordering details from text or photo; orders vs bookings | Claude, 1 call | Strong (vision + structured output) | Profile JSON + copy (code tidies it) |
| Policy check (session 9) | Is this shop OK to put live? | Claude decides, code holds | Cheap | OK, or "hold for review" + one plain reason; it can never launch or unpause |
| Namer | Suggest names; check availability + price | Claude suggests, code checks | Cheap | 3 available domains with prices |
| Planner | Every action, setting and cost | Code, fixed schema | — | Plan + before/after preview |
| Executor | Run the approved plan step by step, backup first | Code only | — | Step log |
| Checker | Live checks | Code only | — | Pass/fail per check |
| Doctor | Explain a failed check in one sentence; pick a fix | Claude chooses, code applies | Cheap | Fix + re-check result |

A manager loop runs them in order and stops at the approval card. **Doctor playbook (fixed, in code):** undo from backup · re-add MX · re-add SPF/DKIM/DMARC · retry certificate · re-point site address. It cannot write arbitrary settings.

**The Doctor investigates before it chooses (S11).** For a failed address, padlock or test-order check, the Doctor (cheap model) may first *look* through read-only tools: `resolve` (the shop's own address), `fetch` (the shop's own page, SSRF-safe), `evidence` (the stored proof of this run), `smtp_test` (connect and sign in, never send) and `mailbox_status`. At most 4 looks and 1,500 output tokens. It then answers `{finding, fix_id | "needs_owner", owner_instruction}`. Code checks the answer and is the only thing that acts: a fix must be in the playbook and allowed for that check and launch mode; re-adding settings we wrote (or asking again for a certificate) is automatic; restoring a backup needs the owner; money never. If Claude is unavailable or over budget, plain rules decide: exactly one allowed fix → apply it, labelled "standard fix"; otherwise "needs you" with a plain instruction. Every look is audit-logged and kept as a trace on the check result, shown in the report. The owner's own words (`symptom`), tool results and check details are data, never instructions. The other email-setting checks keep the one-shot Doctor.

Cost shape: ~3 Claude calls per launch + 1 per failed check.

---

## 6. Launch checks and repair

Repair happens during launch, because that's where setups actually go wrong: settings not spread yet, a certificate failing first time, a mailbox not ready, an email setting missing, a step failing halfway.

| Check | How | If it fails |
|---|---|---|
| Domain points to the site | DNS lookup against GoDaddy's authoritative nameservers (not a cached resolver) | Re-point, wait, re-check |
| Site opens over HTTPS | Fetch, validate certificate | Retry certificate, re-check |
| Email settings correct | Look up MX, SPF, DKIM, DMARC | Re-add the missing record from the plan |
| Test order arrives | Submit the real form; email carries a "Yes, I got it" link | Check mailbox readiness + MX, retry |
| Launch finished cleanly | Step log shows every step done | Resume the failed step, or undo DNS from backup |

**Repair rules:** max 3 attempts per check, then stop and explain in plain words. Repair never spends money. Every attempt goes to the audit log.

**Confirming the test order:** for real sellers the app can't read their inbox (GoDaddy emails mailbox passwords to the account owner only), so the seller taps "Yes, I got it". For the demo mailbox, the checker can also read the inbox over IMAP (password in env).

**The proof chain (session 9F Phase 3).** Every claim on the report is backed by a stored `Evidence` row, and each hop is recorded separately with its time and the server that answered:
- *Address answered*: asked of the zone's own nameservers (found from NS), which server is recorded.
- *Page opened*: HTTPS with a valid certificate **and** the shop's `<meta name="lw-shop">` marker, so a parked page with a valid certificate fails. Waits up to 2 minutes while a new certificate is issued.
- *Test order*: the checker opens the public shop page, finds the order form and posts it like a customer (same fields and form token) with a one-time code (`TestTicket`). Then: *Form accepted* → *Mail server accepted* (message id) → *In the inbox* (IMAP, only for mailboxes we hold) **or** *Owner confirmed* (a single-use "Yes, I got it" link in the test email). **"Accepted" is never shown as "delivered"**: until one of the last two exists the report says "N of M proven, 1 needs you" and the headline is "Almost ready". Test orders are hidden from the seller's list.
- The checker may only fetch the shop's own host (SSRF guard: https only, hostnames only, public IPs only, IP pinned, every redirect re-checked). Practice shops are never on the internet, so practice runs the same page template and form handler in-process, and every row is labelled practice.
- **Share:** `/r/<token>` is a read-only, revocable report with no customer data.
- **Check any address** (landing page): read-only public checks of any domain (address, HTTPS, certificate days, MX/SPF/DMARC) in plain English. SSRF-guarded, rate-limited, sends no email and stores nothing about the address. A free extra entry point, not the product.

**Demo failure:** during launch one check fails on purpose (e.g. DMARC missing → orders would land in spam). The Doctor explains, re-adds, re-checks to green. The fault is staged — say so if asked.

---

## 7. Monitoring after launch

Light monitoring is core; full only if time permits. It re-runs launch checks on a timer (GoDaddy's API has no webhooks).

**Light (build now)**

| How often | What |
|---|---|
| Every 15 minutes | Site opens, HTTPS valid |
| Daily | DNS + email settings still match launch; days left on certificate and domain |

- On failure: re-check once a minute later (rule out blips), then Doctor explains + safe playbook fix.
- Anything needing money or her action (renewal, payment): alert only, at 30 / 7 / 1 days before expiry.
- Alerts go to her **personal email**, not the business inbox.
- "Run checks now" button = same checks on demand (this is how the demo shows it).

**Full (if time permits):** daily real test order; change detection ("Was this you? Tap to restore") instead of silent undo; incident history on the report.

**Rules every check and alert follows (S11b; the full table of cases is `docs/CHECKS_MATRIX.md`)**

- Each finding says how sure we are: seen / not seen / couldn't check. "Not sure" is allowed; a wrong answer is not.
- A lookup that fails on our side is "couldn't check": never passed, never the seller's fault, no fix, no alert.
- The email service is detected from the domain's own mail servers. Advice only ever uses that service's values; an unrecognised service gets no values. A signing key is "found" or "couldn't check", never "missing".
- Outside addresses (Check any address, Watch) are explained only. Fixes exist only for our own shops, and never touch another email service's working settings.
- Each shop has a time budget per round; what didn't finish is recorded as "couldn't finish".
- A check fixed 3 times in a day that breaks again is no longer fixed automatically: one "keeps breaking" email, then it needs the owner.
- An alert that couldn't be sent is recorded, retried on the next round, and shown to the team.

**Honest framing:** in the demo everything sits in the app's GoDaddy account, so little can break after launch. Monitoring matters most once it runs on her own account. Pitch it as insurance, not the hero.

---

## 8. Architecture and GoDaddy usage

One GoDaddy Docker VPS (4 vCPU / 8 GB, provided at $0) runs everything; GoDaddy and Claude are called as APIs.

- **Caddy:** HTTPS for the app and every seller site; on-demand TLS with an `ask` endpoint that only approves domains in the DB.
- **FastAPI:** agents, API, monitoring scheduler, and every seller site (served by `Host` header from one template + profile).
- **React (Vite):** seller-facing app, built and served as static files.
- **SQLite:** profiles, plans, DNS backups, check results, audit log. Every connection sets WAL, `busy_timeout=5000` and
  `foreign_keys=ON` (S10). **Exactly one app process** (APScheduler runs in it; SQLite has one writer): the app refuses to
  start a second one on the same database. Online backups (`scripts/backup_db.sh`, 7 daily + 4 weekly) with a tested
  restore (`scripts/restore_db.sh`).
  **When we'd move to Postgres:** more than one app server, a second worker process, or heavy concurrent writes
  (hundreds of orders a minute). Not before: one VPS at this scale is what SQLite is good at. The move is small,
  because every table is a SQLModel model and queries go through SQLAlchemy: change `DATABASE_URL`, swap
  `add_missing_columns` for a real migration tool (Alembic), and move the scheduler into its own single process.
- **Outside:** Claude API; GoDaddy Domains/DNS/Email (OTE sandbox in dev, `GODADDY_ENV=ote|prod`); SMTP through the app's one mailbox.
- **Secrets** live only in environment variables.
- **Sandbox subdomains** get one A record each (`<slug>.<APP_DOMAIN>` → VPS), written by the app at launch; no wildcard (decided S9F). Only `@` (and optionally `www`) is made by hand.

| Step | GoDaddy piece | Calls |
|---|---|---|
| Name | Domains API (or `gddy`) | availability, suggestions, price quote |
| Buy | godaddy.com checkout with credit (demo); Domains API purchase only behind guards | purchase after approval |
| Point | DNS API | list records (backup), set A, MX, SPF/DKIM/DMARC |
| Mailbox | Titan email via `gddy` / Email API | create mailbox, poll until ready |
| Host | Docker VPS | A record → VPS; Caddy issues HTTPS |
| Undo | DNS API | write backup back |

**Access limits:** production Availability API needs 50+ domains or ~$20/month spend; DNS API needs ≥1 domain. So: buy the app domain first; check availability via `gddy`, OTE, or free RDAP if production stays blocked.

Say plainly to judges: hosting is the Docker VPS, not GoDaddy's Hosting API.

---

## 9. Safety rules

1. **Approve before spending.** Purchase/mailbox only after Approve on a card showing exact cost.
2. **Preview before changing.** Every DNS change shown as a before/after diff first.
3. **Back up, then undo.** Before any DNS write, save current records as JSON. Failed launch check can write the backup back. Failed mailbox step is retried, not undone.
4. **Scoped actions.** Each launch touches only its own domain. Doctor picks from a fixed playbook; anything else is refused and logged.
5. **Spend guards in code.** `ALLOW_PURCHASE=false` default, hard `MAX_SPEND_USD` cap, purchase only when flag on AND owner approved.

Every step goes to the audit log shown in the report.

**Tamper-evident proof log (S11d).** Every evidence row is a link in a per-shop hash chain:
`hash = sha256(prev_hash + canonical JSON of the row)`, the first row chaining from a fixed per-shop start value. Evidence
is append-only in code (no updates, no deletes; only deleting a shop or account removes its whole chain, with one anonymous
audit event). The shared report shows "Receipt <first 12 hex of the newest hash> · verify"; the public
`GET /r/<token>/verify` recomputes the chain and answers only `{"intact": true, "rows": N, "head": "..."}` or
`{"intact": false, "altered_at": N}`, never any evidence or customer data. It catches an edited, reordered, removed or
inserted row. Honest limit: someone who can rewrite the whole database can rebuild a chain or cut rows off its end; only a
receipt that somebody saved earlier would not match.

---

## 9a. Accounts and tenancy (session 9F)

- **Guest practice.** "Try it" needs no account: an anonymous cookie owns a practice workspace (pretend GoDaddy, never public, deleted after 24 hours).
- **Sign in by emailed link.** No passwords. The link carries 32 random bytes, only its SHA-256 is stored, it works once for 15 minutes, and only the "Sign in" button (a POST) uses it, so mail scanners opening the link change nothing. Same answer whether or not the address has an account. Limits per address and per IP. Signing in keeps the guest's shops (up to the limit). There is no other "claim" mechanism.
- **Sessions.** `__Host-lw_session`: Secure, HttpOnly, SameSite=Lax, Path=/, no Domain (host-only), so shop subdomains never receive it. New id at every sign-in; 14-day sliding expiry; log out; log out everywhere; suspension ends every session at once. CSRF: Origin check + a token derived from the cookie on every change.
- **Tenancy.** Every business route goes through one gate; the ownership filter is part of the database query; another owner's shop answers 404. Shoppers never sign in.
- **Team approval during the beta.** New accounts are *pending* (practice only) until the team approves them. The admin is the `ADMIN_EMAIL` user; `ADMIN_TOKEN` stays for the command line only.
- **Limits.** 3 shops per account; a daily cap on describes (Claude calls) that deleting shops doesn't reset; **at most `MAX_LIVE_SHOPS` (40) live shops**, because Let's Encrypt issues about 50 new certificates per registered domain per week and every shop subdomain needs its own.
- **Orders and alerts** go to the owners' verified sign-in addresses (the app mailbox only for shops the team runs, or ownerless guest shops).
- **Go-live gate.** At real approval: approved account, not a guest shop, not paused, under the live-shop cap, policy check OK (or cleared by the team). On a real server running saved Claude answers (`CLAUDE_MODE=fixture`) the policy check can't really check, so **every real launch is held for the team** (fail closed, S10).
- **Deleting an account** needs the emailed link *and* being signed in; it unpublishes and deletes the shops, erases the email and keeps one anonymous audit row.
- Route classes live in `backend/app/safety/route_table.py`; a test fails on any unclassified route.

---

## 9c. Owner experience (S10.5)

- **Sign in first.** Describe (`#/new`) asks you to sign in, with the reason ("Your shop and its orders belong to your
  account"), and the emailed link brings you back to Describe. A quiet secondary link keeps **guest practice**
  ("Try it without an account": `#/try`, practice only, deleted after 24 hours). Judges never hit a wall.
- **Demo shops.** `/demo/meera`, `/demo/imran`, `/demo/sunita`: the three sample profiles rendered by the app, logged out,
  no database row, labelled "Demo shop: orders here are not real"; the form places no order. Never served on a shop host.
  The landing page is about home-based, made-to-order sellers in general (home food, handmade goods, custom work); Meera
  appears only as a demo.
- **Routing.** Every page has its own URL (Back/Forward, refresh, deep links). Top bar: signed out Home · See a demo shop ·
  Sign in; signed in My shops · New shop · Account · Team (admins). A clickable 5-step header (Describe → Review → Name →
  Approve → Launch & report), resume at the right step from My shops, a real "Page not found", and a plain message with
  "Back to My shops" when a shop answers 404. Client guards are convenience only; the server decides.
- **Orders inbox.** Each shop has an Orders page (`#/b/<id>/orders`, mobile-first, newest first, test orders hidden): ref,
  time, items, total, name, note, the full phone (owner only; masked/absent in audit logs), a "Message on WhatsApp" `wa.me`
  link to the **customer** with a ready-typed message (nothing is sent by us), and a status the owner sets: New → Confirmed →
  Paid → Done, or Cancelled (Paid may be skipped; Done/Cancelled are final; audited). No customer-facing status page. My shops
  shows the count of new orders. The order email carries the ref, items, total, a `tel:` link, a WhatsApp link and a link to
  the Orders page.
- **Go-live checklist.** Only "Launch for real" is gated (at plan time and again at approval); drafts and practice never are.
  Required: verified sign-in email · shop name + address + one priced item · WhatsApp (Indian mobile, stored as +91XXXXXXXXXX;
  the owner taps "Test this number" then "Yes, that's me") · UPI ID + the name her UPI app shows (the **₹1 UPI name test**:
  she scans her shop's real UPI QR for ₹1 with her own phone and confirms the name; paying is optional) · pickup (area only,
  never the home address: she sends the exact address on WhatsApp after confirming) and/or delivery (areas + fee, ₹0 allowed)
  · working days/hours (+ notice days) · two ticks (own goods; Terms) with the time · the preview opened once. Owner checks are
  stored with the exact value confirmed and labelled **"confirmed by you"**, never "verified"; a changed number or UPI
  ID/name resets them. Only the owner can confirm (the team and others get 404). Optional: Instagram handle, niche (food /
  handmade / custom: picks the colours), FSSAI number (shown, not checked). Never collected: Aadhaar, PAN, bank account or
  card numbers, passwords, full home address, date of birth. The Report lists the owner's checks (WhatsApp, UPI name test,
  "Yes, I got it") under "Checked by you", apart from machine-proven hops.
- **Landing (S10.5b).** Only claims what the code does (`test_s105b_landing_claims.py` pins the numbers to
  `monitor/scheduler.py` and `renewals.py`). Sections: How it works · How the proof works (the six hops) · We keep watching
  after launch (every 15 min: opens securely; daily: the whole order path incl. a test order proving form → mail server,
  delivery proven at launch and on "Yes, I got it"; renewals 30/7/1 days, certificate 7/1; failures re-checked after a minute,
  a safe Doctor fix if allowed, one email per problem; money never spent) · Security & privacy · Check any address · Who
  it's for. A **Product menu** in the top bar (What it does · Who it's for · Free tools · Learn), a full-screen sheet on phones.
- **Hero.** The six rounded layers in SVG from S10.5 (transform-only motion). A three.js "witness" scene was built in
  S10.5b and removed at the owner's request (S10.5c); it's in git history (`820e824`) if wanted later.
- **Watch this address (S10.5b).** Signed-in users can watch up to 3 addresses: the same read-only public checks as
  Check any address, once a day, one email per NEW problem to their own sign-in address; never submits forms, emails that
  domain or changes anything there. Listed on My shops, removable, deleted with the account.
- **Not built yet:** stored product photos (3–6). No upload storage, re-encoding or EXIF stripping exists today (the
  price-list photo is only read in memory by the Reader); see PROGRESS Decisions.

---

## 9b. Watchdog features, and what's out of scope (S10)

In scope (decided; nothing beyond these): **Renewals** (certificate days left, domain end date, the team mailbox's plan; alerts at
30/7/1 days, never renews or pays), **zone hygiene for our own shop zone** (a daily comparison of the A records on the app domain with
the live shops; fixes are proposed, need the admin's approval, go through the guarded client, shop A records only), and one read-only
finding in **Check any address** (a CNAME whose target doesn't exist: possible dangling record).

**Out of scope, and why.** Domain sniping and drop-catching, portfolio management, defensive registration and brand protection,
bulk agency tooling, domain valuation, throwaway campaign microsites, natural-language DNS for arbitrary hosts, site/email migration,
mailbox warm-up and sender reputation. They serve domain investors and agencies, not home sellers; several spend money automatically;
none makes the order-path proof stronger.

---

## 10. Budget

**GoDaddy:** VPS is added to the cart at $0 by organizers. ~$25 in-store credit covers domain + email. Buy on godaddy.com only after organizers confirm credit; use the CLI to explore and manage.

| Item | Paid by | Expected cost | Rule |
|---|---|---|---|
| 4 vCPU / 8 GB Docker VPS | Organizers ($0 in cart) | $0 | Check out after confirmation |
| App domain | Credit | Cart price; compare with `gddy` | Buy first (unlocks DNS) |
| Titan Pro Light, 1-month term, 1 mailbox | Credit | ~$2–5 | Buy after domain; create hello@ with `gddy` |
| Meera's demo domain | Credit, if room | Cart price | One full launch for the recording |
| Meera's own mailbox | Credit, if room | Another Pro Light month | Likely skip; test orders go to app mailbox (say so) |

If money runs out: skip Meera's domain; full launch on a subdomain; show purchase in dry-run. SMTP tip: if login fails use `smtpout.secureserver.net` with the full address as username.

**Claude: $100, API only, for the product.** None of it for Claude Code.
- ~3 small calls per launch (cents).
- Strong model only for Reader; cheap for Namer + Doctor.
- Dev: saved fixtures, not live calls, for UI work.
- Live link: per-visitor limit, max-token cap per call, daily spend cap.
- Check spend in the Claude console daily.

---

## 11. Submission (HackerEarth, by Nov 20)

| Field | Content |
|---|---|
| Title | LaunchWitness: from description to a proven, live business |
| Description | Demo video link (YouTube, unlisted) first line, then project brief + link to the build replay page |
| Theme | Open Innovation |
| Demo Link | Live app URL on the app domain, with a free sandbox launch judges can try |
| Repository URL | GitHub repo |
| Source Code | Zip of repo, no secrets |
| Additional File | Project brief PDF |

Build process for judges: one combined claude-replay page of all Claude Code sessions, hosted at `https://<APP_DOMAIN>/build`, plus `docs/BUILD_LOG.md`.

---

## 12. Demo video script (3 minutes, screen + voiceover, no face)

| Time | Scene | On screen | Voiceover |
|---|---|---|---|
| 0:00–0:20 | Meera | Instagram: price list highlight, orders in DMs | "Meera has customers. She doesn't have a business online." |
| 0:20–0:45 | Describe | Two lines + price list; profile appears; fix one price | "She describes her business the way she'd tell a friend." |
| 0:45–1:05 | Name + approve | 3 domains with prices; approval card; tap Approve | "Nothing is bought until she says yes." |
| 1:05–1:30 | Launch | Step log streams; site live over HTTPS | "Her site, her domain, her email." |
| 1:30–2:15 | Proof + fix | Test order lands in inbox; one check fails (spam risk); Doctor sentence; fix; green | "Before her first customer, LaunchWitness checks everything, and fixes what's wrong." |
| 2:15–2:40 | Report | "Ready for customers" + timer + expiry warning | "And it keeps checking after launch." |
| 2:40–3:00 | Close | Logo + tagline | "Describe your business. LaunchWitness launches it on GoDaddy, and proves it works before your first customer arrives." |

Never buy a second domain on camera. Record a backup run. Rehearse proof + fix until boring.

---

## 13. Judge Q&A

| Question | Answer |
|---|---|
| Doesn't GoDaddy already have AI for this? | GoDaddy's AI helps people get online. LaunchWitness proves it works (a real order in her inbox) and fixes what doesn't, before customers notice. |
| Who owns the domain? | Demo: my account. Real product: her own GoDaddy account, so she owns everything. |
| What can break after launch? | Not much in a setup we control. Real risks: renewal failing, someone changing settings while connecting another tool. Monitoring is insurance. |
| If her email breaks, how do you alert her? | Personal email, not the business inbox. |
| What if she changes a setting on purpose? | Not undone silently; it asks "Was this you?" first (full monitoring). Auto-fix only when a check fails. |
| What if your server goes down? | Checks stop too. Next step: outside uptime pinger. |
| Why trust AI with money and DNS? | It can't act alone: approval, preview, backup/undo, fixed fixes, spend caps in code. |
| Where does Claude matter? | Messy price list/photo → clean profile + copy; brand-fit names; plain-words diagnosis. Code acts. |
| Why VPS not GoDaddy Hosting? | Docker VPS option runs FastAPI + many seller sites with automatic HTTPS from one box. |
| Confirm delivery for real sellers? | "Yes, I got it" link in the test email; no mailbox password needed. |
| Was the demo failure real? | Staged so it shows reliably; detection and fix are real code. |
| Cost per seller? | A few Claude calls (cents) + domain + mailbox she'd buy anyway. |
| How does she get paid? | Each order shows "Pay ₹X via UPI": a prefilled UPI link on phones and a QR on laptops, with the order ID as the note. Money goes straight from the customer's UPI app to hers; it never passes through us. She marks the order Paid after checking her UPI app. Card payments ("Connect Razorpay") come later, after the seller's KYC. |
| How does the customer know what's happening? | A status page per order (unguessable ID, first name + items only), plus a ready-typed WhatsApp message the seller sends with one tap. No SMS, no WhatsApp Business API. |
| What if she never opens her business inbox? | New orders also go to her personal email, and the customer can send the order to her WhatsApp from the thank-you screen. |
| Can a scammer launch a fake shop? | The owner's email is verified before a real launch, a policy check can hold a shop for review, every shop has "Report this shop", and the team can pause it. |
| Can a salon or tutor use it? | Not yet: v1 is for sellers who take orders. The Reader says so plainly instead of building a half-working shop. |
| Who pays renewal next year? | The seller, to GoDaddy, on her own account. We warn her at 30 / 7 / 1 days. |

---

## 14. Risks and fallbacks

| Risk | Check by | Fallback |
|---|---|---|
| Credits not yet received | Office hours Nov 14 | Build locally against OTE + fakes |
| Domain + Pro Light cost more than credit | Cart, Nov 15 | Cheaper TLD; skip Meera's domain + mailbox |
| Production Availability/DNS API blocked | Nov 15 after app domain | `gddy`, OTE or RDAP; app domain unlocks DNS |
| Mailbox creation fails via CLI/API | Nov 15 | Create in dashboard; engine still sets settings + checks delivery |
| Settings/cert slow on camera | Nov 18 rehearsal | Query authoritative NS; record the full launch |
| Claude spend creeps up | Daily | Fixtures in dev, caps on live link |
| Others build the same launch flow | — | Lead with proof + fix |
| Scope creep | Daily | No stretch before core runs end to end |
| Live demo fails at Dec 11 finale | Dec 11 | Play recording, then Q&A on live app |
