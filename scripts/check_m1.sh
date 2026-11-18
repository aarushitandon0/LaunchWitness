#!/usr/bin/env bash
# Stack acceptance check. Two places, same checks:
#
#   bash scripts/check_m1.sh            # ON THE VPS, from the repo, stack running (reads .env, never prints secrets)
#   bash scripts/check_m1.sh --local    # this computer: the production-like Docker stack (deploy/README.md)
#   EXTERNAL_SUBJECT="hello from my gmail" bash scripts/check_m1.sh   # VPS: also look for your external test email
#
# Checks: DNS (VPS: `A @` and each live shop's own A record; there is NO wildcard), HTTPS + certificate + HSTS +
# http->https, /api/health and its warnings (mailbox expiry), /internal/* blocked from outside on every host but
# working inside the network, the shop-host guard, the session cookie's flags over https, the ADMIN_EMAIL user,
# exactly one app process, the mailbox (SMTP/IMAP; local: Mailpit), a contact-form message arriving, and that
# the SMTP password is in no tracked file or commit. Exit code = number of failures.

export MSYS_NO_PATHCONV=1  # Git Bash on Windows: never rewrite container paths like /app/...
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
cd "$REPO"
FAILS=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }
info() { printf '        %s\n' "$1"; }

LOCAL=false
[ "${1:-}" = "--local" ] && LOCAL=true
# A temp file whose path both bash and native Windows tools (docker.exe, curl.exe) read the same way.
tmpf() { local f; f="$(mktemp)"; cygpath -m "$f" 2>/dev/null || echo "$f"; }

# Read one value from .env without printing it (no `source`: values may contain spaces/symbols).
envval() { grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e 's/[[:space:]]*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }

if $LOCAL; then
  COMPOSE=(docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml)
  APP_DOMAIN=launchwitness.localhost
  SERVER_IP=127.0.0.1
  CA="$(tmpf)"
  "${COMPOSE[@]}" cp caddy:/data/caddy/pki/authorities/local/root.crt "$CA" >/dev/null 2>&1 \
    || { echo "FAIL: can't read Caddy's local CA (is the local stack up? see deploy/README.md)"; exit 1; }
  CURL=(curl -sS --max-time 20 --cacert "$CA")
  curl --version | grep -qi schannel && CURL+=(--ssl-no-revoke)  # Windows curl: no revocation list for a local CA
else
  [ -f .env ] || { echo "FAIL: no .env in $REPO (see docs/NEXT_SESSION_VPS.md)"; exit 1; }
  COMPOSE=(docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml)
  APP_DOMAIN="$(envval APP_DOMAIN)"
  SERVER_IP="$(envval SERVER_IP)"
  CURL=(curl -sS --max-time 20)
  # STAGING_OK=1: Caddy is still on Let's Encrypt STAGING (docs/NEXT_SESSION_VPS.md step 5). Accept that
  # certificate ONLY after checking that the one served for the app domain really is a staging one for that
  # name; everything else is checked as usual. Never set this once the real CA is in use.
  if [ "${STAGING_OK:-}" = 1 ]; then
    stg="$(echo | openssl s_client -connect "$APP_DOMAIN:443" -servername "$APP_DOMAIN" 2>/dev/null \
      | openssl x509 -noout -issuer -subject 2>/dev/null)"
    # OpenSSL 3.0 prints "O = Let's Encrypt, CN = (STAGING) ...", 3.2+ prints "O=Let's Encrypt, CN=(STAGING) ...".
    if echo "$stg" | grep -q "O *= *Let's Encrypt, CN *= *(STAGING)" && echo "$stg" | grep -q "CN *= *$APP_DOMAIN\$"; then
      echo "WARN: STAGING_OK=1: accepting the Let's Encrypt STAGING certificate for $APP_DOMAIN (not trusted by browsers)"
      CURL+=(-k)
    else
      echo "FAIL: STAGING_OK=1 but $APP_DOMAIN doesn't serve a Let's Encrypt staging certificate for itself"; exit 1
    fi
  fi
fi
BASE="https://$APP_DOMAIN"
echo "Stack check for $BASE (server $SERVER_IP)$($LOCAL && echo ', LOCAL stack')"

if [ -z "$("${COMPOSE[@]}" ps -q app 2>/dev/null)" ]; then
  fail "the app container isn't running"; echo "$FAILS failure(s)"; exit "$FAILS"
fi
inapp() { "${COMPOSE[@]}" exec -T app python - "$@"; }

# ---------- 1. DNS ----------
echo "1. Addresses (DNS)"
if $LOCAL; then
  info "(local: *.localhost always means this computer; skipped)"
elif [ -z "$APP_DOMAIN" ] || [ "$APP_DOMAIN" = "localhost" ]; then
  fail "APP_DOMAIN is not set to your real domain in .env"
else
  ip="$(getent ahostsv4 "$APP_DOMAIN" | awk 'NR==1{print $1}')"
  [ -n "$ip" ] && [ "$ip" = "$SERVER_IP" ] && pass "DNS: $APP_DOMAIN -> $ip" \
    || fail "DNS: $APP_DOMAIN -> ${ip:-nothing} (want $SERVER_IP; DNS can take up to an hour)"
  if command -v dig >/dev/null; then
    ns="$(dig +short NS "$APP_DOMAIN" | head -n1)"
    auth="$(dig +short A "$APP_DOMAIN" @"${ns:-ns01.domaincontrol.com}" | head -n1)"
    [ "$auth" = "$SERVER_IP" ] && pass "authoritative answer from ${ns%?}: $auth" || fail "authoritative answer from ${ns:-?}: ${auth:-nothing}"
  fi
fi
SHOPS="$(inapp <<'PY' 2>/dev/null
from sqlmodel import Session, select
from app.db import get_engine
from app.models import Business
with Session(get_engine()) as s:
    for b in s.exec(select(Business).where(Business.status == "live", Business.practice == False, Business.paused == False)).all():  # noqa: E712
        if b.subdomain:
            print(b.subdomain)
PY
)"
SHOP="$(echo "$SHOPS" | head -n1 | tr -d '\r')"
info "live real shops: $(echo "$SHOPS" | grep -c . || true)"
if ! $LOCAL; then
  for s in $SHOPS; do
    ip="$(getent ahostsv4 "$s.$APP_DOMAIN" | awk 'NR==1{print $1}')"
    [ "$ip" = "$SERVER_IP" ] && pass "DNS: $s.$APP_DOMAIN -> $ip (its own A record)" || fail "DNS: $s.$APP_DOMAIN -> ${ip:-nothing}"
  done
  nope="$(getent ahostsv4 "lw-no-such-shop-$RANDOM.$APP_DOMAIN" | awk 'NR==1{print $1}')"
  [ -z "$nope" ] && pass "no wildcard: an unused name doesn't resolve" || warn "an unused name resolves to $nope (a wildcard record exists? we decided per-shop records only)"
