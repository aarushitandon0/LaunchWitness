import base from "./playwright.config";
import { defineConfig } from "@playwright/test";

// Screenshots for the docs (not a test suite): `npx playwright test -c screens.config.ts` → LW_SHOTS (default
// ../docs/screenshots/latest). Same base URL rules as playwright.config.ts.
export default defineConfig({ ...base, testDir: "./screens" });
