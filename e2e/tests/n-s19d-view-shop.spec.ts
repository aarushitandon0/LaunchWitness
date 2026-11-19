// (n) S19D: My shops opens each shop. A practice shop gets "Preview" (the private preview, never a public address);
// a real live shop gets "View shop" (its own address, in a new tab) and shows that address under its name.
// LW_S19D_SHOTS=<dir> also saves My shops at 390 and 1440 px.
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, api, approveUser, describe, launch, newSignedIn, readyForReal, setAddress, shopUrl, unique } from "./helpers";

const card = (page: Page, name: string) => page.locator("ul.shops > li").filter({ hasText: name });

test("My shops: Preview for a practice shop, View shop for a live one", async ({ browser }) => {
  test.setTimeout(240_000);
  const email = `${unique("viewshop")}@example.test`;
  const seller = await newSignedIn(await browser.newContext(), email);
  const id = await describe(seller);
  const slug = unique("e2eview");
  await setAddress(seller, id, slug);
  await launch(seller, id, false);
  const name = (await (await api(seller, "GET", `/api/businesses/${id}`)).json()).name as string;

  // practice: Preview opens the private preview; no public link and no address anywhere on the card
  let list = await (await api(seller, "GET", "/api/businesses")).json();
  expect(list.find((b: { id: number }) => b.id === id).live_url).toBeNull();
  await seller.goto("/#/shops");
  const practice = card(seller, name);
  await expect(practice.getByRole("button", { name: "Preview" })).toBeVisible();
  await expect(practice.getByRole("link", { name: "View shop" })).toHaveCount(0);
  await expect(practice.getByText(`${slug}.`)).toHaveCount(0);
  await practice.getByRole("button", { name: "Preview" }).focus();
  await seller.keyboard.press("Enter"); // keyboard works
  await expect(seller.getByRole("dialog", { name: "Preview of your shop" })).toBeVisible();
  await expect(seller.frameLocator('iframe[title="Preview of your shop"]').locator(".brand")).toBeVisible();
  await seller.keyboard.press("Escape");
  await expect(seller.getByRole("dialog")).toHaveCount(0);

  // real launch (pretend GoDaddy on this server; the shop is served at its own address through Caddy)
  const admin = await newSignedIn(await browser.newContext(), ADMIN_EMAIL);
  await approveUser(admin, email);
  await readyForReal(seller, id);
  await launch(seller, id, true);

  list = await (await api(seller, "GET", "/api/businesses")).json();
  expect(list.find((b: { id: number }) => b.id === id).live_url).toBe(shopUrl(slug));
  await seller.goto("/#/shops");
  await seller.reload(); // same hash as before: load the list again
  const live = card(seller, name);
  const view = live.getByRole("link", { name: "View shop" });
  await expect(view).toHaveAttribute("href", shopUrl(slug));
  await expect(view).toHaveAttribute("target", "_blank");
  await expect(view).toHaveAttribute("rel", /noopener/);
  await expect(live.getByText(new URL(shopUrl(slug)).host)).toBeVisible();
  await expect(live.getByRole("link", { name: "Orders" })).toBeVisible();
  await expect(live.getByRole("link", { name: "Report" })).toBeVisible();
  const [tab] = await Promise.all([seller.context().waitForEvent("page"), view.click()]);
  await tab.waitForLoadState();
  expect(tab.url()).toBe(shopUrl(slug));
  await expect(tab.locator('meta[name="lw-shop"]')).toHaveAttribute("content", /.+/);
  await tab.close();

  // the Report header links the live shop too
  await seller.goto(`/#/b/${id}/report`);
  // (hidden while a check round runs; monitoring may start one right after launch)
  await expect(seller.getByRole("link", { name: "Open my shop" })).toHaveAttribute("href", shopUrl(slug), { timeout: 150_000 });

  const shots = process.env.LW_S19D_SHOTS;
  if (shots) {
    const other = await describe(seller); // a second, practice-only shop so both buttons show
    await launch(seller, other, false);
    for (const width of [390, 1440]) {
      await seller.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      await seller.goto("/#/shops");
      await seller.reload();
      await expect(seller.getByRole("link", { name: "View shop" })).toBeVisible();
      await expect(seller.getByRole("button", { name: "Preview" })).toBeVisible();
      const sideways = await seller.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(sideways, `no sideways scroll at ${width}`).toBe(false);
      await seller.screenshot({ path: `${shots}/my-shops-${width}.png`, fullPage: true });
    }
  }
});