fi

# ---------- 2. HTTPS ----------
echo "2. Website over HTTPS"
if body="$("${CURL[@]}" "$BASE/api/health" 2>&1)" && echo "$body" | grep -q '"ok":true'; then
  pass "$BASE/api/health with a valid certificate"
  echo "$body" | grep -q '"warnings"' && warn "health warnings: $(echo "$body" | sed -e 's/.*"warnings":\[//' -e 's/\].*//')" \
    || pass "health: no warnings"
else
  fail "$BASE/api/health: ${body:0:200}"
fi
hsts="$("${CURL[@]}" -o /dev/null -D - "$BASE/" 2>/dev/null | tr -d '\r' | grep -i '^strict-transport-security:')"
[ -n "$hsts" ] && pass "HSTS on the app ($hsts)" || fail "no Strict-Transport-Security header on $BASE"
redir="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 "http://$APP_DOMAIN/")"
case "$redir" in 30[178]\ https://*) pass "http -> https ($redir)";; *) fail "http://$APP_DOMAIN/ answered '$redir' (want a redirect to https)";; esac
if ! $LOCAL; then
  end="$(echo | openssl s_client -connect "$APP_DOMAIN:443" -servername "$APP_DOMAIN" 2>/dev/null | openssl x509 -noout -enddate -issuer 2>/dev/null | tr '\n' ' ')"
  [ -n "$end" ] && info "certificate: $end"
fi

# ---------- 3. /internal and the shop-host guard ----------
echo "3. Internal endpoints and shop hosts"
bad=""
for p in "/internal/tls-ask?domain=$APP_DOMAIN" "/internal" "/INTERNAL/tls-ask?domain=x" "/internal%2ftls-ask?domain=$APP_DOMAIN" "//internal/tls-ask?domain=$APP_DOMAIN"; do
  code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASE$p")"
  [ "$code" = "404" ] || bad="$bad $p=$code"
