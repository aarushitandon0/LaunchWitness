// S16: every theme in production settings. Each look is launched for real (practice world) on its own shop host, opened
// over https through Caddy: no CSP violation, no blocked font or request, no console error, the hidden lw-shop marker is
// there, and one real order goes through the form. Screenshots at 375 and 1440 go to LW_SHOTS (when set).
import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

const THEMES = ["bakery", "kitchen", "handmade", "tailor", "gifts", "general"];
const SHOTS = process.env.LW_SHOTS || "";

function watch(page: Page): string[] {
  const bad: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || /Content Security Policy|Refused to/i.test(m.text())) bad.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => bad.push(`pageerror: ${e.message}`));
  page.on("requestfailed", (r) => bad.push(`failed: ${r.url()} ${r.failure()?.errorText}`));
  page.on("response", (r) => { if (r.status() >= 400) bad.push(`http ${r.status()}: ${r.url()}`); });
  return bad;
}

for (const theme of THEMES) {
  test(`the ${theme} look in production settings: clean console, marker, fonts, one real order`, async ({ page, browser }) => {
    test.setTimeout(300_000);
    await signIn(page, ADMIN_EMAIL);
    const id = await describe(page);
    const slug = unique(`t${theme.slice(0, 3)}`);
    await setAddress(page, id, slug);
    await readyForReal(page, id);
    const t = await api(page, "PUT", `/api/businesses/${id}/theme`, { theme, accent: "" });
    expect(t.status(), await t.text()).toBe(200);
    await launch(page, id, true);

    const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost") });
    const shop = await ctx.newPage();
    const bad = watch(shop);
    // CSP violations also reach the page as events: count them from inside too.
    await shop.addInitScript(() => {
      (window as unknown as { __csp: string[] }).__csp = [];
      document.addEventListener("securitypolicyviolation", (e) =>
        (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
    });
    for (const width of [1440, 375]) {
      await shop.setViewportSize({ width, height: width === 375 ? 800 : 900 });
      const r = await shop.goto(shopUrl(slug));
      expect(r!.status()).toBe(200);
      expect(r!.headers()["content-security-policy"] || "", "a CSP header is sent").toContain("script-src");
      await expect(shop.locator("body")).toHaveClass(new RegExp(`theme-${theme}`));
      await expect(shop.locator('meta[name="lw-shop"]')).toHaveAttribute("content", /.+/);
      await shop.evaluate(() => document.fonts.ready);
      const fonts = await shop.evaluate(() => [...document.fonts].map((f) => `${f.family}:${f.status}`));
      expect(fonts.some((f) => f.endsWith(":loaded")), fonts.join(", ")).toBe(true);
      expect(fonts.filter((f) => f.endsWith(":error")), "no font failed").toEqual([]);
      const overflow = await shop.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, "no sideways scroll").toBeLessThanOrEqual(0);
      if (SHOTS) {
        fs.mkdirSync(SHOTS, { recursive: true });
        await shop.screenshot({ path: path.join(SHOTS, `${theme}-${width}.png`), fullPage: true });
      }
    }

    // One real order through the form (at phone width).
    await shop.locator(".item .add").first().click();
    await shop.locator("#customer_name").fill(`Riya ${theme}`);
    await shop.locator("#customer_phone").fill("98765 43210");
    await pickDate(shop);
    const pickup = shop.locator('input[name="fulfilment"][value="pickup"]');
    if (await pickup.count()) await pickup.check();
    await shop.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
    await shop.waitForLoadState("load");
    await expect(shop.getByRole("heading", { name: new RegExp(`Thank you, Riya ${theme}`) })).toBeVisible();
    const csp = await shop.evaluate(() => (window as unknown as { __csp: string[] }).__csp);
    expect(csp, "no CSP violations").toEqual([]);
    expect(bad, "no console errors, failed or blocked requests").toEqual([]);
    await ctx.close();

    const orders = await (await api(page, "GET", `/api/businesses/${id}/orders`)).json();
    expect(orders.filter((o: { customer_name: string }) => o.customer_name === `Riya ${theme}`).length).toBe(1);
  });
}
