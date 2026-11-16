// S10.5 screenshots at 375px and 1440px: landing, sign-in-first, My shops with order counts, the Orders page,
// and the preview after a link click. Run against the Docker stack (or a dev server).
import { expect, test, type Page } from "@playwright/test";
import * as path from "path";
import { ADMIN_EMAIL, api, approveUser, describe, launch, newSignedIn, readyForReal, setAddress, shopUrl, unique } from "../tests/helpers";

const OUT = process.env.LW_SHOTS || path.join(__dirname, "..", "..", "docs", "screenshots", "s10-5");
const SIZES = [
  { w: 375, h: 812, tag: "375" },
  { w: 1440, h: 900, tag: "1440" },
];

async function shoot(page: Page, name: string, full = true) {
  for (const s of SIZES) {
    await page.setViewportSize({ width: s.w, height: s.h });
    await page.waitForTimeout(700);
    await page.screenshot({ path: path.join(OUT, `${name}-${s.tag}.png`), fullPage: full });
  }
}

test("S10.5 screens", async ({ browser }) => {
  // 1. landing + sign-in-first, logged out
  const anon = await (await browser.newContext()).newPage();
  await anon.goto("/");
  await anon.waitForTimeout(1500);
  await shoot(anon, "01-landing", false);
  await anon.evaluate(() => document.getElementById("contact")?.scrollIntoView());
  await shoot(anon, "02-landing-who-its-for", false);
  await anon.goto("/#/new");
  await expect(anon).toHaveURL(/#\/signin\?next=new/);
  await shoot(anon, "03-sign-in-first");
  await anon.goto("/demo/meera");
  await shoot(anon, "04-demo-shop", false);

  // 2. a seller with a live shop and two customer orders
  const ctx = await browser.newContext();
  const email = `${unique("shots")}@example.test`;
  const seller = await newSignedIn(ctx, email);
  const admin = await newSignedIn(await browser.newContext(), ADMIN_EMAIL);
  await approveUser(admin, email);
  const id = await describe(seller);
  const slug = unique("shots");
  await setAddress(seller, id, slug);
  await shoot(seller, "05-review-with-go-live-checklist");
  await readyForReal(seller, id);
  await launch(seller, id, true);
  const customer = await (await browser.newContext()).newPage();
  for (const [name, phone] of [["Riya Sharma", "98765 43210"], ["Arjun & Co", "91234 56789"]]) {
    await customer.goto(shopUrl(slug));
    await customer.locator(".item .add").first().click();
    await customer.locator("#customer_name").fill(name);
    await customer.locator("#customer_phone").fill(phone);
    await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
    await customer.waitForLoadState("load");
  }
  await seller.goto("/#/shops");
  await expect(seller.getByText("2 new")).toBeVisible();
  await shoot(seller, "06-my-shops-with-order-counts");
  await seller.goto(`/#/b/${id}/orders`);
  const first = seller.locator(".order-card").first();
  await first.getByRole("button", { name: "Mark confirmed" }).click();
  await expect(first.locator(".order-status")).toHaveText("Confirmed");
  await shoot(seller, "07-orders-page");

  // 3. preview after a link click (a practice shop of the same seller)
  const draft = await describe(seller);
  await seller.goto(`/#/b/${draft}`);
  await seller.getByRole("button", { name: "Preview my shop" }).click();
  const frame = seller.frameLocator('iframe[title="Preview of your shop"]');
  await frame.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "Contact" }).click();
  await expect(frame.locator("header.bar .brand")).toBeVisible();
  await shoot(seller, "08-preview-after-link-click", false);
  expect((await api(seller, "GET", `/api/businesses/${id}/orders`)).status()).toBe(200);
});
