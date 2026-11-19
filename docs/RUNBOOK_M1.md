# RUNBOOK — M1: put LaunchWitness live on the GoDaddy VPS

Copy-paste steps, in order. Each step ends with **✔ Check**: don't go on until it passes.
Commands marked `(laptop)` run on your computer, `(vps)` on the server.
Replace `<APP_DOMAIN>` (= `launchwitness.com`) and `<VPS_IP>` everywhere.

Rules that still apply (CLAUDE.md): secrets live **only** in the server's `.env`; purchases are made by you on godaddy.com with the hackathon credit; never paste a password into chat, a commit or a file other than `.env`.

> **S10 (2026-11-16): for Wednesday's deploy follow `docs/NEXT_SESSION_VPS.md` first; it supersedes the order below.** The
> decisions since this runbook was written: **no wildcard record** (each live shop gets its own A record, written by the app
> through the guarded client), admin = whoever signs in as `ADMIN_EMAIL`, and the stack check is `bash scripts/check_m1.sh`.

> **About `gddy`:** the exact `gddy` sub-commands below are marked *confirm with `gddy tree`*. They were written without access to your CLI version. Run `gddy tree` (or `gddy <command> --help`) first and adjust. Each step also has a REST API or godaddy.com fallback that does the same thing.

---

## 0. Purchases — done (Nov 15)

Already in the GoDaddy account. **Buy nothing else**: $2.37 credit left (expires Nov 23), no card on file.

| Item | Status |
|---|---|
| App domain `launchwitness.com` | Bought, 1 year (renews Nov 2027 at $22.99). `launchwitness.in` was NOT bought. |
| Mailbox `hello@launchwitness.com` | Bought: GoDaddy Professional Email **Pro Light** (secureserver.net backend, not Titan), **1 month**. $5.99/mo monthly; $23.88/yr on a 1-yr term (`EMAIL_PLAN_ESTIMATE_USD=23.88`). **Expires ~Dec 15; auto-renew will lapse** (no card). |
| Mail DNS | Set by GoDaddy: MX `smtp.secureserver.net` / `mailstore1.secureserver.net`, SPF `include:secureserver.net -all`, DKIM ×2, DMARC `p=quarantine`. Leave them alone. |
| Docker VPS | **Free, arrives Wed Nov 18. Do NOT buy one.** |
| Demo seller domain | Not bought. The demo shop is `meerasbakes.launchwitness.com`: its own A record, written by the app at launch (no wildcard). |

`A @` still points at GoDaddy's parked WebsiteBuilder page. Don't change any DNS until the VPS exists (step 6).

**✔ Check:** `python scripts/list_godaddy_domains.py` lists `launchwitness.com` as ACTIVE (read-only, uses the prod keys in `.env`, never prints them). When the VPS arrives, write down its IP as `<VPS_IP>`.

## 1. SSH key and first connection

```bash
# (laptop) make a key just for this server (press Enter for no passphrase, or set one)
ssh-keygen -t ed25519 -f ~/.ssh/launchwitness -C "launchwitness-vps"
cat ~/.ssh/launchwitness.pub        # paste this public key into the VPS dashboard (SSH keys)
```

If the dashboard instead gives you a root password, add the key once with:
`ssh-copy-id -i ~/.ssh/launchwitness.pub root@<VPS_IP>`.

```bash
# (laptop) connect
ssh -i ~/.ssh/launchwitness root@<VPS_IP>
```

Optional but recommended (vps): a non-root user and a firewall.

```bash
adduser --disabled-password --gecos "" lwadmin && usermod -aG sudo lwadmin
mkdir -p /home/lwadmin/.ssh && cp ~/.ssh/authorized_keys /home/lwadmin/.ssh/ && chown -R lwadmin:lwadmin /home/lwadmin/.ssh
echo 'lwadmin ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/lwadmin
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
# from now on: ssh -i ~/.ssh/launchwitness lwadmin@<VPS_IP>
```

