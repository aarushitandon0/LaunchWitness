// S22: a custom order (photo cake): the customer's note + one reference photo reach the owner's Orders page; and the demo
// shops' WhatsApp button opens a plain demo page, never WhatsApp.
import path from "path";
import { Browser, expect, Page, test } from "@playwright/test";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

const PHOTO = path.resolve(__dirname, "../../frontend/public/icon-512.png");
const WISH = "Happy Birthday Riya on the cake, unicorn theme, pink and gold";

async function liveCustomShop(page: Page): Promise<{ id: number; slug: string; photoPrint: number }> {
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique("s22c");
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const products = biz.profile.products.map((p: { name: string }) =>
    /photo print/i.test(p.name) ? { ...p, custom: true } : p);
  const photoPrint = products.findIndex((p: { name: string }) => /photo print/i.test(p.name));
  expect(photoPrint).toBeGreaterThanOrEqual(0);
  const r = await api(page, "PUT", `/api/businesses/${id}`, { profile: { ...biz.profile, products }, subdomain: slug });
  expect(r.status(), await r.text()).toBe(200);
  await launch(page, id, true);
  return { id, slug, photoPrint };
}

async function customer(browser: Browser, js = true) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), javaScriptEnabled: js,
    viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || /Content Security Policy|Refused to/i.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  return { ctx, page, errors };
}

test("Meera photo-cake order with a note and a reference photo: Orders shows both", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { id, slug, photoPrint } = await liveCustomShop(page);
  const { ctx, page: c, errors } = await customer(browser);
  await c.goto(shopUrl(slug));
  const box = c.locator("#custom-box");
  await expect(box).toBeHidden(); // nothing custom in the basket yet
  const cake = c.locator('li.item[data-item="Chocolate truffle cake"]');
  await cake.scrollIntoViewIfNeeded();
  await cake.locator(".q.opt").nth(0).locator(".add").click();
  await expect(box).toBeHidden();
  const print = c.locator(`li.item[data-i="${photoPrint}"]`);
  await print.scrollIntoViewIfNeeded();
  await print.locator(".add").click();
  await expect(box).toBeVisible();
  await c.locator(`#custom_${photoPrint}`).fill(WISH);
  await c.locator("#reference_photo").setInputFiles(PHOTO);
  await c.locator("#customer_name").fill("Asha Rao");
  await c.locator("#customer_phone").fill("98765 43210");
  await pickDate(c);
  await c.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await c.waitForLoadState("load");
  await expect(c.getByRole("heading", { name: /^Thank you, Asha!$/ })).toBeVisible();
  await expect(c.locator(".basket")).toContainText(`Your request: ${WISH}`);
  await expect(c.getByText("Your reference photo was sent to the shop.")).toBeVisible();
  expect(await c.content()).not.toContain("reference-photo");
  expect(errors, errors.join("\n")).toEqual([]);
  await ctx.close();

  await page.goto(`/#/b/${id}/orders`);
  const card = page.locator(".order-card", { hasText: "Asha Rao" });
  await expect(card.getByTestId("custom-note")).toContainText(WISH);
  const img = card.getByTestId("ref-photo").locator("img");
  await expect(img).toBeVisible();
  await expect.poll(() => img.evaluate((i: HTMLImageElement) => i.naturalWidth)).toBeGreaterThan(0);
});

test("JavaScript off: the custom fields show and the order with a photo goes through", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { slug, photoPrint } = await liveCustomShop(page);
  const { ctx, page: c } = await customer(browser, false);
  await c.goto(shopUrl(slug));
  await expect(c.locator(`#custom_${photoPrint}`)).toBeVisible();
  await c.locator('input[name="qty_0_0"]').fill("1");
  await c.locator(`input[name="qty_${photoPrint}"]`).fill("1");
  await c.locator(`#custom_${photoPrint}`).fill(WISH);
  await c.locator("#reference_photo").setInputFiles(PHOTO);
  await c.locator("#customer_name").fill("Ravi K");
  await c.locator("#customer_phone").fill("98765 43211");
  const date = c.locator("#wanted_date");
  if (await date.count()) {
    const min = (await date.getAttribute("min"))!;
    const d = new Date(min + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + 2);
    await date.fill(d.toISOString().slice(0, 10));
  }
  const pick = c.locator('input[name="fulfilment"][value="pickup"]');
  if (await pick.count()) await pick.check();
  await Promise.all([c.waitForNavigation(), c.locator('#order-form button[type="submit"]').click()]);
  await expect(c.locator(".basket")).toContainText(`Your request: ${WISH}`);
  await ctx.close();
});

test("Demo shop: the WhatsApp button opens the plain demo page, never WhatsApp", async ({ browser }) => {
  const { ctx, page: c, errors } = await customer(browser);
  await c.goto(`${BASE}/demo/meera`);
  const wa = c.locator("a.btn-wa").first();
  await expect(wa).toHaveAttribute("href", "/demo/meera/whatsapp");
  await wa.scrollIntoViewIfNeeded();
  await wa.click();
  await expect(c).toHaveURL(/\/demo\/meera\/whatsapp$/);
  await expect(c.getByText("This is a demo website. On a real shop, this button opens a WhatsApp chat with the seller.")).toBeVisible();
  await c.locator("#main .cta").getByRole("link", { name: "Back to the shop" }).click();
  await expect(c).toHaveURL(/\/demo\/meera\/?$/);
  expect(await c.content()).not.toContain("wa.me");
  expect(errors, errors.join("\n")).toEqual([]);
  await ctx.close();
});
