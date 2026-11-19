// S20 Part B: every shop has its own signature, and the page feels alive without breaking the safety layer.
// One launched shop is switched through all six themes x two motifs (keys saved by the owner's picker API). Each look:
// no CSP violation, no console error, no sideways scroll at 375 and 1440. Then basket fly + quick view + reduced motion
// + an order with JavaScript off. Screenshots (LW_SHOTS) at 390 and 1440.
import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

const MOTIFS: Record<string, string[]> = {
  bakery: ["sprinkles", "piping", "cherries"], kitchen: ["leaves", "spices", "steam"], handmade: ["threads", "dots", "brush"],
  tailor: ["stitches", "buttons", "chalk"], gifts: ["ribbons", "confetti", "stars"], general: ["waves", "grid", "sparks"],
};
const SHOTS = process.env.LW_SHOTS || "";

function watch(page: Page): string[] {
  const bad: string[] = [];
  // (a shop host answers /favicon.ico with 404: known since S19C, not part of this work)
  page.on("console", (m) => { if (m.location().url.endsWith("/favicon.ico")) return; if (m.type() === "error" || /Content Security Policy|Refused to/i.test(m.text())) bad.push(`console: ${m.text()}`); });
  page.on("pageerror", (e) => bad.push(`pageerror: ${e.message}`));
  page.on("requestfailed", (r) => bad.push(`failed: ${r.url()} ${r.failure()?.errorText}`));
  return bad;
}

test("six themes x two motifs, then basket, quick view, reduced motion and a JS-off order", async ({ page, browser }) => {
  test.setTimeout(600_000);
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique("s20b");
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const saved = await api(page, "PUT", `/api/businesses/${id}`, {
    profile: { ...biz.profile, selling_mode: "pickup", payment_terms: "on_delivery" }, subdomain: slug });
  expect(saved.status(), await saved.text()).toBe(200);
  await launch(page, id, true);

  const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost") });
  const shop = await ctx.newPage();
  const bad = watch(shop);
  await shop.addInitScript(() => {
    (window as unknown as { __csp: string[] }).__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => (window as unknown as { __csp: string[] }).__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
  });

  for (const [theme, motifs] of Object.entries(MOTIFS)) {
    for (const [n, motif] of motifs.slice(0, 2).entries()) {
      const t = await api(page, "PUT", `/api/businesses/${id}/theme`, { theme, accent: "" });
      expect(t.status(), await t.text()).toBe(200);
      const s = await api(page, "PUT", `/api/businesses/${id}/signature`, { motif, art: ["scatter", "corner", "band"][n === 0 ? 0 : 1] });
      expect(s.status(), await s.text()).toBe(200);
      for (const [width, height] of [[390, 844], [1440, 900]]) {
        await shop.setViewportSize({ width, height });
        const r = await shop.goto(shopUrl(slug));
        expect(r!.status()).toBe(200);
        await expect(shop.locator(".motif-wrap")).toHaveAttribute("data-motif", motif);
        await shop.evaluate(() => document.fonts.ready);
        expect(await shop.evaluate(() => document.documentElement.scrollWidth - window.innerWidth), `${theme}/${motif} sideways at ${width}`).toBeLessThanOrEqual(0);
        expect(await shop.evaluate(() => (window as unknown as { __csp: string[] }).__csp), "no CSP violation").toEqual([]);
        if (SHOTS) {
          fs.mkdirSync(SHOTS, { recursive: true });
          await shop.screenshot({ path: path.join(SHOTS, `${theme}-${motif}-${width}.png`), fullPage: false });
        }
      }
    }
  }
  expect(bad, bad.join("\n")).toEqual([]);

  // ---- interactions, on a fixed look ----
  await api(page, "PUT", `/api/businesses/${id}/theme`, { theme: "bakery", accent: "" });
  await shop.setViewportSize({ width: 390, height: 844 });
  await shop.goto(shopUrl(slug));
  // add to basket: the item is added, the count bumps (the fly dot is gone afterwards)
  await shop.locator(".item .add").first().click();
  await expect(shop.locator("#bar-count")).toContainText("1 item");
  await expect(shop.locator(".fly")).toHaveCount(0, { timeout: 3000 });
  // quick view: the sheet opens with the item's name, its stepper drives the real quantity box, Close returns focus
  const second = shop.locator(".item").nth(1);
  const name = await second.locator("input").first().getAttribute("data-name");
  await second.locator(".qv-open").click();
  const sheet = shop.locator("dialog.qv[open]");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("heading", { name: name! })).toBeVisible();
  await sheet.getByRole("button", { name: "Add to order" }).click();
  await expect(sheet.locator("output")).toHaveText("1");
  await expect(second.locator("input")).toHaveValue("1");
  await sheet.getByRole("button", { name: "One more" }).click();
  await expect(second.locator("input")).toHaveValue("2");
  await shop.keyboard.press("Escape");
  await expect(shop.locator("dialog.qv[open]")).toHaveCount(0);
  await expect(shop.locator("#bar-count")).toContainText("3 items");
  // scroll-spy: scrolling to the second category highlights its chip
  const chips = shop.locator(".chips .chip");
  if ((await chips.count()) > 1) {
    await shop.locator(".cat").nth(1).scrollIntoViewIfNeeded();
    await shop.locator(".cat").nth(1).evaluate((e) => e.scrollIntoView({ block: "start" }));
    await expect(chips.nth(1)).toHaveAttribute("aria-current", "true");
  }
  expect(await shop.evaluate(() => (window as unknown as { __csp: string[] }).__csp)).toEqual([]);

  // ---- reduced motion: nothing moves ----
  const calm = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), reducedMotion: "reduce" });
  const still = await calm.newPage();
  await still.goto(shopUrl(slug));
  expect(await still.locator(".motif").evaluate((e) => getComputedStyle(e).animationName)).toBe("none");
  expect(await still.locator(".pre").count()).toBe(0);
  await still.locator(".item .add").first().click();
  await expect(still.locator(".fly")).toHaveCount(0);
  await calm.close();

  // ---- JavaScript off: the plain form still orders ----
  const plain = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), javaScriptEnabled: false });
  const nojs = await plain.newPage();
  await nojs.goto(shopUrl(slug));
  expect(await nojs.locator(".qv-open").count()).toBe(0);
  await nojs.locator('input[name="qty_0"]').fill("2");
  await nojs.locator("#customer_name").fill("Riya NoJS");
  await nojs.locator("#customer_phone").fill("98765 43210");
  await pickDate(nojs);
  await nojs.getByRole("button", { name: "Send order" }).click();
  await expect(nojs.getByRole("heading", { name: /^Thank you, Riya!$/ })).toBeVisible();
  await plain.close();
  await ctx.close();
});
