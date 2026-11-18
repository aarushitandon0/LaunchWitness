# VPS day (Wed 18 Nov 2026, IST): put LaunchWitness on the internet, then prove one real shop

Written so a model (or a person) can do it **cold**. You need nothing else open except `CLAUDE.md`. Steps are in
order; each ends with **✔ Check**, and you don't go on until it passes. `(laptop)` = the owner's computer, `(vps)` = the
server. Replace `<VPS_IP>` everywhere. The app domain is `launchwitness.com`. Last brought up to date: **S13b** (Nov 17).

**Ground rules (from CLAUDE.md):** never print, paste or commit a secret, and the owner types every secret into the
server's `.env` herself. No purchases (`ALLOW_PURCHASE=false`, always). The only DNS records made by hand are `A @`
(and optionally `www`); the app writes each shop's own A record (`DNS_MODE=per_shop`). **No wildcard** unless GoDaddy's
API refuses us (see the section at the end). Don't touch MX / TXT / CNAME: they carry the mailbox `hello@launchwitness.com`.

What's already proven on the laptop / in Docker (S10, S12, S13b, `deploy/README.md`): the image builds from a clean
clone, runs as non-root with one process, HTTPS through Caddy, `__Host-` cookies, `/internal` blocked, the shop-host
guard, rate limits on the real client IP, a restart and a kill mid-launch, backup + restore, 16 browser flows (incl.
an order kept while email is down and the honest "trouble sending" sign-in), and after a restart: one monitor job,
one outbox sender, stuck `sending` emails put back in the queue. S11c also made one real GoDaddy DNS write and undid it
(it worked, hence `per_shop`). **Not proven until today:** real Let's Encrypt certificates, a shop record written by the
running app, an outside-in test order over the internet, an IMAP delivery proof, real Gmail delivery (inbox vs spam).

### What changed since this guide was first written (S10.5 → S13)

| Since | What | What it means today |
|---|---|---|
| S10.5 | **Go-live checklist** (`app/golive.py`) | "Launch for real" stays disabled until the shop has: a signed-in email, name + address + one priced item, WhatsApp **checked by the owner** ("Test this number" → "Yes, that's me"), UPI ID + display name **checked by the owner** (the ₹1 test → confirm the name), pickup/delivery, hours, **the two ticks** (makes/sells these herself; accepts the Terms) and one look at the preview. Step 10. |
| S11c | **`DNS_MODE=per_shop`** (default) | One A record per shop, written by the app through the guarded client. `wildcard` is the fallback (last section). `wait_dns` and `/internal/tls-ask` need **every** nameserver to agree. |
| S11c | **`CLAUDE_MODE=live`** + spend cap | Reader / Namer / go-live policy check / Doctor call Claude for real. `CLAUDE_DAILY_SPEND_CAP_USD` stops calls for the day; at the cap the policy check holds real launches for the team (safe, manual). |
| S11d | **Hash-chained proof** | Evidence rows are a per-shop hash chain. On the first start, rows from before the chain are chained once (`evidence_chain_backfilled` in the audit log; a fresh database has none, so nothing to do). The shared report's **Verify** recomputes it. |
| S13 A | **Email outbox** | Every email (sign-in, orders, test orders, alerts, team mail, contact) is saved first, tried at once, then retried by the `outbox_send` job (every 20 s; backoff 30 s → 30 min, ~2 h, then "dead" on the team page, "Email outbox" card). `SMTP_DAILY_LIMIT=450` (GoDaddy allows 500/day per mailbox): from 80% test orders wait, at 100% alerts wait; sign-in links and orders never wait. |
| S13 B | **One-minute monitor beat** | One `monitor_tick` job a minute replaces the old two jobs: each shop has a stable minute in the 15 minutes and in the day, 4 workers (`MONITOR_WORKERS`), a 150 s watchdog per check, the daily test order's inbox look happens in up to 3 later one-minute passes. |
| S12 | Demo switch, photos, incidents | Practice only; nothing to set up. |

---

---

> **S17 (2026-11-19): the app container uses public DNS on purpose** (8.8.8.8, 1.1.1.1, 9.9.9.9 via `dns:` in
> `deploy/docker-compose.prod.yml`). The VPS's GoDaddy resolvers give wrong answers for some addresses (example.com → a GoDaddy IP, no SPF).
> Don't "fix" it back; details in `docs/SECURITY.md` "DNS the app trusts".

## 0. Before you touch anything (laptop, 5 min)

