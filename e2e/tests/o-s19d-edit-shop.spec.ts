// (o) S19D Part 7b: My shops -> Edit shop -> add "Mango cake ½ kg" at ₹650 marked New -> Save changes ->
// "Your shop is updated" -> the live shop shows it with a "New" badge. LW_S19D_SHOTS=<dir> saves the edit screen
// and the shop at 390 and 1440 px, in two looks.
import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, api, approveUser, describe, launch, newSignedIn, readyForReal, setAddress, shopUrl, unique } from "./helpers";

test("a live shop gets a new item with a New badge", async ({ browser }) => {
  test.setTimeout(300_000);
  const email = `${unique("editshop")}@example.test`;
  const seller = await newSignedIn(await browser.newContext(), email);
  const id = await describe(seller);
  const slug = unique("e2eedit");
  await setAddress(seller, id, slug);
  const admin = await newSignedIn(await browser.newContext(), ADMIN_EMAIL);
  await approveUser(admin, email);
  await readyForReal(seller, id);
  await launch(seller, id, true);

  await seller.goto("/#/shops");
  await seller.reload();
  await seller.locator("ul.shops > li").getByRole("link", { name: "Edit shop" }).click();
  await seller.waitForURL(new RegExp(`#/b/${id}$`));
  await seller.getByRole("button", { name: "+ Add an item" }).click();
  const row = seller.locator(".product").last();
  await row.getByLabel("Item", { exact: true }).fill("Mango cake ½ kg");
  await row.getByLabel("Price (₹)").fill("650");
  await expect(row.getByLabel(/Show as New on my shop/)).toBeChecked(); // on by default after launch
  await seller.getByRole("button", { name: "Save changes" }).click();
  await expect(seller.getByText("Your shop is updated.")).toBeVisible();
  const view = seller.getByRole("link", { name: "View my shop" });
  await expect(view).toHaveAttribute("href", shopUrl(slug));

  const customer = await (await browser.newContext()).newPage();
  await customer.goto(shopUrl(slug));
  const item = customer.locator(".item").filter({ hasText: "Mango cake ½ kg" });
  await expect(item).toContainText("₹650");
  await expect(item.locator(".new-badge")).toHaveText(/new/i);
  await expect(customer.getByText("New on the menu: Mango cake ½ kg")).toBeVisible();
  await expect(customer.locator('meta[name="lw-shop"]')).toHaveAttribute("content", /.+/);

  const shots = process.env.LW_S19D_SHOTS;
  if (shots) {
    for (const theme of ["bakery", "kitchen"]) {
      expect((await api(seller, "PUT", `/api/businesses/${id}/theme`, { theme })).status()).toBe(200);
      for (const width of [390, 1440]) {
        const size = { width, height: width === 390 ? 844 : 900 };
        await customer.setViewportSize(size);
        await customer.goto(shopUrl(slug) + "#menu");
        await customer.reload(); // same URL as before: load the new look
        await customer.locator(".new-strip").scrollIntoViewIfNeeded();
        await customer.screenshot({ path: `${shots}/shop-new-item-${theme}-${width}.png` });
      }
    }
    for (const width of [390, 1440]) {
      await seller.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await seller.reload();
      await seller.locator(".product").last().scrollIntoViewIfNeeded();
      await seller.screenshot({ path: `${shots}/edit-shop-${width}.png` });
    }
  }
});

test("a held edit keeps the live shop as it was until the team publishes it", async ({ browser }) => {
  test.setTimeout(300_000);
  const email = `${unique("heldedit")}@example.test`;
  const seller = await newSignedIn(await browser.newContext(), email);
  const id = await describe(seller);
  const slug = unique("e2eheld");
  await setAddress(seller, id, slug);
  const admin = await newSignedIn(await browser.newContext(), ADMIN_EMAIL);
  await approveUser(admin, email);
  await readyForReal(seller, id);
  await launch(seller, id, true);

  const biz = await (await api(seller, "GET", `/api/businesses/${id}`)).json();
  const r = await api(seller, "PUT", `/api/businesses/${id}`, {
    profile: { ...biz.profile, tagline: "Cakes, and whisky bottles on order" }, subdomain: biz.subdomain,
  });
  expect(r.status()).toBe(200);
  await seller.goto(`/#/b/${id}`);
  await seller.reload();
  await expect(seller.getByText(/our team will look at them before they go on your shop/)).toBeVisible();

  const customer = await (await browser.newContext()).newPage();
  await customer.goto(shopUrl(slug));
  await expect(customer.locator("body")).not.toContainText("whisky");

  await admin.goto("/#/admin");
  const row = admin.locator("ul.admin-list > li").filter({ hasText: "Edited live shop: needs a look" }).filter({ hasText: email });
  await row.getByRole("button", { name: "Publish edit" }).click();
  await expect(row).toHaveCount(0);
  await customer.reload();
  await expect(customer.locator("body")).toContainText("whisky");
});
