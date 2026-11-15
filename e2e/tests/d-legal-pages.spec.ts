// Privacy and Terms: linked from the sign-in page and the footer, plain and labelled beta.
import { expect, test } from "@playwright/test";

test("privacy and terms are one click from sign-in", async ({ page }) => {
  await page.goto("/#/signin");
  await page.getByRole("link", { name: "Privacy page" }).click();
  await expect(page.getByRole("heading", { name: "What we keep about you, and why" })).toBeVisible();
  await expect(page.getByText(/Version 1 \(beta\)/)).toBeVisible();
  await expect(page.getByText(/a live shop's address becomes public/i)).toBeVisible();
  await page.goto("/#/signin");
  await page.getByRole("link", { name: "Terms of use" }).click();
  await expect(page.getByRole("heading", { name: "The deal, in plain words" })).toBeVisible();
  await expect(page.locator("footer").getByRole("link", { name: "Privacy" })).toBeVisible();
});
