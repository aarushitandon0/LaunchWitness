// S10.5b screenshots: the hero scene at 1917x791, 1440 and 375 (real GPU), the monitoring section, the open Product
// menu (desktop + phone), Check any address with a result, and a short recording of the hero loop.
// Run: npx playwright test -c screens.config.ts s105b   (Windows laptop: uses the GPU through ANGLE/D3D11)
import { expect, test, type Browser, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const OUT = process.env.LW_SHOTS || path.join(__dirname, "..", "..", "docs", "screenshots", "s10-5b");
test.use({ launchOptions: { args: ["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist"] } });

async function page(browser: Browser, w: number, h: number): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ignoreHTTPSErrors: true });
  return ctx.newPage();
}

test("S10.5b screens", async ({ browser }) => {
  test.setTimeout(240_000);
  fs.mkdirSync(OUT, { recursive: true });
  for (const [w, h] of [[1917, 791], [1440, 900], [375, 812]]) {
    const p = await page(browser, w, h);
    await p.goto("/");
    await p.waitForTimeout(5200); // the scene loads after first paint; let the light climb most of the way
    await p.screenshot({ path: path.join(OUT, `01-hero-${w}.png`) });
    await p.context().close();
  }
  for (const [w, h] of [[1440, 900], [375, 812]]) {
    const p = await page(browser, w, h);
    await p.goto("/#watch");
    await p.waitForTimeout(1500);
    await p.locator("#watch").screenshot({ path: path.join(OUT, `02-keep-watching-${w}.png`) });
    await p.goto("/");
    await p.getByRole("button", { name: /Product/ }).filter({ visible: true }).first().click();
    await expect(p.getByRole("region", { name: "Product" }).filter({ visible: true })).toBeVisible();
    await p.waitForTimeout(400);
    await p.screenshot({ path: path.join(OUT, `03-product-menu-${w}.png`) });
    await p.keyboard.press("Escape");
    await p.goto("/#check");
    await p.getByLabel("Web address").fill("example.com");
    await p.getByRole("button", { name: "Check it" }).click();
    await expect(p.getByText(/Read-only results for/)).toBeVisible({ timeout: 30_000 });
    await p.locator("#check").screenshot({ path: path.join(OUT, `04-check-any-address-${w}.png`) });
    await p.context().close();
  }
  // a short recording of one loop (≈ 11 s) at a modest size
  const ctx = await browser.newContext({
    viewport: { width: 960, height: 600 }, ignoreHTTPSErrors: true, recordVideo: { dir: OUT, size: { width: 960, height: 600 } },
  });
  const p = await ctx.newPage();
  await p.goto("/");
  await p.waitForTimeout(11_500);
  const video = p.video()!;
  await ctx.close();
  fs.renameSync(await video.path(), path.join(OUT, "05-hero-loop.webm"));
});
