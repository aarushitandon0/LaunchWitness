import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, BASE, describe, signIn } from "./helpers";

// S14: each kind of shop has its own look. The same order path works in every look, the fonts come from the app itself.

const DEMOS: [string, string][] = [["meera", "bakery"], ["imran", "tailor"], ["sunita", "kitchen"]];

for (const [demo, theme] of DEMOS) {
  test(`the ${demo} demo shop is a ${theme} shop: own fonts, basket total, no sideways scroll`, async ({ page }) => {
    const bad: string[] = [];
    const origin = new URL(BASE).origin;
    page.on("response", (r) => { if (r.url().startsWith("http") && !r.url().startsWith(origin)) bad.push(r.url()); });
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto(`/demo/${demo}`);
    await expect(page.locator("body")).toHaveClass(new RegExp(`theme-${theme}`));
    await page.evaluate(() => document.fonts.ready);
    const loaded = await page.evaluate(() => [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family));
    expect(loaded.length).toBeGreaterThan(0);
    expect(loaded.every((f) => f.includes("LW "))).toBe(true);
    // The basket works in this look: two adds and a plus, and the total is what the prices say.
    const adds = page.locator(".item .add");
    await adds.nth(0).click();
    await adds.nth(1).click();
    await page.locator(".item.chosen .plus").first().click();
    const prices = await page.locator(".item.chosen input").evaluateAll((els) => els.map((e) => [Number((e as HTMLInputElement).value), Number((e as HTMLInputElement).dataset.price)]));
    const expected = prices.reduce((s, [q, p]) => s + q * p, 0);
    const shown = (await page.locator("#total").innerText()).replace(/[^\d]/g, "");
    expect(Number(shown)).toBe(expected);
    expect(expected).toBeGreaterThan(0);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    expect(bad).toEqual([]); // nothing was fetched from another site
  });
}

test("the demo order form still works in a themed shop (demo: places nothing)", async ({ page }) => {
  await page.goto("/demo/imran");
  await page.locator(".item .add").first().click();
  await page.getByLabel("Your name").fill("Asha");
  await page.getByLabel("Your phone number").fill("98765 43210");
  await page.getByRole("button", { name: "Send order" }).click();
  await expect(page.getByRole("heading", { name: "This is a demo" })).toBeVisible();
});

test("without JavaScript the order form is plain boxes and still there", async ({ browser }) => {
  const ctx = await browser.newContext({ javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto("/demo/sunita");
  await expect(page.locator("input[name=qty_0]")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send order" })).toBeVisible();
  await ctx.close();
});

test("the owner picks another look on the Review page; the shop and its preview change", async ({ page }) => {
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  await page.goto(`/#/b/${id}`);
  await expect(page.getByRole("heading", { name: "The look of your shop" }).first()).toBeVisible();
  const frame = page.frameLocator("iframe.theme-preview");
  await expect(frame.locator("body")).toHaveClass(/theme-bakery/, { timeout: 15_000 });
  await page.getByRole("radio", { name: /^Gifts & hampers/ }).click();
  await expect(frame.locator("body")).toHaveClass(/theme-gifts/, { timeout: 15_000 });
  await page.getByRole("radio", { name: "Emerald", exact: true }).click();
  await expect(page.getByRole("radio", { name: "Emerald", exact: true })).toHaveAttribute("aria-checked", "true");
  await page.reload();
  await expect(page.getByRole("radio", { name: /^Gifts & hampers/ })).toHaveAttribute("aria-checked", "true");
});
