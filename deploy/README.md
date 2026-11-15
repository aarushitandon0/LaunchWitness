# deploy/

| File | What |
|---|---|
| `Dockerfile` | One image: React build baked in, FastAPI + seller sites, `/build` replay page. Runs as `lw` (uid 10001), **one uvicorn worker**, healthcheck on `/api/health`. No dev dependencies (`requirements.txt` only). |
| `docker-compose.yml` | Base: `app` (port 8000 **not published**) + `caddy` (the only service with ports: 80/443). Volumes: `app-data` (SQLite), `caddy-data` (certificates). |
| `docker-compose.prod.yml` | On top of the base, on the VPS: `Caddyfile.prod`, monitoring on, `restart: unless-stopped`, healthchecks, capped logs. |
| `docker-compose.local.yml` | On top of base + prod, on your computer: the **production-like local stack** (below). |
| `Caddyfile.prod` | HTTPS for the app (HSTS), on-demand TLS for shops (`ask` → `/internal/tls-ask`), `/internal/*` → 404 on every host, 8 MB body limit, timeouts. Used both on the VPS and locally. |
| `Caddyfile` | Quick plain-http mode (`docker compose -f deploy/docker-compose.yml up`): signing in needs `DEV_MODE=true` there. |

There's no uploads volume because nothing uploaded is stored. Price-list photos are read in memory and sent to the
Reader (`routers/businesses.py`). The state is the SQLite file on `app-data` plus Caddy's certificates on `caddy-data`.
`.env` lives only on the server (`chmod 600`). It's excluded from the image by `.dockerignore`, and the local
stack doesn't read it.

## The production-like local stack

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml up -d --build --wait
bash scripts/check_m1.sh --local          # the same checks as on the VPS
cd e2e && npm install && npx playwright install chromium && npx playwright test   # browser flows over https
```

- App: https://launchwitness.localhost · shops: `https://<slug>.launchwitness.localhost` (`*.localhost` is always
  this computer). Caddy issues certificates from its **own local CA** (`local_certs`), including on-demand ones for
  shops after `tls-ask` says yes. The browser tests accept that CA (`ignoreHTTPSErrors`, only for `.localhost`).
  `check_m1.sh --local` copies the CA's root out of the Caddy container and verifies against it.
- `DEV_MODE=false` (real `__Host-` cookies), `USE_FAKES=true` (pretend GoDaddy, DNS and inbox), `CLAUDE_MODE=fixture`.
- **Every email goes to Mailpit** (http://localhost:8025; sign-in links arrive there). `SMTP_SECURITY=plain` is
  allowed only for a one-word docker host such as `mailpit` (the settings refuse it for any real host name).
- It **never reads `../.env`** (`env_file: !reset []`), so no real key gets into a local container.
- Admin: sign in as `admin@launchwitness.localhost` (the link arrives in Mailpit).
- Restart drill: `PRACTICE_STEP_SECONDS=3 docker compose ... up -d`, then `scripts/restart_drill.py` (see its header)
  starts a practice launch you can kill with `docker compose ... kill -s KILL app`.
- Stop: `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml down`
  (add `-v` to forget the local database and CA).

## Rules that keep it safe (don't "improve" these)

- **One app container, one worker.** APScheduler runs in-process and SQLite has one writer. The app takes a lock
  next to the database at startup and refuses to start a second process (`app/singleton.py`), and it also refuses
  `WEB_CONCURRENCY` > 1. Never add `--workers`, never `--scale app=2`.
- **Only Caddy publishes ports.** The rate limits read the last `X-Forwarded-For` entry, which Caddy always sets
  to the real client and which a client can't forge (no `trusted_proxies`). If port 8000 were ever published,
  anyone could pick their own rate-limit identity.
- **`/internal/*` is closed twice:** Caddy answers 404 on every host, and the app itself answers only to private
  host names (`app:8000`, an IP, a one-word name), never to `launchwitness.com` or a shop.

## S10 audit of deploy/ against the code (2026-11-16 IST): what didn't match, and what was done

| # | Mismatch | Fix |
|---|---|---|
| 1 | The local Caddyfile is plain http, so `__Host-` cookies (`DEV_MODE=false`) can't work through Docker. The production cookie path couldn't be tested before the VPS. | `docker-compose.local.yml` runs `Caddyfile.prod` with Caddy's local CA. |
| 2 | Sign-in emails always go through real SMTP. A local `DEV_MODE=false` run would have used GoDaddy SMTP with the real password from `.env`. | Mailpit catch-all + `SMTP_SECURITY=plain` (one-word hosts only). |
| 3 | The base compose loads `../.env` into the container for local runs too, putting real secrets in a local container. | The local override resets `env_file`. |
| 4 | `Caddyfile.prod` had no HSTS, no timeouts, no body-size limit, and sent the `Server` header. `/internal` (no slash) wasn't matched. | Added all; the matcher is `/internal /internal/*`. |
| 5 | Nothing stopped `--workers 4` (4 copies of every alert and daily test order). | `--workers 1` pinned and commented, plus the startup lock and the `WEB_CONCURRENCY` check. |
| 6 | `--forwarded-allow-ips *` makes `request.client` the *leftmost* XFF entry. That's safe only because Caddy overwrites XFF and `visitor_id` reads the last entry. | Documented (Dockerfile + here). Proven: forged XFF doesn't dodge the limit. |
| 7 | `/internal/*` was blocked only by Caddy; the app answered it on any Host. | The request guard refuses `/internal` for any dotted host name. |
| 8 | `check_m1.sh` checked a **wildcard** record (dropped in S9F), had no cookie / shop-host / one-process / admin checks, and ran only on the VPS. | Rewritten. Same checks `--local` and on the VPS. |
| 9 | RUNBOOK step 4 said to add `*`; step 8 said Titan; step 10 said to paste `ADMIN_TOKEN` into `#/admin`. SPEC, BUILD_PLAN and PROGRESS also said wildcard. | Updated. The VPS steps are now `docs/NEXT_SESSION_VPS.md`. |
| 10 | `backup_db.sh` kept 14 copies with no weekly ones. Its restore copied over the live DB **without removing `-wal`/`-shm`** (an old WAL could be replayed into the restored file), and the restore was never tested. | Part B: online backup, 7 daily + 4 weekly, `restore_db.sh`, tested. |
| 11 | SQLite had no WAL, `busy_timeout` or `foreign_keys`. | Set on every connection. Turning on foreign keys exposed a real bug (the admin demo delete left proof rows behind); fixed. |
| 12 | The prod compose said `restart: always`. | `unless-stopped`. |
| 13 | The data directory was mode 755. | 700, owned by `lw`. |
| 14 | `HEAD /` answers 405 (FastAPI GET routes don't take HEAD). Browsers don't care; an uptime monitor that uses HEAD would. | **Not fixed**: point any monitor at `GET /api/health`. |
