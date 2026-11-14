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
   - Claude (one call) returns the business profile (name, products, prices, hours, area, tone) **plus** the site copy (tagline, about, item descriptions).
2. **Review.** She sees the profile as a form and fixes anything wrong. No AI.
3. **Pick a name.** Claude (one small call) suggests ~10 domain names; code checks real availability + price; shows the best 3.
4. **Preview and approve.** Code fills the fixed template: menu with prices, about, hours, order form, "Order on WhatsApp" link (`wa.me`), UPI QR, privacy page. One approval card lists the domain, total cost and every setting to be made. **Nothing is bought or changed until she taps Approve.**
5. **Launch.** Code only: back up DNS, buy the domain (or use a free sandbox subdomain), point it at the server, set up email, put the site live with HTTPS. Each step streams on screen.
6. **Launch check.** Code checks the site opens, HTTPS is valid, email settings are correct, then places a real test order through her form. If anything fails, the Doctor explains it in one sentence, applies a safe fix or undoes the change, and re-checks until green.
7. **Report and watch.** Report headed **"Your business is ready for customers"**: every check, result, time passed. After launch, the same checks re-run lightly on a timer and alert her if something breaks.

**Two launch modes, same code:**
- **Sandbox launch** at `<slug>.<APP_DOMAIN>`: free, real DNS writes on the app's own domain, real checks. Used for development, rehearsals and judges trying it.
- **Full launch** on a purchased domain: run once, for the recorded demo.

---

## 4. Features

Eight core features first; no stretch item starts until all eight run end to end.

| # | Feature | Tier | What it does |
|---|---|---|---|
| 1 | Business reader | Core | Description + price list (text or photo) → editable profile + site copy, one Claude call |
| 2 | Name finder | Core | Claude suggests names; code checks real availability and price; shows 3 |
| 3 | Site builder | Core | One fixed template: menu, about, hours, order form, WhatsApp link, UPI QR, privacy page |
| 4 | Launch engine | Core | Plan → preview of changes → approval card → execute (GoDaddy Domains, DNS, Email); sandbox + full modes |
| 5 | Launch check | Core | Site resolves, HTTPS valid, email settings present, real test order arrives |
| 6 | Repair during launch | Core | Doctor explains a failed check, applies a playbook fix or undoes from backup, re-checks |
| 7 | Launch report | Core | One page per business: every check, result, timestamp, plus audit log |
| 8 | Light monitoring | Core (light) | Timer re-checks, domain/cert expiry warnings, alert to personal email, "Run checks now" |
| 9 | Full monitoring | Stretch | Daily test order, change detection ("Was this you?"), incident history |
| 10 | /verify page | Stretch | Official Instagram/WhatsApp listed, backed by a DNS TXT record, so buyers spot fakes |
| 11 | MCP server | Stretch | Engine tools over MCP behind the same safety gates |
| 12 | Fleet view | Stretch | Dashboard of all launched businesses |

Out of scope: payments, inventory, WhatsApp/Instagram APIs, multiple templates, custom code generation.

---

## 5. Agents

Claude decides and explains; plain code acts and checks. Three steps use Claude; nothing that spends money or changes settings is left to the model alone.

| Agent | Job | Claude or code | Model | Output |
|---|---|---|---|---|
| Reader | Profile + site copy from text or photo | Claude, 1 call | Strong (vision + structured output) | Profile JSON + copy |
| Namer | Suggest names; check availability + price | Claude suggests, code checks | Cheap | 3 available domains with prices |
| Planner | Every action, setting and cost | Code, fixed schema | — | Plan + before/after preview |
| Executor | Run the approved plan step by step, backup first | Code only | — | Step log |
| Checker | Live checks | Code only | — | Pass/fail per check |
| Doctor | Explain a failed check in one sentence; pick a fix | Claude chooses, code applies | Cheap | Fix + re-check result |

A manager loop runs them in order and stops at the approval card. **Doctor playbook (fixed, in code):** undo from backup · re-add MX · re-add SPF/DKIM/DMARC · retry certificate · re-point site address. It cannot write arbitrary settings.

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

**Honest framing:** in the demo everything sits in the app's GoDaddy account, so little can break after launch. Monitoring matters most once it runs on her own account. Pitch it as insurance, not the hero.

---

## 8. Architecture and GoDaddy usage

One GoDaddy Docker VPS (4 vCPU / 8 GB, provided at $0) runs everything; GoDaddy and Claude are called as APIs.

- **Caddy:** HTTPS for the app and every seller site; on-demand TLS with an `ask` endpoint that only approves domains in the DB.
- **FastAPI:** agents, API, monitoring scheduler, and every seller site (served by `Host` header from one template + profile).
- **React (Vite):** seller-facing app, built and served as static files.
- **SQLite:** profiles, plans, DNS backups, check results, audit log.
- **Outside:** Claude API; GoDaddy Domains/DNS/Email (OTE sandbox in dev, `GODADDY_ENV=ote|prod`); SMTP through the app's one mailbox.
- **Secrets** live only in environment variables.
- **Sandbox subdomains** need a wildcard `*.<APP_DOMAIN>` A record → VPS.

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
