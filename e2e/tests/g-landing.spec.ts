// (g) The landing page (S10.5b): the Product menu (keyboard, Esc, outside click, anchors), the "we keep watching"
// section, and the hero scene: lazy, never loaded on app pages, and replaced by its still image for reduced motion.
import { expect, test } from "@playwright/test";

const SCENE = /\/assets\/scene-[\w-]+\.js$/;

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

test("the hero scene is lazy and only on the landing page", async ({ page }) => {
  const loaded: string[] = [];
  page.on("request", (r) => SCENE.test(new URL(r.url()).pathname) && loaded.push(r.url()));
  await page.goto("/#/signin");
  await page.waitForTimeout(2500);
  expect(loaded, "app pages never load the 3D scene").toEqual([]);
  // ?hero-still loads the scene even without a GPU (it renders one frame): the landing page does load it lazily
  await page.goto("/?hero-still");
  await expect.poll(() => loaded.length, { timeout: 30_000 }).toBeGreaterThan(0);
  await expect(page.getByRole("img", { name: /The proof, bottom to top: Address, Secure page/ })).toBeVisible();
});

test("software WebGL (no real GPU) keeps the still image and never loads three.js", async ({ page }) => {
  // headless Chromium here renders WebGL in software (SwiftShader): exactly the browsers we must spare
  const loaded: string[] = [];
  page.on("request", (r) => SCENE.test(new URL(r.url()).pathname) && loaded.push(r.url()));
  await page.goto("/");
  await expect(page.locator(".hero-still img")).toBeVisible();
  await page.waitForTimeout(2500);
  const gpu = await page.evaluate(() => {
    const gl = document.createElement("canvas").getContext("webgl", { failIfMajorPerformanceCaveat: true });
    return !!gl;
  });
  if (!gpu) expect(loaded).toEqual([]);
});

test("reduced motion shows the still image and never loads three.js", async ({ browser }) => {
  const ctx = await browser.newContext({ reducedMotion: "reduce" });
  const page = await ctx.newPage();
  const loaded: string[] = [];
  page.on("request", (r) => SCENE.test(new URL(r.url()).pathname) && loaded.push(r.url()));
  await page.goto("/");
  await expect(page.locator(".hero-still img")).toBeVisible();
  await page.waitForTimeout(2500);
  expect(loaded).toEqual([]);
  await ctx.close();
});