done
[ -z "$bad" ] && pass "/internal/* answers 404 from outside (5 spellings)" || fail "/internal reachable from outside:$bad"
inside="$("${COMPOSE[@]}" exec -T caddy wget -qO- "http://app:8000/internal/tls-ask?domain=$APP_DOMAIN" 2>&1)"
echo "$inside" | grep -q '"ok":true' && pass "inside the network Caddy's ask works for $APP_DOMAIN" || fail "tls-ask inside the network: ${inside:0:120}"
unknown="$("${COMPOSE[@]}" exec -T caddy wget -qO- "http://app:8000/internal/tls-ask?domain=lw-nobody.$APP_DOMAIN" 2>&1)"
echo "$unknown" | grep -q '404' && pass "no certificate for a shop that doesn't exist" || fail "tls-ask said yes to an unknown shop: ${unknown:0:120}"
if [ -n "$SHOP" ]; then
  SB="https://$SHOP.$APP_DOMAIN"
  page="$("${CURL[@]}" "$SB/" 2>&1)"
  echo "$page" | grep -q 'name="lw-shop"' && pass "$SB opens over HTTPS with its lw-shop marker" || fail "$SB: no lw-shop marker"
  bad=""
  for p in /api/health /internal/tls-ask /build /r/x /assets/x.js; do
    code="$("${CURL[@]}" -o /dev/null -w '%{http_code}' "$SB$p")"; [ "$code" = "404" ] || bad="$bad $p=$code"
  done
  [ -z "$bad" ] && pass "shop host serves no app paths (/api /internal /build /r /assets: 404)" || fail "shop host answered:$bad"
else
  info "(no live real shop yet: shop-host checks skipped)"
fi

# ---------- 4. Accounts: session cookie over https, the admin user ----------
echo "4. Accounts"
admin="$(inapp <<'PY' 2>&1
from sqlmodel import Session, select
from app.config import get_settings
from app.db import get_engine
from app.models import User
s = get_settings()
with Session(get_engine()) as db:
    u = db.exec(select(User).where(User.email == s.admin_email.strip().lower())).first() if s.admin_email else None
    print("ADMIN", "unset" if not s.admin_email else ("ok" if u and u.role == "admin" and u.status == "approved" else "missing"))
    print("DEVMODE", s.dev_mode)
    print("MAILBOX", s.mailbox_expires_on or "unset")
from app.selfcheck import warnings
for w in warnings(s):
    print("SELFCHECK", w.code, w.text)
PY
)"
case "$(echo "$admin" | awk '/^ADMIN/{print $2}')" in
  ok) pass "the ADMIN_EMAIL user exists, approved, role admin";;
  unset) fail "ADMIN_EMAIL is not set";;
  *) fail "the ADMIN_EMAIL user is missing or not admin";;
esac
sc="$(echo "$admin" | grep '^SELFCHECK' | cut -d' ' -f2-)"
if [ -z "$sc" ]; then pass "startup self-check: nothing wrong"
else while IFS= read -r line; do warn "self-check: $line"; done <<<"$sc"; fi
[ "$(echo "$admin" | awk '/^DEVMODE/{print $2}')" = "False" ] && pass "DEV_MODE is off" || fail "DEV_MODE is on"
mb="$(echo "$admin" | awk '/^MAILBOX/{print $2}')"
if [ "$mb" = "unset" ]; then $LOCAL && info "MAILBOX_EXPIRES_ON unset (fine locally)" || fail "MAILBOX_EXPIRES_ON is not set (health can't warn before hello@ lapses)"
else pass "MAILBOX_EXPIRES_ON = $mb (health warns 14 days ahead)"; fi
# A one-time sign-in token for the admin, made inside the app and used once over https, then signed out.
# Nothing is emailed. The token never reaches the screen.
TOKEN="$(inapp <<'PY' 2>/dev/null
from sqlmodel import Session
from app.accounts import issue_token
from app.config import get_settings
from app.db import get_engine
s = get_settings()
if s.admin_email:
    with Session(get_engine()) as db:
        print(issue_token(db, s.admin_email.strip().lower(), "login", visitor="check_m1"))
