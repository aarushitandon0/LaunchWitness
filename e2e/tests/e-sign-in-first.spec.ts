// (e) Sign in first, and routing that behaves like a real app: "Start" → sign-in (with the reason) → emailed link →
// straight back to Describe; Back/Forward and refresh keep the page; unknown pages say "Page not found"; the demo shop
// opens logged out and places no order.
import { expect, test } from "@playwright/test";
import { describe, pickDate, signIn, unique } from "./helpers";

test("Start asks to sign in, then returns to Describe", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Start", exact: true }).first().click();
  await expect(page).toHaveURL(/#\/signin\?next=new/);
  await expect(page.getByText("Your shop and its orders belong to your account")).toBeVisible();
  await expect(page.getByRole("link", { name: "Try it without an account" })).toBeVisible();

  await signIn(page, `${unique("first")}@example.test`, { stay: true });
  await expect(page).toHaveURL(/#\/new$/);
  await expect(page.getByRole("heading", { name: "Describe your business" })).toBeVisible();
  // signed-in top bar
  const nav = page.getByRole("navigation", { name: "Main", exact: true });
  await expect(nav.getByRole("link", { name: "New shop" })).toHaveAttribute("aria-current", "page");
  await expect(nav.getByRole("link", { name: "My shops" })).toBeVisible();

  const id = await describe(page, { here: true });
  // refresh keeps the page; the step header shows where we are and links back
  await page.reload();
  await expect(page).toHaveURL(new RegExp(`#/b/${id}$`));
  await expect(page.getByRole("heading", { name: "Check your details" })).toBeVisible();
  await page.goto(`/#/b/${id}/launch`);
  await page.getByRole("navigation", { name: "Steps" }).getByRole("link", { name: /Review/ }).click();
  await expect(page).toHaveURL(new RegExp(`#/b/${id}$`));
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`#/b/${id}/launch$`));
  await page.goForward();
  await expect(page).toHaveURL(new RegExp(`#/b/${id}$`));

  // a shop that isn't yours (or doesn't exist): plain message + a way back
  await page.goto("/#/b/999999");
  await expect(page.getByRole("link", { name: "Back to My shops" })).toBeVisible();
  // unknown page
  await page.goto("/#/no-such-page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});

test("the demo shop works logged out and places no order", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "See a demo shop" }).first().click();
  await expect(page).toHaveURL(/\/demo\/meera$/);
  await expect(page.getByText("Demo shop: orders here are not real")).toBeVisible();
  await page.getByRole("button", { name: "Add" }).first().click();
  await page.getByLabel("Your name").fill("Asha");
  await page.getByLabel("Your phone number").fill("98765 43210");
  await pickDate(page); // S21B: Meera asks for 2 days notice (live Reader)
  await page.getByRole("button", { name: "Send order" }).click();
  await expect(page.getByRole("heading", { name: "This is a demo" })).toBeVisible();
});