**✔ Check:** `ssh -i ~/.ssh/launchwitness lwadmin@<VPS_IP> 'whoami && sudo ufw status'` prints `lwadmin` and shows 22/80/443 allowed.

## 2. Install Docker

```bash
# (vps)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER" && newgrp docker
```

**✔ Check:** `docker run --rm hello-world` prints "Hello from Docker!" and `docker compose version` prints v2.x.

## 3. Clone the repo

```bash
# (vps)
sudo apt-get install -y git
git clone https://github.com/aarushitandon0/LaunchWitness.git ~/LaunchWitness
cd ~/LaunchWitness && git log --oneline -1
```

(Private repo? Create a read-only **deploy key**: `ssh-keygen -t ed25519 -f ~/.ssh/gh_deploy` on the VPS, add the `.pub` under GitHub → repo → Settings → Deploy keys, then clone with `git@github.com:aarushitandon0/LaunchWitness.git` and `GIT_SSH_COMMAND='ssh -i ~/.ssh/gh_deploy'`.)

**✔ Check:** `ls ~/LaunchWitness/deploy` shows `Dockerfile docker-compose.yml docker-compose.prod.yml Caddyfile Caddyfile.prod`.

## 4. Point DNS at the VPS (ONE hand-made A record, no wildcard)

Only `@` → `<VPS_IP>` is made by hand (plus `www` → `<VPS_IP>` if you want it). **Do not add a `*` wildcard**: each live
shop gets its own A record, written by the app at launch through the guarded GoDaddy client (shop A records only),
and removed when the shop is taken down. The daily zone-hygiene job flags anything else.

Fallback (the simplest): godaddy.com → *Domain* → *DNS* → edit the existing **A `@`** record (it points at the
parked page today) → Value `<VPS_IP>`, TTL 600. Leave MX / TXT / CNAME records alone (they carry the mailbox).

**✔ Check (wait up to an hour):** `dig +short <APP_DOMAIN> @ns01.domaincontrol.com` prints `<VPS_IP>` (use the NS
names your zone shows: `dig +short NS <APP_DOMAIN>`), and `dig +short test123.<APP_DOMAIN>` prints **nothing**.

## 5. Create `.env` on the server only

```bash
# (vps)
cd ~/LaunchWitness && cp .env.example .env && chmod 600 .env && nano .env
```

Fill in (leave anything not listed at its default):