PY
)"
TOKEN="$(echo "$TOKEN" | tail -n1 | tr -d '\r')"
if [ -n "$TOKEN" ]; then
  hdrs="$(tmpf)"
  resp="$("${CURL[@]}" -D "$hdrs" -H 'Content-Type: application/json' -H "Origin: $BASE" \
    --data-binary @- "$BASE/api/auth/confirm" <<<"{\"token\":\"$TOKEN\"}")"
  unset TOKEN
  cookie="$(tr -d '\r' < "$hdrs" | grep -i '^set-cookie: __Host-lw_session=' | head -n1)"
  flags="$(echo "$cookie" | sed -E 's/^set-cookie: __Host-lw_session=[^;]*//I')"  # the value is never shown
  okc=true
  for f in "secure" "httponly" "samesite=lax" "path=/"; do echo "$flags" | grep -qi "$f" || okc=false; done
  echo "$flags" | grep -qi "domain=" && okc=false
  $okc && pass "__Host-lw_session over https:$flags" || fail "session cookie flags wrong or missing:${flags:-(no __Host-lw_session cookie)}"
  raw="$(echo "$cookie" | sed -E 's/^set-cookie: __Host-lw_session=([^;]*).*/\1/I')"
  csrf="$(echo "$resp" | sed -n 's/.*"csrf":"\([^"]*\)".*/\1/p')"
  out="$("${CURL[@]}" -o /dev/null -w '%{http_code}' -X POST -H "Origin: $BASE" -H "X-CSRF-Token: $csrf" \
    -H "Cookie: __Host-lw_session=$raw" "$BASE/api/auth/logout")"
  unset raw csrf
  [ "$out" = "200" ] && info "(that check session was signed out again)" || warn "couldn't sign the check session out ($out)"
  # Its one-time token mustn't count against the admin's daily sign-in links.
  inapp <<'PY' >/dev/null 2>&1
from sqlmodel import Session, delete
from app.db import get_engine
from app.models import LoginToken
with Session(get_engine()) as db:
    db.exec(delete(LoginToken).where(LoginToken.visitor == "check_m1"))
    db.commit()
PY
  rm -f "$hdrs"
fi

# ---------- 5. One app process ----------
echo "5. One app process"
procs="$(inapp <<'PY' 2>&1
import os
n = 0
for p in os.listdir("/proc"):
    if p.isdigit():
        try:
            c = open(f"/proc/{p}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        n += any(x.endswith(b"uvicorn") for x in c[:2]) and b"app.main:app" in c
print(n)
PY
)"
[ "$(echo "$procs" | tail -n1 | tr -d '\r')" = "1" ] && pass "exactly one uvicorn process" || fail "uvicorn processes: $procs (must be 1)"
nlog="$("${COMPOSE[@]}" logs app 2>&1 | grep -c 'monitor started' || true)"
info "scheduler starts logged since the container was created: $nlog (one per start)"
# S13: one monitor beat a minute + one outbox sender, never two of either (the last start's job list).
jobs="$("${COMPOSE[@]}" logs app 2>&1 | grep 'monitor started' | tail -n1 | sed -n 's/.*jobs=//p')"
nt="$(printf '%s' "$jobs" | grep -o "'monitor_tick'" | wc -l | tr -d ' ')"
no="$(printf '%s' "$jobs" | grep -o "'outbox_send'" | wc -l | tr -d ' ')"
if [ "$nt" = "1" ] && [ "$no" = "1" ]; then pass "scheduler: one monitor_tick, one outbox_send"
else fail "scheduler jobs at the last start: monitor_tick x$nt, outbox_send x$no (each must be 1): $jobs"; fi
rec="$("${COMPOSE[@]}" logs app 2>&1 | grep 'startup reconcile' | tail -n1 | sed -n 's/.*startup reconcile: //p')"
[ -n "$rec" ] && info "startup reconcile (rows put back after a stop): $rec"

# ---------- 6. Mailbox + contact form ----------
echo "6. Mailbox and contact form"
MARK="m1check-$(date +%s)-$RANDOM"
if $LOCAL; then
  "${COMPOSE[@]}" exec -T app python -c "import smtplib,os; smtplib.SMTP(os.environ['SMTP_HOST'], int(os.environ['SMTP_PORT']), timeout=10).quit()" \
    && pass "SMTP reaches the local catch-all (Mailpit)" || fail "SMTP to Mailpit"
else
  out="$(inapp "${EXTERNAL_SUBJECT:-}" <<'PY' 2>&1
import imaplib, os, smtplib, ssl, sys
user = os.environ.get("SMTP_USER", "")
ctx = ssl.create_default_context()
try:
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtpout.secureserver.net"), int(os.environ.get("SMTP_PORT", 465)), context=ctx, timeout=20) as s:
        s.login(user, os.environ.get("SMTP_PASSWORD", ""))
    print("SMTP_OK", user)
except Exception as e:
    print("SMTP_FAIL", type(e).__name__)
try:
    m = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST", "imap.secureserver.net"), int(os.environ.get("IMAP_PORT", 993)), ssl_context=ctx)
    m.login(os.environ.get("IMAP_USER", ""), os.environ.get("IMAP_PASSWORD", ""))
    m.select("INBOX", readonly=True)
    print("IMAP_OK")
    subj = sys.argv[1] if len(sys.argv) > 1 else ""
    if subj:
        typ, data = m.search(None, "SUBJECT", '"%s"' % subj.replace('"', ""))
        print("EXTERNAL_FOUND" if data and data[0].split() else "EXTERNAL_MISSING")
    m.logout()
except Exception as e:
    print("IMAP_FAIL", type(e).__name__)
PY
)"
  echo "$out" | grep -q '^SMTP_OK' && pass "SMTP login as $(echo "$out" | awk '/^SMTP_OK/{print $2}')" || fail "SMTP login: $(echo "$out" | grep '^SMTP_FAIL' | cut -d' ' -f2-)"
  echo "$out" | grep -q '^IMAP_OK' && pass "IMAP login (inbox readable)" || fail "IMAP login: $(echo "$out" | grep '^IMAP_FAIL' | cut -d' ' -f2-)"
  if [ -n "${EXTERNAL_SUBJECT:-}" ]; then
    echo "$out" | grep -q '^EXTERNAL_FOUND' && pass "external test email \"$EXTERNAL_SUBJECT\" is in the inbox" || fail "external test email not found"
  else
    info "(manual) send an email from another account, then re-run with EXTERNAL_SUBJECT=\"<its subject>\""
  fi
fi
resp="$("${CURL[@]}" -H 'Content-Type: application/json' -H "Origin: $BASE" \
  -d "{\"name\":\"Stack check\",\"email\":\"m1-check@example.org\",\"message\":\"Automatic stack check $MARK\"}" "$BASE/api/contact" 2>&1)"
if echo "$resp" | grep -q '"ok":true'; then
  pass "contact form accepted the message"
  if $LOCAL; then
    found=""
    for _ in $(seq 1 10); do
      curl -s "http://localhost:8025/api/v1/search?query=$MARK" | grep -q '"total":[1-9]' && { found=1; break; }; sleep 1
    done
    [ -n "$found" ] && pass "contact message arrived (Mailpit)" || fail "contact message not in Mailpit"
  else
    found="$(inapp "$MARK" <<'PY' 2>&1
import imaplib, os, ssl, sys, time
mark = sys.argv[1]
for _ in range(12):
    try:
        m = imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST", "imap.secureserver.net"), int(os.environ.get("IMAP_PORT", 993)), ssl_context=ssl.create_default_context())
        m.login(os.environ.get("IMAP_USER", ""), os.environ.get("IMAP_PASSWORD", ""))
        m.select("INBOX", readonly=True)
        typ, data = m.search(None, "BODY", '"%s"' % mark)
        m.logout()
        if data and data[0].split():
            print("FOUND"); sys.exit(0)
    except Exception as e:
        print("ERR", type(e).__name__)
    time.sleep(10)
print("MISSING")
PY
)"
    echo "$found" | grep -q '^FOUND' && pass "contact message arrived in the mailbox (IMAP)" || fail "contact message not in the inbox after 2 minutes"
  fi
