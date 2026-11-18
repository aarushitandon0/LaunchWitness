// S17: on Describe, each item is a row with its own photo. After "Make my website" the photos are on the items the
// Reader made from those rows (the server matches her words), shown on Review and in the shop's preview.
import { expect, Page, test } from "@playwright/test";
import { ADMIN_EMAIL, api, signIn } from "./helpers";

async function canvasJpeg(page: Page, color: string): Promise<Buffer> {
  const bytes = await page.evaluate(async (c) => {
    const cv = document.createElement("canvas");
    cv.width = 800;
    cv.height = 600;
    const g = cv.getContext("2d")!;
    g.fillStyle = c;
    g.fillRect(0, 0, 800, 600);
    const blob: Blob = await new Promise((r) => cv.toBlob((b) => r(b!), "image/jpeg", 0.9));
    return Array.from(new Uint8Array(await blob.arrayBuffer()));
  }, color);
  return Buffer.from(bytes);
}

test("each item gets its photo on Describe and keeps it on Review and in the shop", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page, ADMIN_EMAIL);
  await page.goto("/#/new");
  await expect(page.getByRole("heading", { name: "Describe your business" })).toBeVisible();
  // The rows are the default; the example fills them (one row per line of Meera's list).
  await expect(page.getByLabel("Item 1 name")).toBeVisible();
  await page.getByRole("button", { name: /Meera/ }).click();
  const first = await page.getByLabel("Item 1 name").inputValue();
  const second = await page.getByLabel("Item 3 name").inputValue();
  expect(first).toMatch(/truffle/i);
  expect(await page.getByLabel("Item 1 price").inputValue()).toMatch(/650/);

  // Add and remove a row, then a photo on two items (a thumbnail shows in the row at once).
  const before = await page.locator(".item-entry").count();
  await page.getByRole("button", { name: "+ Add another item" }).click();
  await expect(page.locator(".item-entry")).toHaveCount(before + 1);
  await page.getByRole("button", { name: `Remove item ${before + 1}` }).click();
  await expect(page.locator(".item-entry")).toHaveCount(before);
  await page.getByLabel(`Photo of item 1: ${first}`).setInputFiles({ name: "a.jpg", mimeType: "image/jpeg", buffer: await canvasJpeg(page, "#6b3a1f") });
  await page.getByLabel(`Photo of item 3: ${second}`).setInputFiles({ name: "b.jpg", mimeType: "image/jpeg", buffer: await canvasJpeg(page, "#e9c46a") });
  await expect(page.locator(".item-entry .item-thumb")).toHaveCount(2);

  // Switching to the pasted list and back keeps the items.
  await page.getByRole("button", { name: "Paste a whole list instead" }).click();
  await expect(page.getByRole("textbox", { name: "Price list" })).toHaveValue(new RegExp(first.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")));
  await page.getByRole("button", { name: "Add items one by one, with photos" }).click();
  await expect(page.getByLabel("Item 1 name")).toHaveValue(first);
  // (the round trip drops the photos: re-add one, as she would)
  await page.getByLabel(`Photo of item 1: ${first}`).setInputFiles({ name: "a.jpg", mimeType: "image/jpeg", buffer: await canvasJpeg(page, "#6b3a1f") });
  await page.getByLabel(`Photo of item 3: ${second}`).setInputFiles({ name: "b.jpg", mimeType: "image/jpeg", buffer: await canvasJpeg(page, "#e9c46a") });

  await page.getByRole("button", { name: "Make my website" }).click();
  await page.waitForURL(/#\/b\/\d+$/);
  const id = Number(page.url().match(/#\/b\/(\d+)/)![1]);
  await expect(page.getByText(/couldn't add the photo/)).toHaveCount(0);

  // On Review: two item thumbnails, on the right items.
  const list = await (await api(page, "GET", `/api/businesses/${id}/photos`)).json();
  const items = Object.keys(list.items);
  expect(items.length).toBeGreaterThanOrEqual(2);
  expect(items.some((n) => /truffle/i.test(n))).toBe(true);
  expect(list.shop).toEqual([]); // item photos, never shop photos
  await expect(page.locator(".item-thumb")).toHaveCount(items.length);

  // In the shop's preview: the item photos are there.
  const html = await (await api(page, "GET", `/api/businesses/${id}/preview`)).text();
  for (const n of items) expect(html).toContain(list.items[n].small.replace(/-\d+\.webp$/, ""));
});

test("a photo too big is refused in its row, before anything is sent", async ({ page }) => {
  await signIn(page, ADMIN_EMAIL);
  await page.goto("/#/new");
  await page.getByLabel("Item 1 name").fill("Brownies box of 9");
  const big = Buffer.alloc(7 * 1024 * 1024 + 10, 0xff);
  await page.getByLabel("Photo of item 1: Brownies box of 9").setInputFiles({ name: "huge.jpg", mimeType: "image/jpeg", buffer: big });
  await expect(page.getByRole("alert")).toContainText("too big");
  await expect(page.locator(".item-entry .item-thumb")).toHaveCount(0);
});

test("Review -> back to Describe: her words come back, Read it again keeps the same shop", async ({ page }) => {
  test.setTimeout(180_000);
  await signIn(page, ADMIN_EMAIL);
  await page.goto("/#/new");
  await page.getByRole("button", { name: /Meera/ }).click();
  await page.getByRole("button", { name: "Make my website" }).click();
  await page.waitForURL(/#\/b\/\d+$/);
  const id = Number(page.url().match(/#\/b\/(\d+)/)![1]);
  const before = await (await api(page, "GET", `/api/businesses/${id}`)).json();

  // The current step's label is readable (light on the dark pill), and Describe is a link back.
  const here = page.locator(".stepper-here > span");
  const [fg, bg] = await here.evaluate((el) => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]);
  expect(fg).not.toEqual(bg);
  const lum = (c: string) => { const [r, g, b] = c.match(/\d+/g)!.map(Number); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  expect(Math.abs(lum(fg) - lum(bg))).toBeGreaterThan(100);
  await page.locator(".stepper").getByRole("link", { name: /Describe/ }).click();
  await page.waitForURL(new RegExp(`#/b/${id}/describe$`));

  // Her words are back, as rows.
  await expect(page.getByLabel("About your business")).toHaveValue(before.description);
  await expect(page.getByLabel("Item 1 name")).toHaveValue(/truffle/i);
  await page.getByLabel("Item 1 price").fill("700");
  await page.getByRole("button", { name: "Read it again" }).click();
  await page.waitForURL(new RegExp(`#/b/${id}$`));

  const after = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  expect(after.id).toBe(id);
  expect(after.subdomain).toBe(before.subdomain);
  expect(after.price_list).toContain("₹700");
  const shops = await (await api(page, "GET", "/api/businesses")).json();
  expect(shops.filter((s: { id: number }) => s.id === id)).toHaveLength(1);
});