| Variable | Value | Where it comes from |
|---|---|---|
| `APP_DOMAIN` | `<APP_DOMAIN>` | the domain you bought |
| `APP_BASE_URL` | `https://<APP_DOMAIN>` | — |
| `ADMIN_TOKEN` | 32+ random chars | `openssl rand -base64 32` on the VPS (admin is **off** while it's `change-me` or < 16 chars) |
| `SERVER_IP` | `<VPS_IP>` | VPS dashboard |
| `USE_FAKES` | `true` for now | step 10 explains when to set `false` |
| `VISITOR_DESCRIBES_PER_DAY` / `VISITOR_LAUNCHES_PER_DAY` / `VISITOR_CONTACTS_PER_DAY` | `5` / `3` / `5` | defaults; judges' limits |
| `MONITOR_ENABLED` | `true` | (forced on by `docker-compose.prod.yml` anyway) |
| `ANTHROPIC_API_KEY` | your key, or empty | console.anthropic.com → API keys (only when you decide to go live) |
| `CLAUDE_MODE` | `fixture` (→ `live` later) | keep `fixture` until the key exists and you approve live calls |
| `CLAUDE_MODEL_STRONG` / `CLAUDE_MODEL_CHEAP` | defaults | Reader / Namer + Doctor |
| `CLAUDE_MAX_TOKENS` / `CLAUDE_DAILY_SPEND_CAP_USD` | `1500` / `3` | budget guards |
| `GODADDY_ENV` | `ote` (→ `prod` only when you decide) | — |
| `GODADDY_API_KEY` / `GODADDY_API_SECRET` | production key + secret | developer.godaddy.com → API Keys → *Production* |
| `GODADDY_OTE_API_KEY` / `GODADDY_OTE_API_SECRET` | OTE key + secret | developer.godaddy.com → API Keys → *OTE* |
| `ALLOW_PURCHASE` | `false` | **never change** (you buy on godaddy.com) |
| `MAX_SPEND_USD` | `15` | **never raise casually** |
| `EMAIL_PLAN_ESTIMATE_USD` | real yearly Pro Light price | your GoDaddy cart (step 0) |
| `SMTP_HOST` / `SMTP_PORT` | `smtpout.secureserver.net` / `465` | GoDaddy Professional Email settings (587 STARTTLS is the automatic fallback) |
| `SMTP_USER` | `hello@<APP_DOMAIN>` (full address) | step 8 |
| `SMTP_PASSWORD` | the mailbox password | the one you set in step 8 (or the email GoDaddy sends the account owner) |
| `IMAP_HOST` / `IMAP_PORT` | `imap.secureserver.net` / `993` | GoDaddy Professional Email settings |
| `IMAP_USER` / `IMAP_PASSWORD` | same address and password as SMTP | step 8 |
| `DATABASE_URL` | default | SQLite on the `app-data` volume |
| `CADDYFILE` | `Caddyfile.prod` | (the prod compose file forces it anyway) |

**✔ Check:** `ls -l .env` shows `-rw-------`, and `git status --short` does **not** list `.env`.

## 6. Start the stack with HTTPS (Caddyfile.prod)

```bash
# (vps)
cd ~/LaunchWitness
docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build
docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml ps
```

(Tip: `alias lwc='docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml'` in `~/.bashrc`, then `lwc ps`, `lwc logs -f app`.)

**✔ Check:** `ps` shows `app` and `caddy` as **(healthy)**; from your laptop `curl -sS https://<APP_DOMAIN>/api/health` prints `{"ok":true,"env":"ote"}` without a certificate error; the landing page opens on your phone.
(If Caddy can't get a certificate: `lwc logs caddy | tail -50`; usually DNS from step 4 hasn't spread yet, or port 80/443 is closed.)

## 7. Nightly database backup

```bash
# (vps)
bash scripts/backup_db.sh                      # first backup now
( crontab -l 2>/dev/null; echo '15 3 * * * cd $HOME/LaunchWitness && bash scripts/backup_db.sh >> backups/backup.log 2>&1' ) | crontab -
```

**✔ Check:** `ls -l backups/daily/` shows `launchwitness-<time>.db` (mode `-rw-------`); 7 daily + 4 weekly are kept. Restore, if ever needed: `bash scripts/restore_db.sh backups/daily/launchwitness-<time>.db`.

## 8. Create the mailbox `hello@<APP_DOMAIN>`

> **Already done (Nov 15):** `hello@launchwitness.com` exists on GoDaddy Professional Email (secureserver.net) and its DNS records are set. Just copy the address + password into the VPS `.env` and restart; the check below uses GoDaddy webmail (email.secureserver.net), not Titan.

With `gddy` (*confirm with `gddy tree | grep -i -A5 email`*):

```bash
gddy email accounts list                                   # confirm syntax: shows the Pro Light plan
gddy email accounts create hello@<APP_DOMAIN>             # confirm syntax; set a strong password when asked
```

Fallback: godaddy.com → *Email & Office* → your Pro Light plan → *Set up account* → `hello@<APP_DOMAIN>`. Let GoDaddy add the email DNS records (MX / SPF / DKIM) to `<APP_DOMAIN>` when it offers to.
Put the address and password in `.env` (`SMTP_USER`, `SMTP_PASSWORD`, `IMAP_USER`, `IMAP_PASSWORD`), then restart the app:

```bash
lwc up -d
```

**✔ Check:** you can log in at GoDaddy webmail (email.secureserver.net) with `hello@<APP_DOMAIN>`, and `dig +short MX <APP_DOMAIN>` shows `smtp.secureserver.net` / `mailstore1.secureserver.net`.

## 9. Test email + run the M1 check

1. From another account (e.g. your personal email) send a mail to `hello@<APP_DOMAIN>` with subject `M1 external test`.
2. On the VPS:

```bash
EXTERNAL_SUBJECT="M1 external test" bash scripts/check_m1.sh
```

It checks HTTPS (valid certificate, HSTS), DNS for the app domain and each live shop (and that no wildcard exists), `/internal/*` blocked, the session cookie's flags, the ADMIN_EMAIL user, one app process, SMTP + IMAP login, your external email, a contact-form message arriving in the inbox, and that the SMTP password is in no tracked file or commit.

**✔ Check:** the last line says `M1: all checks passed.` Also tick the four M1 AC boxes in `docs/BUILD_PLAN.md` / `docs/PROGRESS.md`.

## 10. Real launches for admin-created businesses (practice mode off)

Public visitors' businesses are **always practice**, whatever you set here. `USE_FAKES=false` only makes **admin-created** businesses use real GoDaddy/DNS/email. Do it **after** the integration rows below (otherwise a real launch stops with "isn't switched on yet").

1. Finish rows 6 → 2 → 3 → 7 → 5 → 9 of the table below (enough for a real **free-address (sandbox)** launch).
2. In `.env`: `USE_FAKES=false` (keep `GODADDY_ENV=ote` until you have tested on the app domain, then `prod`). `lwc up -d`.
3. In your browser: sign in at `https://<APP_DOMAIN>/#/signin` with the `ADMIN_EMAIL` address (the team page is `#/admin`). Approved accounts can now launch for real.
4. Do a sandbox launch for Meera.

**✔ Check:** the launch report says "Your business is ready for customers", and `https://meera.<APP_DOMAIN>` opens with a padlock on your phone (M3 AC1).

## 11. Real integration TODO, in the order to do them

(Details for each row: `docs/PROGRESS.md` → "Real integration TODO".)

| Order | Row | What | Why this order |
|---|---|---|---|
| 1 | 10 | Server `.env` (done in step 5) | everything reads it |
| 2 | 15 | `ADMIN_TOKEN` (done in step 5) | real launches need admin |
| 3 | 16 | Fresh DB (nothing deployed before, so nothing to do) | — |
| 4 | 6 | Authoritative DNS lookups (`ns*.domaincontrol.com` IPs) | checks must not read caches |
| 5 | 2 | `is_owned` against the real account | guards every DNS write |
| 6 | 3 | Scoped DNS writes on the app domain in **OTE**, then **prod** | the sandbox launch writes `A <sub>` |
| 7 | 7 | HTTPS probe vs a bad certificate | launch check |
| 8 | 5 | Titan mailbox `find` (app mailbox), later `create`/`status`/`dkim` | sandbox needs `find`; full needs all |
| 9 | 9 | IMAP test-order arrival on the demo inbox | test-order check |
| 10 | 8 | Certificate retry (optional Caddy admin API) | repair |
| 11 | 12, 13 | Certificate end date, domain end date | report days left + warnings |
| 12 | 14 | Monitoring on the VPS (jobs fire, alert emails arrive) | after real checks work |
| 13 | 1 | Availability + price (method to choose) | needed for own-name launches |
| 14 | 4 | Purchase stays manual (leave as is) | — |
| 15 | 11 | Live Claude (`ANTHROPIC_API_KEY`, `CLAUDE_MODE=live`) | only with your OK per call |

**✔ Check (end of M1 + Fable session):** `bash scripts/check_m1.sh` all PASS; a real sandbox launch is green; then M4 AC5 (Meera's own domain, if credit allows).

## Everyday commands

```bash
lwc ps                     # status (healthy?)
lwc logs -f app            # app logs
git pull && lwc up -d --build   # deploy a new version
bash scripts/backup_db.sh  # backup now
python3 scripts/seed_demo.py --url https://<APP_DOMAIN> --launched   # rehearse the demo (practice)
export ADMIN_TOKEN="$(grep '^ADMIN_TOKEN=' .env | cut -d= -f2-)"   # read from .env, never typed on the command line
python3 scripts/seed_demo.py --url https://<APP_DOMAIN> --reset
```
