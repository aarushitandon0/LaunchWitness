# LaunchWitness: from description to a proven, live business

*GoDaddy Inclusive Innovation Hackathon 2026 · Open Innovation · one-page brief (draft for the PDF)*

> **Describe your business. LaunchWitness launches it on GoDaddy and proves everything works before your first customer arrives.**

## Problem

Small sellers like Meera, who bakes cakes at home and takes orders in Instagram messages, either never get online or end up with a setup that is quietly broken.
- **Setup is technical.** A GoDaddy survey found 63% of India's small businesses had no website. Of those planning one, 30% wanted someone to build and manage it for them. *(Older survey: background only. A 2025–26 figure is still to find.)*
- **Half-working setups go unnoticed.** Only 44.9% of small businesses use DMARC, against 75.3% of large enterprises (March 2026). In a scan of small-business domains, 36% had no SPF record. The result is that order emails land in spam, and the owner just thinks business is slow.
- **AI could do the setup, but isn't trusted to.** It means spending money and changing email settings for someone who can't check the work.

## Solution

Meera types two lines and pastes her price list.
- **Reader:** LaunchWitness builds her mobile site (menu in ₹, WhatsApp button, UPI QR, order form).
- **Namer:** it suggests real, available domain names with their prices.
- **Approval card:** one card shows every step, every setting as before and after, and the exact cost. Nothing happens until she approves.

Then it **launches and proves**. It points the domain, sets up her business email and turns on HTTPS. Then it checks every part for real: the address, the HTTPS certificate, the four email settings, and **a real test order arriving in her inbox**. A failed check is explained in one plain sentence ("Order emails could land in spam: a protection setting is missing"), fixed from a safe playbook, and re-checked to green.

The report says **"Your business is ready for customers"**, with the time each check passed. After launch it keeps watching:
- every 15 minutes: the site and HTTPS
- daily: the email settings and the days left on the domain and certificate

Warnings go to her personal email.

## How GoDaddy is used

GoDaddy is the engine, not decoration:
- **Domains:** availability and price for the suggested names. Purchase stays with the owner on godaddy.com and is adopted after her approval.
- **DNS API:**
  - a backup of the zone before any change
  - scoped record writes (A, MX, SPF, DKIM, DMARC)
  - undo from the backup
  - checks asked of GoDaddy's authoritative nameservers
- **Email (Titan):** creates or adopts the business mailbox, then sends and receives orders through `smtpout.secureserver.net` / IMAP.
- **Docker VPS:** hosts everything. Caddy issues HTTPS for every seller site on demand, but only for domains in the app's database.

Sandbox launches use free subdomains of the app's own domain, so judges can try the real flow without buying anything.

## How Claude is used

Claude **decides and explains**; code **acts and checks**. There are three Claude roles:
- **Reader** (strong model, 1 call): description, price list or photo → a strict profile schema.
- **Namer** (cheap model): suggests about 10 names, which code then checks.
- **Doctor** (cheap model): one plain sentence for a failed check, plus a fix id. The fix must come from a fixed playbook, and code applies it.

A launch costs about 3 calls plus 1 per failed check, with `max_tokens` limits and a daily spend cap. The whole product was also **built with Claude Code** in recorded sessions. A planned, tested and documented session ritual is replayed at `/build`, with a summary of each session in `BUILD_LOG.md`.

## Safety

- **Approve before spending.** Purchases are off by default, have a hard spend cap and need the owner's approval record.
- **Preview before changing.** Every DNS change is shown as before and after.
- **Back up, then undo.** Writes without a backup are refused.
- **Scoped actions.** A launch only touches its own domain, one record at a time. The Doctor can't act outside its 5-fix playbook (max 3 attempts, never spends money); anything else is refused and logged.
- **Full audit log** in every report.
- **Safe public link:** practice mode for visitors, per-visitor limits, a secret owner link per business, and no secrets in the repo.

## What's next

1. Go live on the GoDaddy VPS and app domain; launch Meera's real domain on camera.
2. Full monitoring: a daily real test order, and change detection ("Was this you? Tap to restore") instead of silent fixes.
3. A `/verify` page backed by a DNS TXT record, so buyers can spot fake shops using her name.
4. Run on the seller's own GoDaddy account, where monitoring matters most.
5. More languages for the description, and a template per trade (food, tailoring, tuition).
