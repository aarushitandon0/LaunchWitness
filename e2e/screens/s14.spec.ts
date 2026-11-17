// S14 screenshots: the Review page's look picker (live thumbnails, accent row, private preview) at 375 and 1440.
// Run: LW_BASE=http://localhost:8000 LW_MAIL= npx playwright test -c screens.config.ts s14   (default out: docs/screenshots/s14)
import { test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { ADMIN_EMAIL, describe, signIn } from "../tests/helpers";

const OUT = process.env.LW_SHOTS || path.join(__dirname, "..", "..", "docs", "screenshots", "s14");

test("S14 look picker", async ({ browser }) => {
  fs.mkdirSync(OUT, { recursive: true });
  for (const [w, h] of [[1440, 1000], [375, 812]] as [number, number][]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await signIn(page, ADMIN_EMAIL);
    const id = await describe(page);
    await page.goto(`/#/b/${id}`);
    const card = page.locator(".theme-card");
    await card.waitFor();
    await page.getByRole("radio", { name: /^Tailoring/ }).click();
    await page.frameLocator("iframe.theme-preview").locator("body.theme-tailor").waitFor();
    await page.getByRole("radio", { name: "Red thread", exact: true }).click();
    await page.waitForTimeout(800);
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({ path: path.join(OUT, `review-picker-${w}.png`) });
    await ctx.close();
  }
});
