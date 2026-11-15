# e2e: browser flows (Playwright)

```bash
cd e2e && npm install && npx playwright install chromium
npx playwright test                                   # against the Docker stack: https://launchwitness.localhost
LW_BASE=http://localhost:8000 LW_MAIL= npx playwright test   # against the dev server (DEV_MODE=true shows links)
```

- **Docker stack** (default): start it first (`deploy/README.md`). Sign-in links are read from Mailpit
  (http://localhost:8025). The browser accepts Caddy's local CA **only for `.localhost`**.
- **Dev server**: run uvicorn with the environment shown in `docs/STATE_FOR_NEXT_SESSION.md` (fixture Claude, fakes,
  a scratch database, SMTP pointed at a closed port, `DEV_MODE=true`, `APP_DOMAIN=localhost`).
- Flows: (a) sign-up → pending → team approves → describe → practice launch → real launch (pretend GoDaddy) → a
  customer order on the shop's own host → report → share link opened logged out; (b) two sellers can't reach each
  other's shop, preview, orders, export, names, plans, report or share by URL; (c) guest practice is kept after signing
  in; (d) Privacy and Terms are one click from sign-in.
- Not covered here: the owner tapping "Yes, I got it". On a practice server the test-order email goes to the
  pretend inbox (in server memory), so there's no link to tap; pytest covers that path
  (`test_s9_phase3_proof.py::test_accepted_is_not_delivered_until_the_owner_taps`), and on the VPS it's a manual step.
- API calls are made by the page itself (`fetch` with the browser's cookies and CSRF token), like the real frontend;
  Node can't resolve `*.localhost` on Windows.
