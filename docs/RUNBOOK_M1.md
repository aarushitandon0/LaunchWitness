# RUNBOOK — M1: put LaunchWitness live on the GoDaddy VPS

Copy-paste steps, in order. Each step ends with **✔ Check**: don't go on until it passes.
Commands marked `(laptop)` run on your computer, `(vps)` on the server.
Replace `<APP_DOMAIN>` (e.g. `launchwitness.in`) and `<VPS_IP>` everywhere.

Rules that still apply (CLAUDE.md): secrets live **only** in the server's `.env`; purchases are made by you on godaddy.com with the hackathon credit; never paste a password into chat, a commit or a file other than `.env`.

> **About `gddy`:** the exact `gddy` sub-commands below are marked *confirm with `gddy tree`*. They were written without access to your CLI version. Run `gddy tree` (or `gddy <command> --help`) first and adjust. Each step also has a REST API or godaddy.com fallback that does the same thing.

---

## 0. Buy (you, on godaddy.com, with the hackathon credit)

1. Docker VPS (4 vCPU / 8 GB), Ubuntu 24.04 if offered.
2. The app domain `<APP_DOMAIN>`.
3. One Titan **Pro Light** mailbox on `<APP_DOMAIN>` (you'll name it `hello@<APP_DOMAIN>` in step 8).
   Note the real yearly price for `EMAIL_PLAN_ESTIMATE_USD` (currently a $24 placeholder).

**✔ Check:** all three show in your GoDaddy account (*My Products*). Write down the VPS IP shown in the VPS dashboard as `<VPS_IP>`.

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
adduser --disabled-password --gecos "" lw && usermod -aG sudo lw
mkdir -p /home/lw/.ssh && cp ~/.ssh/authorized_keys /home/lw/.ssh/ && chown -R lw:lw /home/lw/.ssh
echo 'lw ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/lw
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable
# from now on: ssh -i ~/.ssh/launchwitness lw@<VPS_IP>
```

**✔ Check:** `ssh -i ~/.ssh/launchwitness lw@<VPS_IP> 'whoami && sudo ufw status'` prints `lw` and shows 22/80/443 allowed.

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

## 4. Point DNS at the VPS (A record + wildcard)

Two A records on `<APP_DOMAIN>`: `@` → `<VPS_IP>` (the app) and `*` → `<VPS_IP>` (free seller addresses like `meera.<APP_DOMAIN>`).

With `gddy` (*confirm with `gddy tree`*; the shape is "add/replace a DNS record"):

```bash
gddy tree | grep -i -A3 dns                         # find the record command
gddy dns records set <APP_DOMAIN> A @ <VPS_IP>     # confirm syntax
gddy dns records set <APP_DOMAIN> A '*' <VPS_IP>   # confirm syntax
```

Same thing with the GoDaddy REST API (production keys from developer.godaddy.com; keep them in your shell only):

```bash
read -rs GD_KEY && read -rs GD_SECRET              # type them, nothing is echoed
for name in @ '*'; do
  curl -sS -X PUT "https://api.godaddy.com/v1/domains/<APP_DOMAIN>/records/A/$name" \
    -H "Authorization: sso-key $GD_KEY:$GD_SECRET" -H 'Content-Type: application/json' \
    -d '[{"data":"<VPS_IP>","ttl":600}]' && echo " set A $name"
done
unset GD_KEY GD_SECRET
```

Fallback: godaddy.com → *Domain* → *DNS* → *Add record* → Type **A**, Name `@`, Value `<VPS_IP>`; again with Name `*`.

**✔ Check (wait up to an hour):**
`dig +short <APP_DOMAIN> @ns01.domaincontrol.com` and `dig +short test123.<APP_DOMAIN> @ns01.domaincontrol.com` both print `<VPS_IP>` (use the NS names your zone shows: `dig +short NS <APP_DOMAIN>`).

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
| `SMTP_HOST` / `SMTP_PORT` | `smtpout.secureserver.net` / `465` | GoDaddy Titan settings |
| `SMTP_USER` | `hello@<APP_DOMAIN>` (full address) | step 8 |
| `SMTP_PASSWORD` | the mailbox password | the one you set in step 8 (or the email GoDaddy sends the account owner) |
| `IMAP_HOST` / `IMAP_PORT` | `imap.secureserver.net` / `993` | GoDaddy Titan settings |
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
( crontab -l 2>/dev/null; echo '15 3 * * * cd ~/LaunchWitness && bash scripts/backup_db.sh >> backups/backup.log 2>&1' ) | crontab -
```

**✔ Check:** `ls -l backups/` shows `launchwitness-<time>.db` (mode `-rw-------`). Restore, if ever needed: `bash scripts/backup_db.sh --restore backups/launchwitness-<time>.db`.

## 8. Create the mailbox `hello@<APP_DOMAIN>`

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

**✔ Check:** you can log in at the Titan webmail with `hello@<APP_DOMAIN>`, and `dig +short MX <APP_DOMAIN>` shows the Titan mail servers.

## 9. Test email + run the M1 check

1. From another account (e.g. your personal email) send a mail to `hello@<APP_DOMAIN>` with subject `M1 external test`.
2. On the VPS:

```bash
EXTERNAL_SUBJECT="M1 external test" bash scripts/check_m1.sh
```

It checks HTTPS (valid certificate), DNS for the app domain and the wildcard, `/internal/*` blocked, SMTP + IMAP login, your external email, a contact-form message arriving in the inbox, and that the SMTP password is in no tracked file or commit.

**✔ Check:** the last line says `M1: all checks passed.` Also tick the four M1 AC boxes in `docs/BUILD_PLAN.md` / `docs/PROGRESS.md`.

## 10. Real launches for admin-created businesses (practice mode off)

Public visitors' businesses are **always practice**, whatever you set here. `USE_FAKES=false` only makes **admin-created** businesses use real GoDaddy/DNS/email. Do it **after** the integration rows below (otherwise a real launch stops with "isn't switched on yet").

1. Finish rows 6 → 2 → 3 → 7 → 5 → 9 of the table below (enough for a real **free-address (sandbox)** launch).
2. In `.env`: `USE_FAKES=false` (keep `GODADDY_ENV=ote` until you have tested on the app domain, then `prod`). `lwc up -d`.
3. In your browser: `https://<APP_DOMAIN>/#/admin` → paste `ADMIN_TOKEN`. Businesses you now create are real; the yellow "Practice mode" banner disappears for you only.
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
