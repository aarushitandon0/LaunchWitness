// S15: where a shop sells and how a customer pays. A customer outside the delivery area is told politely (in the page,
// and again by the server), then chooses pickup and orders; the pay link asks for the advance with the order number.
import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

test("outside the delivery area -> told politely -> chooses pickup -> orders -> pays the advance", async ({ page, browser }) => {
  test.setTimeout(300_000);
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique("s15");
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const saved = await api(page, "PUT", `/api/businesses/${id}`, {
    profile: {
      ...biz.profile, selling_mode: "pickup_local", delivery_areas: "Baner, 411045", delivery_fee_inr: 80,
      payment_terms: "advance", advance_percent: 30, accepts_cash: true, cancellation_preset: "full_24h",
    },
    subdomain: slug,
  });
  expect(saved.status(), await saved.text()).toBe(200);
  await launch(page, id, true);

  const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost") });
  const customer = await ctx.newPage();
  await customer.setViewportSize({ width: 375, height: 800 });
  await customer.goto(shopUrl(slug));
  await expect(customer.getByRole("heading", { name: "Where we sell" })).toBeVisible();
  await customer.locator(".item .add").first().click();
  await customer.locator("#customer_name").fill("Riya Outside");
  await customer.locator("#customer_phone").fill("98765 43210");
  await pickDate(customer);

  // Delivery to a PIN she doesn't serve: told before sending (the page), and refused by the server too.
  await customer.locator('input[name="fulfilment"][value="delivery"]').check();
  await customer.locator("#delivery_address").fill("12 MG Road, Bengaluru");
  await customer.locator("#delivery_pin").fill("560001");
  await expect(customer.locator("#area-msg")).toContainText("delivers only in Baner and 411045");
  await expect(customer.locator("#area-msg")).toContainText("You could choose pickup instead.");
  await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await expect(customer.locator("#area-msg")).toBeVisible(); // still on the form: nothing was sent
  // The server refuses it too. The browser sends the same form with form.submit(), which skips the page's own check
  // (Node can't resolve *.localhost on Windows, and the shop's security policy stops fetch()).
  const [post] = await Promise.all([
    customer.waitForResponse((r) => r.url().endsWith("/order") && r.request().method() === "POST"),
    customer.locator("#order-form").evaluate((f: HTMLFormElement) => HTMLFormElement.prototype.submit.call(f)),
  ]);
  expect(post.status()).toBe(422);
  expect(await post.text()).toContain("delivers only in Baner and 411045. You could choose pickup instead.");
  expect((await (await api(page, "GET", `/api/businesses/${id}/orders`)).json()).length).toBe(0);
  await customer.goto(shopUrl(slug));
  await customer.locator(".item .add").first().click();
  await customer.locator("#customer_name").fill("Riya Outside");
  await customer.locator("#customer_phone").fill("98765 43210");
  await pickDate(customer);

  // She chooses pickup instead and orders.
  await customer.locator('input[name="fulfilment"][value="pickup"]').check();
  await expect(customer.locator("#delivery-fields")).toBeHidden();
  await expect(customer.locator("#pay-now")).toContainText("You'll pay");
  await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await customer.waitForLoadState("load");
  await expect(customer.getByRole("heading", { name: /Thank you, Riya Outside/ })).toBeVisible();
  await expect(customer.getByText(/Pay now: ₹/)).toBeVisible();
  const href = await customer.getByRole("link", { name: "open your UPI app" }).getAttribute("href");
  expect(href).toMatch(/^upi:\/\/pay\?/);
  expect(href).toMatch(/am=\d+\.00/);
  expect(decodeURIComponent(href!)).toMatch(/tn=Order LW-[A-Z0-9]{8}/);
  await expect(customer.getByText("Cancel up to 24 hours before for a full refund.")).toBeVisible();
  await ctx.close();

  // The owner's Orders page reads where the money stands, and the address of a delivery is only ever there.
  await page.goto(`/#/b/${id}/orders`);
  const card = page.locator(".order-card", { hasText: "Riya Outside" });
  await expect(card.locator(".order-pay")).toContainText("Waiting for the advance");
  await expect(card.getByRole("button", { name: "Mark confirmed" })).toBeVisible();
  await card.getByRole("button", { name: "Mark confirmed" }).click();
  await expect(card.getByRole("button", { name: "Advance received" })).toBeVisible();
  await card.getByRole("button", { name: "Advance received" }).click();
  await expect(card.locator(".order-pay")).toContainText("Advance paid");
});
