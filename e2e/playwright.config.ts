import { defineConfig } from "@playwright/test";

// LW_BASE: the app's URL. Default: the production-like Docker stack (deploy/README.md).
//   Dev server instead: LW_BASE=http://localhost:8000 (uvicorn with DEV_MODE=true, APP_DOMAIN=localhost).
// LW_MAIL: Mailpit's URL when the app really sends email (Docker stack). Empty = DEV_MODE shows the link.
const base = process.env.LW_BASE || "https://launchwitness.localhost";

export default defineConfig({
  testDir: "./tests",
  timeout: 300_000,
  workers: 1, // one app process, one SQLite writer: run the flows one after another
  reporter: [["list"]],
  use: {
    // LW_CHROME: a pre-installed Chromium to use instead of the one this Playwright version downloads.
    launchOptions: process.env.LW_CHROME ? { executablePath: process.env.LW_CHROME } : {},
    baseURL: base,
    // ONLY for the local stack: Caddy's own local CA isn't in the system trust store. Never against the VPS.
    ignoreHTTPSErrors: base.includes(".localhost"),
    trace: "retain-on-failure",
  },
});