elif echo "$resp" | grep -q 'several messages today'; then
  warn "contact form: this address's daily limit is used up (the limit works; delivery not re-checked today)"
else
  fail "contact form: ${resp:0:200}"
fi

# ---------- 7. Secrets ----------
echo "7. Secrets"
git ls-files --error-unmatch .env >/dev/null 2>&1 && fail ".env is tracked by git!" || pass ".env is not tracked by git"
if ! $LOCAL; then
  mode="$(stat -c '%a' .env 2>/dev/null)"
  [ "$mode" = "600" ] && pass ".env is chmod 600" || fail ".env mode is ${mode:-?} (chmod 600 .env)"
  PW="$(envval SMTP_PASSWORD)"
  if [ -z "$PW" ]; then
    fail "SMTP_PASSWORD is empty in .env"
  else
    # -f <(...) keeps the password off every command line (ps can't see it).
    git grep -qF -f <(printf '%s\n' "$PW") -- . 2>/dev/null && fail "SMTP password found in a tracked file" || pass "SMTP password not in any tracked file"
    git log -p --all 2>/dev/null | grep -qF -f <(printf '%s\n' "$PW") && fail "SMTP password found in git history" || pass "SMTP password not in any commit"
  fi
  unset PW
fi
docker image inspect "$("${COMPOSE[@]}" images -q app 2>/dev/null | head -n1)" >/dev/null 2>&1 && \
  { "${COMPOSE[@]}" exec -T app sh -c 'test ! -e /app/.env && test ! -e /app/backend/.env' && pass "no .env inside the image" || fail ".env found inside the app image"; }

$LOCAL && rm -f "$CA"
echo
if [ "$FAILS" -eq 0 ]; then echo "Stack check: all checks passed."; else echo "Stack check: $FAILS check(s) failed."; fi
exit "$FAILS"
