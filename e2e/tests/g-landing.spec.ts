// (g) The landing page (S10.5b): the Product menu (keyboard, Esc, outside click, anchors) and the "we keep watching"
// section.
import { expect, test } from "@playwright/test";


test("the Product menu opens, closes and jumps to sections", async ({ page }) => {
  await page.goto("/");
  const menu = page.getByRole("button", { name: /Product/ }).first();
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  const panel = page.getByRole("region", { name: "Product" });
  for (const col of ["What it does", "Who it's for", "Free tools", "Learn"]) await expect(panel.getByText(col)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(menu).toBeFocused();
  await menu.click();
  await page.mouse.click(5, 400); // outside
  await expect(panel).toHaveCount(0);
  await menu.click();
  await panel.getByRole("link", { name: "Keep watching" }).click();
  await expect(page).toHaveURL(/#watch$/);
  await expect(page.getByRole("heading", { name: "We keep watching after launch" })).toBeInViewport();
  await expect(page.locator("#watch .watch-item .label", { hasText: "Every 15 minutes" })).toBeVisible();
  // from another page, a menu link still lands on the section
  await page.goto("/#/signin");
  await page.getByRole("button", { name: /Product/ }).first().click();
  await page.getByRole("region", { name: "Product" }).getByRole("link", { name: "Security & privacy" }).click();
  await expect(page.getByRole("heading", { name: "Your shop is yours alone." })).toBeInViewport();
});
