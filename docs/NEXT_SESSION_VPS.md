# VPS day (Wed 18 Nov 2026, IST): put LaunchWitness on the internet, then prove one real shop

Written so a model (or a person) can do it **cold**. You need nothing else open except `CLAUDE.md`. Steps are in
order; each ends with **✔ Check**, and you don't go on until it passes. `(laptop)` = the owner's computer, `(vps)` = the
server. Replace `<VPS_IP>` everywhere. The app domain is `launchwitness.com`.

**Ground rules (from CLAUDE.md):** never print, paste or commit a secret, and the owner types every secret into the
server's `.env` herself. No purchases (`ALLOW_PURCHASE=false`, always). The only DNS records made by hand are `A @`
(and optionally `www`); the app writes each shop's own A record. **No wildcard.** Don't touch MX / TXT / CNAME: they carry
the mailbox `hello@launchwitness.com`.

What's already proven on the laptop (S10, `deploy/README.md`): the image builds from a clean clone, runs as non-root
with one process, HTTPS through Caddy, `__Host-` cookies, `/internal` blocked, the shop-host guard, rate limits on the
real client IP, a restart and a kill mid-launch, backup + restore, and the 4 browser flows. **Not proven until today:**
real Let's Encrypt certificates, a real GoDaddy DNS write, the authoritative DNS answer, an outside-in test order over the
internet, and an IMAP delivery proof.

---

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

The owner types the values; nobody else sees them. Production values:

| Variable | Value |
|---|---|
| `APP_DOMAIN` | `launchwitness.com` |
| `APP_BASE_URL` | `https://launchwitness.com` |
| `APP_ORIGIN` | empty (taken from `APP_BASE_URL`) |
| `DEV_MODE` | `false` (the app refuses to start with `true` on https) |
| `USE_FAKES` | `false`: real GoDaddy, DNS, mailbox, web checks |
| `SERVER_IP` | `<VPS_IP>` |
| `ADMIN_EMAIL` | the owner's address for the team page (she signs in with it by email link) |
| `ADMIN_TOKEN` | a fresh one: `openssl rand -base64 32` (command line only; never reuse a local one) |
| `CLAUDE_MODE` | `live` (with `fixture` every real launch is held for team review: safe but manual) |
| `ANTHROPIC_API_KEY` | the owner's key |
| `CLAUDE_DAILY_SPEND_CAP_USD` | `2` (the whole budget is $100; the cap stops calls for the day, and the policy check then holds launches) |
| `CLAUDE_MODEL_STRONG` / `CLAUDE_MODEL_CHEAP` | defaults |
| `GODADDY_ENV` | `prod` (launchwitness.com is in the production account) |
| `GODADDY_API_KEY` / `GODADDY_API_SECRET` | production key + secret (developer.godaddy.com) |
| `ALLOW_PURCHASE` | `false`. **Never change.** |
| `MAX_SPEND_USD` | `15` (unchanged) |
| `MAILBOX_EXPIRES_ON` | the hello@ plan's end date from GoDaddy (about `2026-12-15`); health warns 14 days ahead, the team gets 30/7/1-day emails |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_SECURITY` | `smtpout.secureserver.net` / `465` / `ssl` |
| `SMTP_USER` / `SMTP_PASSWORD` | `hello@launchwitness.com` / its password |
| `IMAP_HOST` / `IMAP_PORT` | `imap.secureserver.net` / `993` |
| `IMAP_USER` / `IMAP_PASSWORD` | `hello@launchwitness.com` / the same password |
| `MONITOR_ENABLED` | `true` (forced by the prod compose anyway) |
| `PRACTICE_STEP_SECONDS` | `0` |
| everything else | the `.env.example` defaults |

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
and run `lwc up -d`.

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
   address `meerasbakes` → Launch → **for real**. With `CLAUDE_MODE=live` the policy check runs (one cheap call).
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
- The daily jobs run on their own: monitoring (one test order per live shop per day through hello@: **check GoDaddy's
  send limit**), team renewals, zone hygiene (the team page lists anything that doesn't match), backups at 03:15.

---

## Rollback (any step)

1. **App misbehaving:** `lwc down` (Caddy and the app stop; the database stays on the volume).
2. **Bad data:** `bash scripts/restore_db.sh backups/daily/<file>.db` (it saves a copy of the current database first,
   then restores and compares row counts).
3. **A shop record:** the shop's owner deletes the shop (its page → Delete): the app removes its A record through the
   guarded client. (Pausing on the team page only hides the shop; the record stays.) By hand: godaddy.com → DNS →
   delete `A <shop>`. Any leftover shows up on the team page under "Address records" the next day (or press "Check now").
4. **Everything:** set `A @` back to the value from step 0; `lwc down`.

## If Let's Encrypt refuses

- `too many certificates` / `rateLimited` in `lwc logs caddy`: stop retrying. Switch to staging
  (`ACME_CA=…staging… lwc up -d`) to keep testing, and wait (the weekly limit resets on a rolling 7 days; failed
  validations after an hour). The app caps live shops at `MAX_LIVE_SHOPS=40` for this reason.
- `NXDOMAIN` / timeout during validation: DNS hasn't spread (step 6), or port 80/443 is closed (`sudo ufw status`,
  the VPS provider's own firewall).
- A shop gets no certificate: `/internal/tls-ask` says no unless the shop is live, real and unpaused. Check with
  `lwc exec -T caddy wget -qO- "http://app:8000/internal/tls-ask?domain=<shop>.launchwitness.com"`.