- **Write down what `A @` points to now** (GoDaddy's parked page): godaddy.com → launchwitness.com → DNS → the `A @`
  value. That's the rollback value.
- `git log --oneline -1` on `main` is the version you'll deploy. Run the suite once: `cd backend && ../.venv/Scripts/python -m pytest -q | tail -1`.

## 1. SSH key, user, firewall (vps)

```bash
# (laptop) a key just for this server
ssh-keygen -t ed25519 -f ~/.ssh/launchwitness -C "launchwitness-vps"
cat ~/.ssh/launchwitness.pub          # paste into the VPS dashboard (SSH keys), or: ssh-copy-id -i ~/.ssh/launchwitness.pub root@<VPS_IP>
ssh -i ~/.ssh/launchwitness root@<VPS_IP>

# (vps, as root) a normal user with your key
adduser --disabled-password --gecos "" lw && usermod -aG sudo lw
mkdir -p /home/lw/.ssh && cp ~/.ssh/authorized_keys /home/lw/.ssh/ && chown -R lw:lw /home/lw/.ssh && chmod 700 /home/lw/.ssh
echo 'lw ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/lw

# key login only
sed -i -E 's/^#?PasswordAuthentication .*/PasswordAuthentication no/; s/^#?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
grep -rl 'PasswordAuthentication yes' /etc/ssh/sshd_config.d/ 2>/dev/null | xargs -r sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/'
systemctl restart ssh || systemctl restart sshd

# firewall: only 22, 80, 443
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
```

Note: Docker-published ports go **around** ufw. That's fine for Caddy's 80/443 (we want them open), and it's one
more reason **port 8000 must never be published** (`deploy/README.md`, "Rules").

**✔ Check** from a NEW laptop terminal (keep the root one open until this works):
`ssh -i ~/.ssh/launchwitness lw@<VPS_IP> 'whoami; sudo ufw status | head -8'` prints `lw` and 22/80/443 ALLOW, and
`ssh root@<VPS_IP>` is refused.

## 2. Docker (vps, as lw)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker lw && newgrp docker
```

**✔ Check:** `docker run --rm hello-world` and `docker compose version` (v2.x).

## 3. Clone (vps)

```bash
sudo apt-get install -y git sqlite3 dnsutils
git clone https://github.com/aarushitandon0/LaunchWitness.git ~/LaunchWitness && cd ~/LaunchWitness && git log --oneline -1
```

(Private repo: a read-only deploy key, see `docs/RUNBOOK_M1.md` step 3.)

**✔ Check:** the commit matches step 0; `ls deploy` shows `Caddyfile.prod docker-compose.yml docker-compose.prod.yml`.

## 4. `.env`, on the server only (the OWNER fills it in)

```bash
cd ~/LaunchWitness && cp .env.example .env && chmod 600 .env && nano .env
```

The owner types the values; nobody else sees them. Use **"The production `.env` checklist"** at the end of this
file: every variable, what to put, no values. The ones that matter most today: `USE_FAKES=false`, `SERVER_IP`,
`GODADDY_ENV=prod` + its key/secret, `CLAUDE_MODE=live` + `ANTHROPIC_API_KEY` + `CLAUDE_DAILY_SPEND_CAP_USD=2`,
the SMTP/IMAP password, `SMTP_DAILY_LIMIT=450`, `DNS_MODE=per_shop`, a fresh `ADMIN_TOKEN`, and `MAILBOX_EXPIRES_ON`.

**✔ Check:** `ls -l .env` shows `-rw-------`; `git status --short` doesn't list `.env`.

## 5. Start the stack, first with Let's Encrypt STAGING

Staging certificates aren't trusted by browsers, but the staging CA has far higher rate limits, so the first
attempts (while DNS may still be spreading) can't burn the real quota (50 certificates per domain per week, 5 failed
validations per hostname per hour).

```bash
cd ~/LaunchWitness
alias lwc='docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml'
echo "alias lwc='docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml'" >> ~/.bashrc
ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory lwc up -d --build --wait
lwc ps && lwc logs app | grep -E 'self-check|reconcile|monitor started'
```

The app logs its self-check. Expect **no** `self-check [...]` lines. Each one names a wrong setting; fix it in `.env`
and run `lwc up -d`. Also expect exactly these two lines per start (S13):

```
startup reconcile: {'plans': 0, 'check_runs': 0, 'outbox': 0}
monitor started (pid 1): jobs=['guest_cleanup', 'monitor_tick', 'outbox_send', 'team_renewals', 'watch_addresses', 'zone_hygiene']
```

`monitor_tick` and `outbox_send` must each appear **once** (`check_m1.sh` checks it). A non-zero `outbox` count after
a restart is normal: emails that were mid-send are put back in the queue and go out within a minute.

## 6. Point `A @` at the VPS (the ONLY hand-made record)

godaddy.com → launchwitness.com → DNS → edit **A `@`** → `<VPS_IP>`, TTL 600. Optionally add **A `www`** →
`<VPS_IP>` (no app code serves `www`; it would only redirect if you add a Caddy block. Skip it unless wanted).
**Don't add `*`.**

**✔ Check (can take up to an hour):**
```bash
dig +short NS launchwitness.com                                   # e.g. ns55.domaincontrol.com.
dig +short launchwitness.com @ns55.domaincontrol.com              # <VPS_IP>   (the zone's own server, not a cache)
dig +short test123.launchwitness.com @ns55.domaincontrol.com      # nothing (no wildcard)
curl -sk https://launchwitness.com/api/health                     # {"ok":true,...}  (-k: staging cert)
```

## 7. Switch to the real CA

Only after **both** nameservers answer with the VPS (Let's Encrypt may ask either one; a failed try counts against
5 per name per hour): `for ns in $(dig +short NS launchwitness.com); do dig +short launchwitness.com @$ns; done`
must print `<VPS_IP>` twice. The app does the same for every shop: a shop is turned on only when every nameserver
answers, and `/internal/tls-ask` asks them again before it lets Caddy request a certificate.

```bash
lwc up -d --wait          # without ACME_CA: back to Let's Encrypt production
lwc logs caddy | grep -iE 'certificate obtained|error' | tail
```

**✔ Check:** `curl -sS https://launchwitness.com/api/health` works **without** `-k`, and the landing page opens on a phone
with a padlock.

## 8. The stack check

```bash
EXTERNAL_SUBJECT="VPS external test" bash scripts/check_m1.sh   # first send that email to hello@ from another account
```

It checks: `A @` and no wildcard, HTTPS + HSTS + http→https, `/internal` blocked (5 spellings) but working inside the
network, the session cookie's flags over https (a one-time token, no email sent, signed out again), the ADMIN_EMAIL user,
the self-check, exactly one uvicorn, SMTP + IMAP login, a contact message arriving over IMAP, `.env` mode 600, the SMTP
password in no file or commit. **✔ Check:** `Stack check: all checks passed.` (WARN lines are explained in place.)

## 9. Backups (cron) and the off-server copy

```bash
bash scripts/backup_db.sh                    # first one now: backups/daily/ and backups/weekly/
( crontab -l 2>/dev/null; echo '15 3 * * * cd $HOME/LaunchWitness && bash scripts/backup_db.sh >> backups/backup.log 2>&1' ) | crontab -
crontab -l
```

**Manual TODO for the owner:** an off-server copy. Nothing does it automatically (no cloud service was chosen). Weekly from
the laptop: `scp -i ~/.ssh/launchwitness -r lw@<VPS_IP>:LaunchWitness/backups ./lw-backups-$(date +%F)`. Backups
hold customers' names and phone numbers: keep that folder private.

## 10. The first real GoDaddy write: one shop A record, through the app

This is the first time code writes to the real zone. The write goes through `GoDaddyClient.set_records`, whose
app-zone guard allows only an `A` record for a valid shop name on `launchwitness.com`; the executor saves a `DnsBackup`
first. Both are unit-tested but **new on the real API**, so watch it.

1. The owner signs in at `https://launchwitness.com/#/signin` with `ADMIN_EMAIL` (the link arrives in her inbox).
2. **For the IMAP proof (step 12) the shop's owner must be `hello@launchwitness.com`**, the mailbox the app can read.
   In a private window, sign in as `hello@launchwitness.com` (open the link from GoDaddy webmail,
   email.secureserver.net). As the admin, approve that account on `#/admin`.
3. As hello@: Describe → the demo shop (e.g. Meera's text from `backend/tests/fixtures/sellers/meera_cakes.json`) →
   address `meerasbakes`. Then the **go-live checklist** (the Launch page lists what's missing; "Launch for real" is
   disabled until all of it is done, and the server refuses it too):
   - WhatsApp number → **Test this number** (opens WhatsApp to that number) → **Yes, that's me**.
   - UPI ID + the name the UPI app shows → the **₹1 UPI test** (her shop's real QR for ₹1) → confirm the name matches.
   - Pickup area and/or delivery areas, working days and hours.
   - **The two ticks:** "I make or sell these myself" and "I accept the Terms" → save.
   - **Preview my shop** once.
   Then Launch → **for real**. With `CLAUDE_MODE=live` the go-live policy check runs (one cheap call). If the daily spend
   cap is reached, or `CLAUDE_MODE=fixture`, the launch is **held for team review** (`#/admin`) instead: safe, not a bug.
4. Watch while it runs:
   ```bash
   lwc logs -f app                                                   # the plan's steps
   dig +short meerasbakes.launchwitness.com @ns55.domaincontrol.com  # <VPS_IP> once written
   ```
5. In the database: the backup taken before the write, and the steps:
   ```bash
   lwc exec -T app python - <<'PY'
   from sqlmodel import Session, select
   from app.db import get_engine
   from app.models import AuditEvent, DnsBackup
   with Session(get_engine()) as s:
       b = s.exec(select(DnsBackup).order_by(DnsBackup.id.desc())).first()
       print("backup:", b.domain if b else None, b.created_at if b else None)
       for e in s.exec(select(AuditEvent).where(AuditEvent.action.like("step_%")).order_by(AuditEvent.id.desc()).limit(8)):
           print(e.action, e.result, e.target)
   PY
   ```

**✔ Check:** the GoDaddy DNS page shows `A meerasbakes → <VPS_IP>` and **nothing else changed** (compare with step 0).

## 11. Real HTTPS + the `lw-shop` marker

The first visit to `https://meerasbakes.launchwitness.com` makes Caddy ask `/internal/tls-ask` (yes: a live, real,
unpaused shop) and fetch a certificate; the checker waits for it.

```bash
curl -sS https://meerasbakes.launchwitness.com/ | grep -o '<meta name="lw-shop"[^>]*>'
curl -s -o /dev/null -w '%{http_code}\n' https://meerasbakes.launchwitness.com/api/health      # 404 (shop host)
echo | openssl s_client -connect meerasbakes.launchwitness.com:443 -servername meerasbakes.launchwitness.com 2>/dev/null | openssl x509 -noout -issuer -enddate
```

**✔ Check:** the marker prints, `/api/health` is 404 on the shop host, the issuer is Let's Encrypt (not staging).

## 12. Outside-in test order + IMAP proof + the authoritative answer, recorded

Press **Run checks now** on the shop's report (as hello@). The checker posts a real order through the **public** form over
the internet (`SafeWeb`, SSRF-guarded), the order email goes out through hello@, and because the shop's owner *is*
hello@, the checker finds it over IMAP.

**✔ Check** on the report (and on a shared link, `Share` → open it logged out):
- "Your address leads to your website": the hop names the zone's own nameserver (`ns##.domaincontrol.com (ip)`), not
  "pretend nameserver". That's the authoritative answer, stored as Evidence.
- "Opens securely": status 200, certificate end date, the marker found.
- "A test order reached your inbox": hops **Form accepted → Mail server accepted → In the inbox**, with times, server
  `imap.secureserver.net`.
- Nothing says "Practice".

Then one **real seller** shop (a separate account with her own email): she taps **"Yes, I got it"** in the test-order
email. The hop becomes "Owner confirmed", the only delivery proof for an inbox we can't read.

## 13. Afterwards

- Update `docs/PROGRESS.md` + `docs/STATE_FOR_NEXT_SESSION.md` with what was proven, then the transcript (`CLAUDE.md`).
- The jobs run on their own: `monitor_tick` every minute (each live shop: address + padlock every 15 minutes, the full
  check with one test order once a day, at its own minute), `outbox_send` every 20 s, team renewals, watched addresses,
  zone hygiene (the team page lists anything that doesn't match), guest clean-up hourly, backups at 03:15 (cron).
- Email budget: one test order per live shop per day goes through hello@. `SMTP_DAILY_LIMIT=450` (GoDaddy's limit is
  500/day per mailbox). At 40 shops that's ~40 a day plus sign-ins and orders: far below. The team page's **Email outbox**
  card shows sent today / the limit, anything retrying and anything dead (counts and error kinds only).

---

## Rollback (any step)

1. **App misbehaving:** `lwc down` (Caddy and the app stop; the database stays on the volume).
2. **Bad data:** `bash scripts/restore_db.sh backups/daily/<file>.db` (it saves a copy of the current database first,
   then restores and compares row counts).
3. **A shop record:** the shop's owner deletes the shop (its page → Delete): the app removes its A record through the
   guarded client. (Pausing on the team page only hides the shop; the record stays.) By hand: godaddy.com → DNS →
   delete `A <shop>`. Any leftover shows up on the team page under "Address records" the next day (or press "Check now").
4. **Everything:** set `A @` back to the value from step 0; `lwc down`.

## If GoDaddy's API refuses us (401/403 on DNS: some accounts may not use the API)

1. godaddy.com → launchwitness.com → DNS → add **A `*`** → `<VPS_IP>`, TTL 600 (this replaces "Don't add `*`" in step 6).
2. In `.env` set `DNS_MODE=wildcard`, then `lwc up -d --wait`. The app now reads and writes nothing at GoDaddy for shops.
   (Step 10's "first real write" doesn't happen; check instead that `dig +short meerasbakes.launchwitness.com @ns55.domaincontrol.com`
   answers `<VPS_IP>` before you launch.) Keep Let's Encrypt on staging (step 5) until a shop name resolves on both nameservers.
3. Each shop is still proven: every nameserver must answer `<VPS_IP>` for its name, then the padlock and the shop's own marker over HTTPS.
4. Certificates stay safe: `/internal/tls-ask` says yes only for live, unpaused shops, so `anything.launchwitness.com` gets none.
5. Weaker than per-shop records: a deleted shop's name still reaches our server (it shows "not found"), and "Address records" on the team page only checks that `*` is right; fixes there are by hand.

## If Let's Encrypt refuses

- `too many certificates` / `rateLimited` in `lwc logs caddy`: stop retrying. Switch to staging
  (`ACME_CA=…staging… lwc up -d`) to keep testing, and wait (the weekly limit resets on a rolling 7 days; failed
  validations after an hour). The app caps live shops at `MAX_LIVE_SHOPS=40` for this reason.
- `NXDOMAIN` / timeout during validation: DNS hasn't spread (step 6), or port 80/443 is closed (`sudo ufw status`,
  the VPS provider's own firewall).
- A shop gets no certificate: `/internal/tls-ask` says no unless the shop is live, real and unpaused. Check with
  `lwc exec -T caddy wget -qO- "http://app:8000/internal/tls-ask?domain=<shop>.launchwitness.com"`.
  It also says no while any nameserver doesn't answer `<VPS_IP>` for the shop (so no failed attempt is spent).

## If email misbehaves

- **Sign-in says "We're having trouble sending email"**: the first try failed; the outbox keeps trying for the link's
  life. Look at the team page → **Email outbox** (error kinds, e.g. `login refused` = wrong `SMTP_PASSWORD`,
  `unreachable` = port 465 blocked: the app also tries 587). `lwc logs app | grep -i "could not send"`.
- **An order shows "Email to you: retrying"**: it's saved; the email goes when the mail server answers. "failed" =
  gave up after ~2 h (the order is still on the Orders page).
- **Gmail puts our mail in spam**: check the mailbox's own SPF/DKIM at GoDaddy (Email & Office → DNS settings) but
  **don't edit MX/TXT by hand today**; note it in PROGRESS. (The sign-in page has no "check your spam folder" hint
  yet: if Gmail files us as spam, adding one is a small follow-up.)
- `/api/health` as the admin shows `outbox_dead` when anything gave up in the last day.

---

## The production `.env` checklist (names and what to put; **no values here**)

Fill in on the server only (`nano .env`, mode 600). "default" = leave the `.env.example` value.

| Variable | What to put |
|---|---|
| `APP_DOMAIN` | `launchwitness.com` |
| `APP_BASE_URL` | `https://launchwitness.com` |
| `APP_ORIGIN` | empty (taken from `APP_BASE_URL`) |
| `ADMIN_EMAIL` | the owner's address for the team page (signs in by email link) |
| `DEV_MODE` | `false` (the app refuses `true` on https) |
| `SESSION_DAYS` | default (14) |
| `SIGNIN_LINKS_PER_EMAIL_PER_DAY` / `SIGNIN_LINKS_PER_IP_PER_HOUR` | default (5 / 10) |
| `MAX_SHOPS_PER_USER` / `USER_DESCRIBES_PER_DAY` | default (3 / 5) |
| `MAX_LIVE_SHOPS` | default (40: the certificate limit) |
| `SHOP_REPORTS_PER_VISITOR_PER_DAY`, `ADDRESS_CHECKS_PER_HOUR`, `ADDRESS_CHECKS_PER_DAY` | defaults |
| `MAILBOX_EXPIRES_ON` | the hello@ plan's end date, `YYYY-MM-DD` (from GoDaddy; about 2026-12-15) |
| `ADMIN_TOKEN` | a fresh random one, 16+ characters (`openssl rand -base64 32`); never a local one |
| `SERVER_IP` | `<VPS_IP>` |
| `USE_FAKES` | `false` |
| `DNS_MODE` | `per_shop` (`wildcard` only per the section above) |
| `PRACTICE_STEP_SECONDS` | `0` |
| `VISITOR_DESCRIBES_PER_DAY`, `VISITOR_LAUNCHES_PER_DAY`, `ORDERS_PER_VISITOR_PER_HOUR`, `ORDERS_PER_SHOP_PER_DAY`, `VISITOR_CONTACTS_PER_DAY` | defaults |
| `MONITOR_ENABLED` | `true` (the prod compose forces it anyway) |
| `MONITOR_WORKERS` | default (4) |
| `ANTHROPIC_API_KEY` | the owner's key |
| `CLAUDE_MODE` | `live` |
| `CLAUDE_MODEL_STRONG` / `CLAUDE_MODEL_CHEAP` / `CLAUDE_MAX_TOKENS` | defaults |
| `CLAUDE_DAILY_SPEND_CAP_USD` | `2` (whole budget $100; at the cap, calls stop for the day and real launches are held) |
| `GODADDY_ENV` | `prod` |
| `GODADDY_API_KEY` / `GODADDY_API_SECRET` | the production key + secret (developer.godaddy.com) |
| `GODADDY_OTE_API_KEY` / `GODADDY_OTE_API_SECRET` | empty (not used with `prod`) |
| `ALLOW_PURCHASE` | `false`. **Never change.** |
| `MAX_SPEND_USD` / `EMAIL_PLAN_ESTIMATE_USD` | defaults (15 / 23.88) |
| `MAIL_PROVIDER` | `secureserver` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_SECURITY` | `smtpout.secureserver.net` / `465` / `ssl` |
| `SMTP_USER` | `hello@launchwitness.com` |
| `SMTP_PASSWORD` | the mailbox password |
| `SMTP_DAILY_LIMIT` | `450` |
| `IMAP_HOST` / `IMAP_PORT` | `imap.secureserver.net` / `993` |
| `IMAP_USER` | `hello@launchwitness.com` |
| `IMAP_PASSWORD` | the same mailbox password |
| `DATABASE_URL` | default (`sqlite:///./data/launchwitness.db`, on the `app-data` volume) |
| `CADDYFILE` | default: ignored by the prod compose (it always mounts `Caddyfile.prod`) |
| `ACME_CA` | **not in `.env`**: set it only on the command line for the staging start (step 5) |

**✔ Check:** `grep -c . .env` is about 50 lines; `grep -E '^(USE_FAKES|DEV_MODE|ALLOW_PURCHASE)=' .env` shows `false`
three times; `lwc logs app | grep 'self-check \['` prints nothing.

## Smoke test after deploy (10 lines, in order)

1. **Sign in** at `https://launchwitness.com/#/signin` with a real **Gmail** address: the link arrives (check the inbox
   **and the spam folder**; note which), it opens the app, you're signed in.
2. **Team page** (`#/admin`, as `ADMIN_EMAIL`): approve that account; the **Email outbox** card shows sent today ≥ 1, nothing dead.
3. **Launch the demo shop for real** (step 10: the go-live checklist, both confirmations, the two ticks, preview).
4. The shop opens over **https** with a padlock on a phone: `https://<shop>.launchwitness.com` (Let's Encrypt, not staging).
5. Place a **test order** as a customer from the phone: it shows on the Orders page with "Email to you: sent".
6. The order email arrives in the owner's inbox; press **"Yes, I got it"** in the test-order email → the hop says "Owner confirmed".
7. **Share** the report → open the link logged out → **Verify** says the receipt is intact.
8. Landing → **Check any address** with `gmail.com` and with the shop's address: both answer in plain words.
9. `bash scripts/backup_db.sh` makes a file in `backups/daily/`, and `crontab -l` shows the 03:15 line.
10. `EXTERNAL_SUBJECT=... bash scripts/check_m1.sh` → `Stack check: all checks passed.` (one `monitor_tick`, one `outbox_send`).
