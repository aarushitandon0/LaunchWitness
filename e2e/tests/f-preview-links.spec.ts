// (f) The owner's private preview: every link and button on the shop page works INSIDE the frame.
// Bug (S10.5 §4): in-page links like #menu resolved against the app's URL, so the frame went blank.
import { expect, test, type FrameLocator, type Page } from "@playwright/test";
import { api, describe, newSignedIn, unique } from "./helpers";

async function openPreview(page: Page, id: number): Promise<FrameLocator> {
  await page.goto(`/#/b/${id}`);
  await page.getByRole("button", { name: "Preview my shop" }).click();
  const frame = page.frameLocator('iframe[title="Preview of your shop"]');
  await expect(frame.locator(".brand")).toBeVisible();
  return frame;
}

const stillTheShop = async (frame: FrameLocator) => {
  await expect(frame.locator("header.bar .brand")).toBeVisible();
  await expect(frame.getByText("Preview: only you can see this page")).toBeVisible();
};

test("every link and button in the preview stays inside the shop", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await newSignedIn(ctx, `${unique("preview")}@example.test`);
  const id = await describe(page);
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const profile = { ...biz.profile, whatsapp: "98765 43210", phone: "98765 43210", instagram: "meera.bakes" };
  expect((await api(page, "PUT", `/api/businesses/${id}`, { profile, subdomain: biz.subdomain })).status()).toBe(200);
  const hasInstagram = !!(await (await api(page, "GET", `/api/businesses/${id}`)).json()).profile.instagram;

  const frame = await openPreview(page, id);
  const appUrl = page.url();

  // in-page anchors scroll within the shop
  for (const name of ["Menu", "Contact"]) {
    await frame.getByRole("navigation", { name: "Sections" }).getByRole("link", { name }).click();
    await stillTheShop(frame);
  }
  await frame.locator("header.bar").getByRole("link", { name: "Order" }).click();
  await stillTheShop(frame);
  const chips = frame.locator(".chips a");
  for (let i = 0; i < (await chips.count()); i++) {
    await chips.nth(i).click();
    await stillTheShop(frame);
  }
  await frame.getByRole("link", { name: "See menu & order" }).click();
  await stillTheShop(frame);

  // basket buttons work
  await frame.locator(".item .add").first().click();
  await expect(frame.locator("#bar-count")).toHaveText("1 item");
  await frame.locator(".item .plus").first().click();
  await expect(frame.locator("#bar-count")).toHaveText("2 items");

  // the order form doesn't send; it says why
  await frame.locator("#customer_name").fill("Test");
  await frame.locator("#customer_phone").fill("98765 43210");
  await frame.getByRole("button", { name: "Send order" }).click();
  await expect(frame.getByText("Preview: orders are turned off until your shop is live")).toBeVisible();
  await stillTheShop(frame);

  // external links open a new tab (and never navigate the frame)
  for (const name of hasInstagram ? [/WhatsApp/, /Instagram/] : [/WhatsApp/]) {
    const link = frame.getByRole("link", { name }).first();
    await expect(link).toHaveAttribute("target", "_blank");
    const [popup] = await Promise.all([ctx.waitForEvent("page"), link.click()]);
    await popup.close();
    await stillTheShop(frame);
  }
  await expect(frame.getByRole("link", { name: /Call/ }).first()).toHaveAttribute("target", "_blank");

  // the shop's own pages open inside the preview, and back again
  await frame.locator("footer").getByRole("link", { name: "Privacy" }).click();
  await expect(frame.getByRole("heading", { name: "Privacy" })).toBeVisible();
  await stillTheShop(frame);
  await frame.getByRole("link", { name: "Back to the shop" }).click();
  await expect(frame.locator("#menu")).toBeVisible();
  await stillTheShop(frame);

  // the app itself never moved
  expect(page.url()).toBe(appUrl);
});
