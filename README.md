<p align="center">
  <img src="brand/logo-mark.png" alt="LaunchWitness logo" width="96" />
</p>

<h1 align="center">LaunchWitness</h1>

<p align="center">
  <b>Describe your business. LaunchWitness puts it online on GoDaddy, proves a real order reaches you, fixes what breaks, and keeps checking.</b>
</p>

<p align="center">
  Submission for the <b>GoDaddy Inclusive Innovation Hackathon 2026</b> (Round 2, Open Innovation)
</p>

<p align="center">
  <a href="https://launchwitness.com">Live app</a> ·
  <a href="https://meeras-eggless-bakes.launchwitness.com">Live demo shop</a> ·
  <a href="https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz">Its proof report</a> ·
  <a href="https://launchwitness.com/build">How it was built</a> ·
  <code>&lt;demo video link&gt;</code>
</p>

---

## Contents

1. [The short version](#the-short-version)
2. [The problem](#the-problem)
3. [What LaunchWitness does](#what-launchwitness-does)
4. [Try it in two minutes (for judges)](#try-it-in-two-minutes-for-judges)
5. [The seller's journey, step by step](#the-sellers-journey-step-by-step)
6. [What "proven" means](#what-proven-means)
7. [The Doctor: fixing what breaks](#the-doctor-fixing-what-breaks)
8. [Keeping watch after launch](#keeping-watch-after-launch)
9. [The shop itself](#the-shop-itself)
10. [Safety: why an AI can be trusted with this](#safety-why-an-ai-can-be-trusted-with-this)
11. [How GoDaddy is used](#how-godaddy-is-used)
12. [How Claude is used](#how-claude-is-used)
13. [Architecture](#architecture)
14. [Tech stack](#tech-stack)
15. [Repository layout](#repository-layout)
16. [Running it yourself](#running-it-yourself)
17. [Testing](#testing)
18. [Security](#security)
19. [What's real today, and what isn't yet](#whats-real-today-and-what-isnt-yet)
20. [How it was built](#how-it-was-built)
21. [What's next](#whats-next)
22. [Further reading](#further-reading)

---

## The short version

Lots of tools will build a small business a website. Almost none of them tell the owner whether a customer's order will actually reach them.

**LaunchWitness is a website builder that doesn't stop at "your site is ready".** A home seller types a few lines about their business and pastes their price list (or uploads a photo of it). LaunchWitness then:

1. **Builds** a mobile-friendly shop with their menu, prices, order form, WhatsApp button and UPI payment for each order.
2. **Puts it online** on GoDaddy: the web address, the DNS settings, HTTPS and email.
3. **Proves it works** by placing a real test order through the real order form and following it all the way to the inbox.
4. **Fixes what breaks** using a small, fixed list of safe repairs, and explains every problem in one plain sentence.
5. **Keeps checking** after launch, and emails the owner before something breaks or expires.

The report only says **"Your business is ready for customers."** when every one of those checks has passed, and every claim on it is backed by stored, tamper-evident evidence.

---

## The problem

Meet **Meera** (our demo persona). She bakes eggless cakes at home in Pune. Customers find her on Instagram and order in direct messages. She has no website, no business email, and "DNS" means nothing to her.

Sellers like Meera run into three problems:

| Problem | What it looks like |
|---|---|
| **Setup is technical.** | Domains, DNS records, certificates and email settings are a foreign language. Many small sellers never get online at all, and many of those who plan to want someone else to do it for them. |
| **Half-working setups go unnoticed.** | A missing email setting means order emails land in spam. Studies of small-business domains repeatedly find missing SPF and DMARC records (a March 2026 analysis put DMARC adoption at about 45% for small businesses, against about 75% for large ones). The owner doesn't see an error message. They just think business is slow. |
| **AI could do the setup, but isn't trusted to.** | Setting up a business online means spending money and changing settings. An owner who can't read a DNS record can't check an AI's work. |

LaunchWitness answers all three: it does the technical work, it **proves** the result instead of assuming it, and it is built so the AI can never spend money or change settings on its own.

---

## What LaunchWitness does

In order of importance:

1. **Proof.** Before the owner shares their link with a single customer, a real test order has to travel through their public order form and arrive. LaunchWitness also checks that the address points to the right place, that the site opens securely, and that the email settings are right. Each step is recorded with the time and the server that answered.
2. **Repair (the Doctor).** A failed check is explained in one sentence a non-technical person understands ("Order emails could land in spam: a protection setting is missing"), repaired from a fixed list of five safe fixes, and checked again. Nothing outside that list can ever run.
3. **Watching.** After launch, the site is re-checked every 15 minutes and the settings daily. The owner is emailed at their personal address (not the business inbox, which might be the thing that's broken).
4. **Building, last.** If the seller has no site yet, LaunchWitness builds one from what they typed, in one of six looks designed for home businesses (bakery, home kitchen, handmade, tailoring, gifts, general).

Building is listed last on purpose. Plenty of products build sites. The new part is the proof.

---

## Try it in two minutes (for judges)

No account, no payment, nothing to install:

1. Open **https://launchwitness.com** and press **Try it**.
2. Pick one of the example sellers (or type your own description and price list).
3. Review the shop it built, choose a look, and run a **practice launch**. Practice mode runs every step against a pretend GoDaddy, so nothing is bought and nothing goes on the internet. It is always clearly labelled "Practice".
4. Watch the checks run, then open the report.

To see a **real** launch that has already happened:

- **Live shop:** https://meeras-eggless-bakes.launchwitness.com (its DNS record was written by the app through the GoDaddy API; its HTTPS certificate was issued on demand by Let's Encrypt).
- **Its shared proof report:** https://launchwitness.com/r/GsZj7gOAoCydSauqdNpoaWksKHVW-HSz. Press **Verify** to recompute the evidence chain yourself.

Other things worth a look:

- **Check any address** on the landing page (`/#check`): type any domain and get a plain-English health check of its address, HTTPS certificate and email settings.
- **Demo shops:** `/demo/meera`, `/demo/imran`, `/demo/sunita`.
- **Sign in** with any email address to see the account side. New accounts can practise straight away; real launches need the team's approval during the beta.

---

## The seller's journey, step by step

| # | Step | Who does it | What happens |
|---|---|---|---|
| 1 | **Describe** | Seller + Claude | The seller types a few lines and pastes a price list or uploads a photo of one (even handwritten). One Claude call reads it into a structured profile: business name, products and prices in ₹, hours, area, pickup or delivery, notice needed, UPI name, food licence number if given, plus the shop's wording and look. If the business takes **bookings** rather than orders (a salon, a tutor), it says so plainly and doesn't build a half-working shop. |
| 2 | **Review** | Seller | The profile appears as an ordinary form. The seller fixes anything wrong, adds photos, picks one of six looks and an accent colour, and sees a private live preview. No AI involved. |
| 3 | **Pick a name** | Claude + code | Claude suggests about ten names. Code checks which are really available and what they cost, and shows the best three. (Today, real launches use a free `<shop>.launchwitness.com` address.) |
| 4 | **Approve** | Seller | One card shows every step, every setting as **before → after**, and the exact cost. **Nothing is bought or changed until the seller taps Approve.** |
| 5 | **Launch** | Code only | Back up the current DNS settings, point the address at the server, set up email, turn the site on with HTTPS. Each step streams on screen and is logged. |
| 6 | **Prove** | Code (+ Claude to explain) | Run every check, including a real test order. Anything that fails goes to the Doctor, gets a safe fix, and is checked again. |
| 7 | **Report and watch** | Code | A report with every check, its result and time, the Doctor's explanations, and the full audit log. A shareable read-only link. Monitoring starts. |

After launch the seller also gets an **Orders** page (New → Confirmed → Paid → Done / Cancelled, with a one-tap WhatsApp message to the customer, and a "Customer says paid" note when a customer sends their UPI reference), new-order emails at their personal address, and an account page where they can delete everything.

---

## What "proven" means

Most tools would call a site "live" once the page loads. LaunchWitness is stricter. Each claim on the report comes from a stored `Evidence` row, and each hop is recorded separately:

| Check | How it's proven | Why it's done this way |
|---|---|---|
| **The address leads to the shop** | Asked of the domain's **own authoritative nameservers** (found from its NS records), not a cached resolver. The answering server is recorded. Google, Cloudflare and Quad9 are also asked, as information only. | Cached resolvers can show old answers for hours. The authoritative answer is the truth. |
| **The shop opens securely** | An HTTPS request with full certificate validation, **and** the page must carry the shop's own `<meta name="lw-shop">` marker. | A parked page with a valid certificate would otherwise pass. |
| **Email settings are right** | MX, SPF, DKIM and DMARC are looked up. The email provider is recognised from the domain's mail servers, and advice only ever uses that provider's values. | A missing setting silently sends orders to spam. |
| **A real order arrives** | The checker opens the public shop page, finds the order form and submits it exactly like a customer would (same fields, same form token), carrying a one-time code. Then it records: *form accepted* → *mail server accepted* (with message id) → *in the inbox* (read over IMAP, for mailboxes the app holds) **or** *owner confirmed* (a single-use "Yes, I got it" link inside the test email). | This is the whole point: the path a customer's order takes, tested end to end. |
| **The launch finished cleanly** | The step log shows every step done. | A half-finished launch can be resumed or undone. |

Two rules keep the report honest:

- **"Accepted" is never shown as "delivered".** Until the order is seen in the inbox or the owner confirms it, the report says something like "6 of 7 proven, 1 needs you" and the headline is "Almost ready".
- **"Not sure" is allowed. A wrong answer is not.** Every finding says how sure it is: *seen*, *not seen*, or *couldn't check*. If a lookup fails on our side, that is "couldn't check": never a pass, never the seller's fault, never an alert.

**The evidence is tamper-evident.** Each shop's evidence rows form an append-only hash chain (`app/chain.py`), written only through one function (`proof.add`). Anyone with the shared report link can press **Verify** (or call `GET /r/<token>/verify`), and the server recomputes the chain and says either "Intact" or exactly which saved step changed.

---

## The Doctor: fixing what breaks

Launches go wrong in ordinary ways: settings that haven't spread yet, a certificate that fails first time, a mailbox that isn't ready, a step that stops halfway. The Doctor handles these.

**How it works:**

1. A check fails.
2. For an address, padlock or test-order failure, the Doctor (Claude, cheap model) may first **investigate** using five **read-only** tools: `resolve` (the shop's own address), `fetch` (the shop's own page, through the SSRF guard), `evidence` (the stored proof of this run), `smtp_test` (connect and sign in to the mail server, never send) and `mailbox_status`. It gets at most 4 looks.
3. It answers with a finding in one plain sentence and **either** a fix id from the playbook **or** "needs you" with plain instructions for the owner.
4. **Code** checks the answer and is the only thing that acts.

**The playbook is five fixes, fixed in code** (`backend/app/agents/playbook.py`):

| Fix | What it does |
|---|---|
| `restore_backup` | Put every setting this launch touched back exactly as it was before (undo). Needs the owner. |
| `readd_mx` | Re-add the mail-server setting from the approved plan. |
| `readd_email_auth` | Re-add the SPF / DKIM / DMARC settings from the approved plan. |
| `retry_certificate` | Ask for the HTTPS certificate again. |
| `repoint_site` | Point the address at the shop again. |

**Limits:** at most 3 attempts per check, no fix ever spends money, and every attempt is written to the audit log. A fix the model suggests that isn't in the playbook, or isn't allowed for that check and launch type, is refused and logged. If Claude is unavailable or over budget, plain rules decide instead: if exactly one fix is allowed it is applied and labelled "Standard fix", otherwise the owner gets clear instructions.

On the report, each investigation is shown as a short timeline: *Looked up where your address leads → it leads nowhere → Pointed your address at your shop again → Checked again: working.*

**Describe the problem:** an owner can also type what they or a customer saw ("my customer says the page won't open"). Every check runs again and their words go to the Doctor, fenced off as data so they can't be used as instructions.

---

## Keeping watch after launch

GoDaddy's APIs have no webhooks, so LaunchWitness re-runs its checks on a timer:

| How often | What is checked |
|---|---|
| **Every 15 minutes** | The site opens, HTTPS is valid, the shop marker is present. |
| **Daily** | Address and email settings still match the launch; days left on the certificate and domain; a fresh test order, sent to LaunchWitness's own check mailbox (never to the owner) and found there over IMAP; answers from three public resolvers. |
| **On demand** | "Run checks now" on the report. |

Rules it follows:

- **A seller only gets a test email when she asked for one** (at launch, "Run checks now" or "Describe the problem"). Every test email's subject starts with `TEST, not a real order:` and opens with a grey "This is a check" banner, with no customer call or WhatsApp buttons. Test orders never appear on the Orders page or count against her daily limit.
- A failure is re-checked a minute later to rule out a blip before anything happens.
- Something that needs money or the owner's action (a renewal) is an **alert only**, sent 30, 7 and 1 days ahead.
- A check that has been fixed 3 times in a day and breaks again is no longer fixed automatically. The owner gets one "keeps breaking" email.
- Alerts go to the owner's **personal email**, through an outbox that saves every email first and retries with growing waits, so an order is never lost even if the mail server is down.
- Shops are checked side by side by a small worker pool, each at its own minute, with a 150-second watchdog per check.

**Watch this address:** signed-in users can also have any website (not just their shop) checked daily and get an email when something new goes wrong. Outside addresses are only ever *explained*, never changed.

---

## The shop itself

Every seller's site comes from **one rendering engine and one template**, server-rendered by FastAPI with Jinja2 and chosen by the `Host` header. There is no generated code and no per-seller CSS.

- **Six looks** for home businesses: Bakery & desserts, Home kitchen / tiffin, Handmade & crafts, Tailoring & custom work, Gifts & hampers, General. Claude picks only a **key** (which look, which accent, three short lines of copy). Code validates the key and draws everything: colours, self-hosted fonts, layout and illustrations.
- **Menu with prices in ₹**, a basket that works even without JavaScript, extras listed separately, a search box for long menus.
- **Order form** with date (minimum notice enforced), pickup or delivery (by area or PIN code), time slots, quantities, and totals worked out **on the server**.
- **Payment by UPI, only after an order**: the shop page never shows the seller's UPI ID or QR code. After a real order, the thank-you page (and the order's own private status page) shows "Pay ₹X via UPI" as a prefilled UPI link on phones and a QR code on laptops, with the exact amount and the order ID as the note. Pay-on-delivery orders get no UPI details at all. Money goes straight from the customer to the seller. It never passes through LaunchWitness.
- **"I've paid"**: after paying in their own UPI app, the customer can enter the 12-digit UPI reference (UTR) and, optionally, a screenshot (re-encoded, no hidden data). The seller sees **"Customer says paid"**, never "Paid": they check their own UPI app and mark the order Paid themselves. References and screenshots are private to the seller, and are deleted 30 days after the order closes.
- **Each shop's own signature**: a small set of drawings (sprinkles, leaves, stars and so on) chosen by code from the shop's name, shown as a strip under the top of the page where no text sits, plus gentle touches (add-to-basket, a quick view of each item). The page works the same with JavaScript off.
- **WhatsApp button**, an order status page per order, a privacy page, "Report this shop", and the optional food licence (FSSAI) number.
- **Product photos**: re-encoded to WebP from the pixels alone, so no location or camera data survives.
- **Accessibility and safety**: every colour combination passes WCAG AA (tested), every seller-supplied field is HTML-escaped (tested with hostile input in every field, in every look), and shop pages send a strict Content-Security-Policy.

Screenshots of every look: [`docs/screenshots/s14/contact-sheet.png`](docs/screenshots/s14/contact-sheet.png).

---

## Safety: why an AI can be trusted with this

The core rule: **the model decides and explains; plain code acts and checks.**

| Rule | How it's enforced |
|---|---|
| **Approve before spending** | A purchase in code needs **all three**: `ALLOW_PURCHASE=true` (off by default), a cost under the hard cap `MAX_SPEND_USD`, and a matching approval record from the owner. In practice, domains are bought by the owner on godaddy.com and then adopted. |
| **Preview before changing** | Every DNS change is shown as before → after on the approval card. |
| **Back up, then undo** | The current records are saved before any DNS write. A write without a backup is refused. A failed launch can be put back. |
| **Scoped writes** | A launch can only touch its own domain (or its own subdomain), one record type and name at a time. DNS is never written to a domain that isn't in the app's own database. |
| **Fixed repairs** | The Doctor can only choose from five fixes in code. Anything else is refused and logged. |
| **Everything audited** | Every change of state writes an `AuditEvent` (who, what, when, result), shown in the report. |
| **Sandbox by default** | `GODADDY_ENV=ote` (GoDaddy's test environment) unless production is set explicitly. |
| **No secrets in the repo** | All keys come from environment variables. `.env` exists only on the server. A secret scan of the repo and the whole git history is clean. |
| **Trust and safety for a public tool** | Sign-in by email link (no passwords); team approval before an account can launch for real; a Claude policy check that can only **hold** a shop for human review, never launch one (and holds if it fails); "Report this shop"; a team pause switch; rate limits per visitor and per account; a cap of 40 live shops. |

---

## How GoDaddy is used

GoDaddy is the engine, not decoration.

| Step | GoDaddy product | What LaunchWitness does with it |
|---|---|---|
| **Find a name** | Domains API | Availability and price for the names Claude suggests. |
| **Buy** | godaddy.com checkout | Done by the owner, then adopted after approval. The API purchase path exists but is locked behind the spend guards. |
| **Point and protect** | DNS API | Back up the zone; write scoped records (A, MX, SPF, DKIM, DMARC); undo from backup. All calls share one rate limit (50 a minute, under GoDaddy's 60). |
| **Email** | GoDaddy Professional Email (Titan) | The app's mailbox sends every email over SMTP (`smtpout.secureserver.net`) and reads the inbox over IMAP to prove a test order arrived. |
| **Host** | GoDaddy Docker VPS | Runs everything. Caddy issues an HTTPS certificate for each shop on demand, but only for domains in the app's database. |
| **Verify** | GoDaddy's authoritative nameservers | Checks ask GoDaddy's own nameservers, not a cache, so the result is the real one. |

Hosting is the Docker VPS, not GoDaddy's Hosting API: one box runs the app and every seller site with automatic HTTPS.

---

## How Claude is used

Claude has three jobs, and none of them involve acting on money or DNS.

| Role | Model | Job | Output |
|---|---|---|---|
| **Reader** | Strong (`claude-sonnet-5-5`, vision) | Turn a messy description and price list (text or photo, English or Hinglish) into a strict profile, the shop's wording, and its look. Decide whether the business takes orders or bookings. | Profile JSON. Code tidies and validates every field. |
| **Namer** | Cheap (`claude-haiku-5-5`) | Suggest about ten names that fit the brand. | Names. Code checks availability and price. |
| **Doctor** | Cheap | Investigate a failed check with read-only tools and explain it in one sentence. | A finding plus a playbook fix id or "needs you". Code applies it. |
| **Policy check** | Cheap | Is this shop OK to put live? | OK, or "hold for review" with a reason. It can never launch or unpause. |

**Cost:** roughly 3 calls per launch plus 1 per failed check, a few cents in total. Every call has a tight `max_tokens`, and a daily spend cap stops live calls when reached. During development, saved responses ("fixtures") in `backend/tests/fixtures/` replace live calls, so the UI was built at $0 of API spend. Seller text and tool results are always passed as data, and a prompt-injection fixture is part of the test suite.

---

## Architecture

```
                      ┌──────────────── GoDaddy Docker VPS ─────────────────┐
                      │                                                     │
 browser / phone ───▶ │  Caddy                                              │
 (app, shops,         │   • HTTPS for the app and every shop                │
  shared reports)     │   • on-demand TLS, approved by an internal "ask"    │
                      │     endpoint (only domains in the database)         │
                      │      │                                              │
                      │      ▼                                              │
                      │  FastAPI app (one process)                          │──▶ GoDaddy Domains / DNS APIs
                      │   • JSON API + the built React app                  │──▶ Claude API
                      │   • seller shops (Jinja2, picked by Host header)    │      (Reader, Namer, Doctor, policy)
                      │   • agents: Planner, Executor, Checker (code)       │──▶ SMTP / IMAP (app mailbox)
                      │   • Doctor playbook (code)                          │──▶ public DNS + HTTPS probes
                      │   • outbox (every email saved, then retried)        │      (through the SSRF guard)
                      │   • APScheduler monitoring + worker pool            │
                      │   • SQLite (WAL) on a volume, nightly backups       │
                      └─────────────────────────────────────────────────────┘
```

### The agents

| Agent | Claude or code | Job |
|---|---|---|
| **Reader** | Claude | Description + price list → profile + copy + look |
| **Namer** | Claude suggests, code checks | Available names with real prices |
| **Policy** | Claude decides, code holds | OK to go live, or hold for a human |
| **Planner** | Code | Every step, every before → after setting, and the cost → the approval card |
| **Executor** | Code | Runs the approved plan with the guards, backup first, resumable step log |
| **Checker** | Code | Address, HTTPS, email settings, real test order, clean finish |
| **Doctor** | Claude chooses, code applies | Investigate, explain, pick a playbook fix, re-check |

### Design decisions worth knowing

- **Every outside service sits behind one wrapper with a fake.** GoDaddy, Claude, SMTP, IMAP, DNS and HTTPS each have a real and an in-memory implementation (`app/integrations.py`). Practice mode (`USE_FAKES=true`) and the whole test suite run against the fakes, and tests block every real network call.
- **Practice and real launches run the same code.** Practice swaps the outside world for fakes; the shop page, order handler and checks are identical, and every practice row is labelled.
- **One A record per shop, no wildcard.** Each real shop gets exactly one DNS record written by the app, so a shop that doesn't exist doesn't resolve.
- **SQLite on purpose.** One VPS, one app process (the app refuses to start a second), WAL mode, online backups (7 daily + 4 weekly) with a tested restore. Moving to Postgres is a small change because every table is a SQLModel model.
- **The checker can't be turned into a weapon.** It reaches websites only through `SafeWeb`: it resolves the host once, refuses private, loopback and cloud-metadata addresses, pins the checked IP, and re-checks every redirect.
- **The app container uses public DNS resolvers.** The VPS's own resolvers returned wrong answers for some domains during testing, so the app asks 8.8.8.8, 1.1.1.1 and 9.9.9.9 instead.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel + SQLite, httpx, dnspython, APScheduler, Jinja2, Pillow, segno (QR codes), `anthropic` SDK |
| Frontend | React 18, Vite 5, TypeScript, plain CSS (no UI kit) |
| Seller sites | Server-rendered Jinja2, one template, six themes, self-hosted open-licence fonts |
| Infrastructure | GoDaddy Docker VPS, Docker Compose, Caddy (automatic HTTPS, on-demand TLS) |
| Email | GoDaddy Professional Email over SMTP and IMAP; Mailpit for the local stack |
| Testing | pytest (1,580+ backend tests), Playwright end-to-end flows, ruff |

---

## Repository layout

```
backend/
  app/
    main.py              FastAPI app, routers, host-based shop routing
    config.py            settings from environment variables
    models.py, db.py     SQLite tables (Business, Plan, DnsBackup, Evidence, AuditEvent, Approval, ...)
    agents/              reader, namer, policy, doctor, investigator (Claude);
                         planner, executor, checker, launch_check, playbook (code)
    checks/              DNS lookups, HTTPS probes, email-settings checks, SSRF-safe fetch
    godaddy/             GoDaddy API client (ote|prod, scoped DNS writes), availability, email, rate limit
    sites/               shop rendering, themes, orders, fulfilment rules, templates, fonts
    mail/                SMTP, IMAP, email layout
    monitor/             scheduler for light monitoring
    safety/              spend guard, access control, CSRF/origin guard, route table
    proof.py, chain.py   evidence rows and the hash chain
    outbox.py            every email saved first, then sent and retried
    routers/             API routes (auth, businesses, launch, report, admin, watch, ...)
  tests/                 pytest suite + fixtures (saved Claude responses, sample sellers)
frontend/                React + Vite app (landing, describe, review, launch, report, orders, admin)
e2e/                     Playwright end-to-end tests
deploy/                  Dockerfile, docker-compose files, Caddyfile (local) and Caddyfile.prod
scripts/                 backups, checks, demo seeding, screenshots, secret scan, replay builder
docs/                    spec, build plan, progress, build log, security, checks matrix, runbooks, screenshots
replay/                  redacted Claude Code session transcripts (served at /build)
```

---

## Running it yourself

### Option 1: practice mode on your machine (no keys needed)

Practice mode uses in-memory fakes for GoDaddy, DNS, the mailbox and HTTPS, and saved Claude responses, so you don't need any API keys.

```bash
cp .env.example .env                       # defaults are safe: fakes on, sandbox, purchases off
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm install && npm run build)

cd backend
../.venv/bin/pytest -q                     # run the tests (no network)
../.venv/bin/uvicorn app.main:app --port 8000
```

Open http://localhost:8000. For local development set `DEV_MODE=true` in `.env` so sign-in links appear on screen instead of being emailed (it refuses to start on https). `cd frontend && npm run dev` runs the frontend with hot reload and proxies `/api` to port 8000.

> **On Windows**, use `.venv/Scripts/python -m pytest` and `.venv/Scripts/python -m uvicorn ...` instead.

### Option 2: the full stack with Docker

```bash
docker compose -f deploy/docker-compose.yml up --build      # → http://localhost
```

A production-like stack (real HTTPS through Caddy's local certificate authority, `DEV_MODE=false`, fakes, and Mailpit to catch emails at http://localhost:8025):

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml \
  -f deploy/docker-compose.local.yml up -d --build --wait     # → https://launchwitness.localhost
bash scripts/check_m1.sh --local                              # automated checks of the running stack
```

### Option 3: production on a VPS

Follow [`docs/RUNBOOK_M1.md`](docs/RUNBOOK_M1.md) and [`docs/NEXT_SESSION_VPS.md`](docs/NEXT_SESSION_VPS.md). In short: fill `.env` on the server (never in the repo), then

```bash
docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
bash scripts/check_m1.sh
```

Backups: `bash scripts/backup_db.sh` (7 daily + 4 weekly), restore with `bash scripts/restore_db.sh <file>`.

### Rehearsing the demo

```bash
python3 scripts/seed_demo.py --launched     # creates Meera's shop and runs a practice launch
python3 scripts/seed_demo.py --reset        # removes it
```

To show the Doctor at work, sign in as the team (`ADMIN_EMAIL`), open a shop's report, and use the demo switch to stage a fault: the address leads nowhere, a parked page, a broken padlock, or a refused mail sign-in. The fault is staged so the demo is reliable; detecting and fixing it is real code.

### Key environment variables

All are listed in [`.env.example`](.env.example) with safe defaults.

| Variable | Default | Meaning |
|---|---|---|
| `USE_FAKES` | `true` | Use in-memory fakes for every outside service |
| `GODADDY_ENV` | `ote` | GoDaddy sandbox; `prod` only when set explicitly |
| `ALLOW_PURCHASE` | `false` | Purchases are impossible unless turned on |
| `MAX_SPEND_USD` | `15` | Hard limit on any single purchase |
| `CLAUDE_MODE` | `fixture` | `fixture` uses saved responses; `live` calls the API |
| `CLAUDE_DAILY_SPEND_CAP_USD` | `3` | Live Claude calls stop when reached |
| `DNS_MODE` | `per_shop` | One A record per shop (or `wildcard`) |
| `MONITOR_ENABLED` | `true` | Background monitoring (tests never start it) |
| `MAX_LIVE_SHOPS` | `40` | Upper limit on real shops |

---

## Testing

```bash
cd backend && ../.venv/bin/pytest -q          # 1,580+ tests, no network access allowed
.venv/bin/python -m ruff check backend        # lint
cd frontend && npx tsc --noEmit && npm run build
cd e2e && npm install && npx playwright install chromium && npx playwright test
bash scripts/secret_scan.sh                   # secrets in the repo and the whole git history
```

What the tests cover, among other things:

- **Every check scenario** in [`docs/CHECKS_MATRIX.md`](docs/CHECKS_MATRIX.md): about forty website and email situations, each with the exact wording shown, how sure it is, and what the Doctor may do.
- **Access control:** every owner route tested as owner, another seller, a guest, logged out and admin. A test fails if any route is missing from the route table.
- **XSS:** a hostile string in every free-text field, every product field and the order form, parsed with a real HTML parser, in every theme.
- **SSRF:** private ranges, redirect re-checks, IP pinning, redirect loops.
- **Safety guards:** purchases blocked without all three conditions, DNS writes refused without a backup or outside the database.
- **The Claude agents** against saved real responses, including a prompt-injection seller and a handwritten price-list photo.
- **End-to-end flows** in a real browser: a full seller journey, two sellers who must not see each other's shops, guest practice, sign-in, legal pages, every theme launched in practice with no console errors or CSP violations, and more.

---

## Security

A one-page overview is in [`docs/SECURITY.md`](docs/SECURITY.md). Highlights:

- **Ownership checks** are part of the database query, so another owner's shop answers 404, the same as one that doesn't exist.
- **CSRF:** every state-changing request needs the app's Origin and a token bound to the session cookie.
- **Cookies** are `__Host-` prefixed, Secure, HttpOnly and SameSite=Lax with no Domain, so shop subdomains never receive them.
- **Tokens** (sign-in, share, "Yes, I got it") are 32 random bytes and only their SHA-256 hash is stored.
- **Uploads** are size-capped, checked by content, and the price-list photo is never stored.
- **The certificate "ask" endpoint** is closed to the public at both Caddy and the app.
- **Privacy:** a customer's street address appears only on the owner's Orders page and in the order email, never in logs, evidence or the shared report.

---

## What's real today, and what isn't yet

Being honest about the state of a hackathon build:

**Real and running in production**

- The app at https://launchwitness.com on a GoDaddy Docker VPS, with Let's Encrypt HTTPS.
- A real shop launched by the app: its DNS record written through the GoDaddy API with a backup first, its certificate issued on demand, all seven checks proven, and a shareable report with an intact evidence chain.
- Real email: sign-in links, order emails and test orders sent through GoDaddy Professional Email, and test orders found in the inbox over IMAP.
- Monitoring, nightly database backups, and a tested restore.
- Private UPI: the live shops show UPI details only after an order, and customers can tell the shop they paid (UTR and an optional screenshot), which the seller checks before marking the order Paid.

**Not done yet**

- **Real launches on the seller's own domain** were cut for this round. They work in practice mode; real launches use a free `<shop>.launchwitness.com` address.
- **Creating a mailbox for each seller** through GoDaddy's email API is still a stub. Test orders go to the app's own mailbox, or the owner confirms with "Yes, I got it".
- **The admin** is whoever controls the `ADMIN_EMAIL` inbox. There is no second factor yet.
- **The demo fault** is staged so it shows reliably on camera. The detection and the fix are real.
- **Payments** are UPI links only. No money passes through LaunchWitness, so it never confirms a payment: "Customer says paid" stays a claim until the seller checks their UPI app. Card payments (a gateway, after the seller's KYC) are future work.

---

## How it was built

The whole product was built in **Claude Code**, over recorded sessions, each following a fixed ritual written in [`CLAUDE.md`](CLAUDE.md):

1. Read the progress file and propose a plan mapped to the acceptance criteria in [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md).
2. Wait for the owner's OK before coding.
3. Make small, tested commits.
4. Update [`docs/PROGRESS.md`](docs/PROGRESS.md) and [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md), then save a transcript that is redacted and secret-scanned before it is committed.

Product decisions (scope, safety rules, budget, what to postpone) stayed with the human. When the spec didn't answer something, the simplest option was chosen and recorded under "Decisions". A few hard rules held across every session: no secrets in the repo, Claude Code never spends money, GoDaddy defaults to the sandbox, and live Claude calls during development were kept to a minimum by using saved responses.

Every feature session ended with a check in a real browser at phone width, which caught real bugs. The full record is replayed at **https://launchwitness.com/build**, and a human-written summary of each session is in [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md).

---

## What's next

1. **Run on the seller's own GoDaddy account**, so they own everything and monitoring matters most.
2. **Own-domain launches and per-seller mailboxes**, using the guarded purchase path and GoDaddy's email API.
3. **Change detection:** when a setting changes, ask "Was this you? Tap to restore" instead of fixing silently.
4. **A `/verify` page** backed by a DNS TXT record, so buyers can tell a seller's real shop from a fake using their name.
5. **More trades and languages:** bookings for salons and tutors, more Indian languages for the description.
6. **Card payments** ("Connect Razorpay") after the seller's KYC.

---

## Further reading

| Document | What's in it |
|---|---|
| [`docs/SPEC.md`](docs/SPEC.md) | The full product spec |
| [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md) | Milestones and acceptance criteria |
| [`docs/CHECKS_MATRIX.md`](docs/CHECKS_MATRIX.md) | Every check scenario, its wording, and the test that proves it |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security on one page |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Status, decisions and open questions |
| [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) | One entry per build session |
| [`docs/RUNBOOK_M1.md`](docs/RUNBOOK_M1.md) | Going live on the VPS, step by step |
| [`deploy/README.md`](deploy/README.md) | The Docker setup in detail |
| [`e2e/README.md`](e2e/README.md) | Running the end-to-end tests |

---

<p align="center">
  Built for the GoDaddy Inclusive Innovation Hackathon 2026. LaunchWitness is a working name.
</p>
