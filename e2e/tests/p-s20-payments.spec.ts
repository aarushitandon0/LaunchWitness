// S20 Part A: the UPI details are private until a real order. The customer orders, sees the UPI link with the exact amount,
// says she paid (12-digit UTR + a screenshot), and the owner's Orders page reads "Customer says paid" until SHE marks it Paid.
import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

// A tiny valid PNG (1x1, 120x120 would be nicer but the pipeline only needs a real image of >= 64 px)
function png(): Buffer {
  // 64x64 solid colour PNG generated with a minimal encoder (no dependency).
  const zlib = require("zlib") as typeof import("zlib");
  const w = 64, h = 64;
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 3 + 1)] = 0; for (let x = 0; x < w; x++) { const o = y * (w * 3 + 1) + 1 + x * 3; raw[o] = 200; raw[o + 1] = 120; raw[o + 2] = 60; } }
  const crcTable = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (b: Buffer) => { let c = 0xffffffff; for (const x of b) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (t: string, d: Buffer) => { const len = Buffer.alloc(4); len.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

test("private UPI -> order -> thank-you shows it -> says paid with UTR + screenshot -> owner marks Paid", async ({ page, browser }) => {
  test.setTimeout(300_000);
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique("s20");
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const upi = biz.profile.upi_id as string;
  expect(upi).toBeTruthy();
  const saved = await api(page, "PUT", `/api/businesses/${id}`, {
    profile: { ...biz.profile, selling_mode: "pickup", payment_terms: "upfront" }, subdomain: slug,
  });
  expect(saved.status(), await saved.text()).toBe(200);
  await launch(page, id, true);

  const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost") });
  const customer = await ctx.newPage();
  const csp: string[] = [];
  customer.on("console", (m) => { if (/Content Security Policy|Refused to/i.test(m.text())) csp.push(m.text()); });
  await customer.setViewportSize({ width: 390, height: 800 });
  await customer.goto(shopUrl(slug));
  // The shop page says how payment works and never shows the UPI details.
  await expect(customer.locator("#paying")).toContainText("UPI");
  const html = await customer.content();
  expect(html).not.toContain(upi);
  expect(html.toLowerCase()).not.toContain("upi://");
  await expect(customer.getByLabel("UPI payment QR code")).toHaveCount(0);

  await customer.locator(".item .add").first().click();
  await customer.locator("#customer_name").fill("Riya Payer");
  await customer.locator("#customer_phone").fill("98765 43210");
  await pickDate(customer);
  await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await customer.waitForLoadState("load");
  await expect(customer.getByRole("heading", { name: /Thank you, Riya Payer/ })).toBeVisible();
  const href = await customer.getByRole("link", { name: "open your UPI app" }).getAttribute("href");
  expect(href).toMatch(/^upi:\/\/pay\?/);
  expect(href).toMatch(/am=\d+\.00/);

  // "I've paid": a plain form (works without JavaScript). A wrong number is refused with a plain sentence.
  await customer.locator("#utr").fill("1234");
  await customer.locator("#shot").setInputFiles({ name: "pay.png", mimeType: "image/png", buffer: png() });
  await customer.getByRole("button", { name: "I've paid" }).click();
  await expect(customer.getByRole("alert")).toContainText("12-digit");
  await customer.locator("#utr").fill("7319 0826 5514");
  await customer.locator("#shot").setInputFiles({ name: "pay.png", mimeType: "image/png", buffer: png() });
  await customer.getByRole("button", { name: "I've paid" }).click();
  await expect(customer.getByText("You told the shop you paid")).toBeVisible();
  await expect(customer.locator("#claim")).toContainText("ending 5514");
  await expect(customer.locator("#claim")).toContainText("not marked paid");
  expect(await customer.locator("body").innerText()).not.toContain("7319 0826 5514");
  expect(csp, csp.join("\n")).toEqual([]);
  await ctx.close();

  // The owner: "Customer says paid", the screenshot, then SHE marks it Paid.
  await page.goto(`/#/b/${id}/orders`);
  const card = page.locator(".order-card", { hasText: "Riya Payer" });
  await expect(card.getByTestId("payment-claim")).toContainText("Customer says paid · UTR 7319 0826 5514");
  await expect(card.locator(".order-pay")).not.toContainText(/^Paid|Fully paid/);
  const shot = card.getByRole("link", { name: "View screenshot" });
  await expect(shot).toBeVisible();
  const img = await page.request.get((await shot.getAttribute("href"))!);
  expect(img.status()).toBe(200);
  expect(img.headers()["content-type"]).toBe("image/webp");
  expect(img.headers()["cache-control"]).toContain("no-store");
  await card.getByRole("button", { name: "Mark confirmed" }).click();
  await expect(card.getByRole("button", { name: /received|Paid/ }).first()).toBeVisible();
  await card.getByRole("button", { name: /received|Paid/ }).first().click();
  await expect(card.locator(".order-pay")).toContainText(/paid/i);
});
