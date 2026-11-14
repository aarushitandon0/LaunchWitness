#!/usr/bin/env bash
# M1 acceptance check. Run ON THE VPS, from the repo, with the stack running:
#
#   bash scripts/check_m1.sh
#   EXTERNAL_SUBJECT="hello from my gmail" bash scripts/check_m1.sh   # also look for your external test email
#
# Prints PASS / FAIL for each M1 criterion (docs/BUILD_PLAN.md):
#   1. https://<APP_DOMAIN> loads with a valid certificate (+ DNS: app domain and wildcard point here)
#   2. the mailbox is reachable (SMTP + IMAP login with the .env password, inside the app container)
#      and, if EXTERNAL_SUBJECT is set, the external test email is in the inbox
#   3. a contact-form submission arrives in the mailbox (found over IMAP by a unique marker)
#   4. the SMTP password is only in the server .env: not tracked, not in any file or commit
# Secrets are never printed. Exit code = number of failures.

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
FAILS=0
pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAILS=$((FAILS + 1)); }
info() { printf '        %s\n' "$1"; }

# Read one value from .env without printing it (no `source`: values may contain spaces/symbols).
envval() { grep -E "^$1=" .env 2>/dev/null | tail -n1 | cut -d= -f2- | sed -e 's/[[:space:]]#.*$//' -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"; }

if [ ! -f .env ]; then
  echo "FAIL: no .env in $REPO (see docs/RUNBOOK_M1.md step 5)"; exit 1
fi
APP_DOMAIN="$(envval APP_DOMAIN)"
SERVER_IP="$(envval SERVER_IP)"
COMPOSE=(docker compose --env-file .env -f deploy/docker-compose.yml -f deploy/docker-compose.prod.yml)
echo "M1 check for https://$APP_DOMAIN (server $SERVER_IP)"

# ---------- 1. HTTPS + DNS ----------
echo "1. Website over HTTPS"
if [ -z "$APP_DOMAIN" ] || [ "$APP_DOMAIN" = "localhost" ]; then
  fail "APP_DOMAIN is not set to your real domain in .env"
else
  for host in "$APP_DOMAIN" "m1-check-$RANDOM.$APP_DOMAIN"; do
    ip="$(getent ahostsv4 "$host" | awk 'NR==1{print $1}')"
    label="$host"; [ "$host" != "$APP_DOMAIN" ] && label="wildcard *.$APP_DOMAIN"
    if [ -n "$ip" ] && [ "$ip" = "$SERVER_IP" ]; then pass "DNS: $label -> $ip"
    else fail "DNS: $label -> ${ip:-nothing} (want $SERVER_IP; DNS can take up to an hour)"; fi
  done
  if body="$(curl -sS --max-time 15 "https://$APP_DOMAIN/api/health" 2>&1)" && echo "$body" | grep -q '"ok":true'; then
    pass "https://$APP_DOMAIN loads with a valid certificate"
    end="$(echo | openssl s_client -connect "$APP_DOMAIN:443" -servername "$APP_DOMAIN" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)"
    [ -n "$end" ] && info "certificate valid until $end"
  else
    fail "https://$APP_DOMAIN/api/health: ${body:0:200}"
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "https://$APP_DOMAIN/internal/tls-ask?domain=x")"
  [ "$code" = "404" ] && pass "/internal/* is not reachable from outside" || fail "/internal/* answered $code (want 404)"
fi

# Run Python inside the app container (it has the .env values; nothing is printed but results).
inapp() { "${COMPOSE[@]}" exec -T app python - "$@"; }

if [ -z "$("${COMPOSE[@]}" ps -q app 2>/dev/null)" ]; then
  fail "the app container isn't running (docker compose ... up -d)"; echo "$FAILS failure(s)"; exit "$FAILS"
fi

# ---------- 2. Mailbox reachable ----------
echo "2. Mailbox"
out="$(inapp "${EXTERNAL_SUBJECT:-}" <<'PY' 2>&1
import imaplib, os, smtplib, ssl, sys
user = os.environ.get("SMTP_USER", "")
ctx = ssl.create_default_context()
try:
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtpout.secureserver.net"), int(os.environ.get("SMTP_PORT", 465)), context=ctx, timeout=20) as s:
        s.login(user, os.environ.get("SMTP_PASSWORD", ""))
    print("SMTP_OK", user)
except Exception as e:
    print("SMTP_FAIL", type(e).__name__, str(e)[:120].replace(os.environ.get("SMTP_PASSWORD", "") or "\0", "***"))
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
    print("IMAP_FAIL", type(e).__name__, str(e)[:120])
PY
)"
echo "$out" | grep -q '^SMTP_OK' && pass "SMTP login as $(echo "$out" | awk '/^SMTP_OK/{print $2}') (smtpout.secureserver.net:465)" \
  || fail "SMTP login: $(echo "$out" | grep '^SMTP_FAIL' | cut -d' ' -f2-)"
echo "$out" | grep -q '^IMAP_OK' && pass "IMAP login (inbox readable)" || fail "IMAP login: $(echo "$out" | grep '^IMAP_FAIL' | cut -d' ' -f2-)"
if [ -n "${EXTERNAL_SUBJECT:-}" ]; then
  echo "$out" | grep -q '^EXTERNAL_FOUND' && pass "external test email \"$EXTERNAL_SUBJECT\" is in the inbox" \
    || fail "external test email \"$EXTERNAL_SUBJECT\" not found in the inbox"
else
  info "(manual) send an email from another account, then re-run with EXTERNAL_SUBJECT=\"<its subject>\""
fi

# ---------- 3. Contact form arrives ----------
echo "3. Contact form"
MARK="m1check-$(date +%s)-$RANDOM"
resp="$(curl -sS --max-time 20 -H 'Content-Type: application/json' \
  -d "{\"name\":\"M1 check\",\"email\":\"m1-check@example.org\",\"message\":\"Automatic M1 check $MARK\"}" \
  "https://$APP_DOMAIN/api/contact" 2>&1)"
if echo "$resp" | grep -q '"ok":true'; then
  pass "contact form accepted the message"
  found="$(inapp "$MARK" <<'PY' 2>&1
import imaplib, os, ssl, sys, time
mark = sys.argv[1]
for _ in range(12):  # up to ~2 minutes
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
  echo "$found" | grep -q '^FOUND' && pass "contact form message arrived in the mailbox" \
    || fail "contact form message not in the inbox after 2 minutes ($(echo "$found" | tail -n1))"
else
  fail "contact form: ${resp:0:200}"
fi

# ---------- 4. Password only in server .env ----------
echo "4. Secrets"
git ls-files --error-unmatch .env >/dev/null 2>&1 && fail ".env is tracked by git!" || pass ".env is not tracked by git"
PW="$(envval SMTP_PASSWORD)"
if [ -z "$PW" ]; then
  fail "SMTP_PASSWORD is empty in .env"
else
  # -f <(...) keeps the password off every command line (ps can't see it).
  if git grep -qF -f <(printf '%s\n' "$PW") -- . 2>/dev/null; then fail "SMTP password found in a tracked file (git grep)"
  else pass "git grep: SMTP password not in any tracked file"; fi
  if git log -p --all 2>/dev/null | grep -qF -f <(printf '%s\n' "$PW"); then fail "SMTP password found in git history"
  else pass "SMTP password not in any commit"; fi
fi
unset PW

echo
if [ "$FAILS" -eq 0 ]; then echo "M1: all checks passed."; else echo "M1: $FAILS check(s) failed."; fi
exit "$FAILS"
