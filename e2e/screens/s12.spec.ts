// S12 screenshots: the report after a staged fault (Doctor timeline, incident, symptom box, demo switch),
// the shared report (timeline + receipt + Verify), the landing hop track and watch strip, at 375/1440/1917.
// Run: npx playwright test -c screens.config.ts s12   (LW_SHOTS=<dir> to redirect; default docs/screenshots/s12)
import { expect, test, type Browser, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { ADMIN_EMAIL, api, describe, launch, setAddress, signIn, unique } from "../tests/helpers";

const OUT = process.env.LW_SHOTS || path.join(__dirname, "..", "..", "docs", "screenshots", "s12");
const SIZES: [number, number][] = [[375, 812], [1440, 900], [1917, 791]];
const ONLY = process.env.LW_SHOTS_ONLY || ""; // "report" | "landing" | "" (both)

async function page(browser: Browser, w: number, h: number, state?: string): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, ignoreHTTPSErrors: true, storageState: state });
  return ctx.newPage();
}

test("S12 report screens", async ({ browser }) => {
  test.skip(ONLY === "landing");
  test.setTimeout(300_000);
  fs.mkdirSync(OUT, { recursive: true });
  const admin = await page(browser, 1440, 900);
  await signIn(admin, ADMIN_EMAIL);
  const id = await describe(admin);
  await setAddress(admin, id, unique("meera"));
  await launch(admin, id, false);
  const before = (await (await api(admin, "GET", `/api/businesses/${id}/report`)).json()).run.id;
  expect((await api(admin, "PUT", `/api/admin/businesses/${id}/demo-fault`, { fault: "a_record" })).status()).toBe(200);
  expect((await api(admin, "POST", `/api/businesses/${id}/checks`)).status()).toBe(202);
  await expect
    .poll(async () => {
      const r = await (await api(admin, "GET", `/api/businesses/${id}/report`)).json();
      return r.run.id > before && r.run.status === "done";
    })
    .toBe(true);
  expect((await api(admin, "PUT", `/api/admin/businesses/${id}/demo-fault`, { fault: "smtp_login" })).status()).toBe(200);
  expect((await api(admin, "POST", `/api/businesses/${id}/checks`)).status()).toBe(202);
  await expect
    .poll(async () => (await (await api(admin, "GET", `/api/businesses/${id}/report`)).json()).run.status, { timeout: 60_000 })
    .toBe("done");
  const share = (await (await api(admin, "POST", `/api/businesses/${id}/share`)).json()).url as string;
  const state = path.join(OUT, ".state.json");
  await admin.context().storageState({ path: state });
  await admin.context().close();
  for (const [w, h] of SIZES) {
    const p = await page(browser, w, h, state);
    await p.goto(`/#/b/${id}/report`);
    await expect(p.locator(".doctor-found").first()).toBeVisible({ timeout: 30_000 });
    await p.locator(".checks details.tech-details").first().evaluate((d) => ((d as HTMLDetailsElement).open = true));
    await p.waitForTimeout(500);
    await p.screenshot({ path: path.join(OUT, `10-report-${w}.png`), fullPage: true });
    await p.goto(share.replace(/^https?:\/\/[^/]+/, ""));
    await p.getByRole("button", { name: "Verify" }).click();
    await expect(p.getByText(/^Intact/)).toBeVisible();
    await p.screenshot({ path: path.join(OUT, `11-shared-report-${w}.png`), fullPage: true });
    await p.context().close();
  }
  fs.rmSync(state, { force: true });
});

test("S12 landing screens", async ({ browser }) => {
  test.skip(ONLY === "report");
  test.setTimeout(240_000);
  fs.mkdirSync(OUT, { recursive: true });
  for (const [w, h] of SIZES) {
    const p = await page(browser, w, h);
    await p.goto("/#proof");
    await p.waitForTimeout(1200);
    await p.locator("#proof").screenshot({ path: path.join(OUT, `01-proof-before-${w}.png`) });
    await p.getByRole("button", { name: "Send a test order" }).click();
    await expect(p.getByRole("button", { name: "Send it again" })).toBeVisible({ timeout: 10_000 });
    await p.getByRole("button", { name: /Order form/ }).click();
    await p.waitForTimeout(700);
    await p.locator("#proof").screenshot({ path: path.join(OUT, `02-proof-sent-${w}.png`) });
    await p.locator("#watch").scrollIntoViewIfNeeded();
    await p.getByRole("button", { name: "Something breaks", exact: true }).click();
    await expect(p.getByRole("button", { name: "Play it again" })).toBeVisible({ timeout: 15_000 });
    await p.waitForTimeout(500);
    await p.locator("#watch").screenshot({ path: path.join(OUT, `03-watch-broke-${w}.png`) });
    await p.context().close();
  }
});

/** A simple "product photo" drawn in the browser (no binary files in the repo): a cake-like shape on a warm background. */
async function drawnPhoto(p: Page, hue: number): Promise<Buffer> {
  const bytes = await p.evaluate(async (h) => {
    const c = document.createElement("canvas");
    c.width = 1600;
    c.height = 1200;
    const g = c.getContext("2d")!;
    const bg = g.createLinearGradient(0, 0, 1600, 1200);
    bg.addColorStop(0, `hsl(${h}, 55%, 88%)`);
    bg.addColorStop(1, `hsl(${h + 20}, 45%, 70%)`);
    g.fillStyle = bg;
    g.fillRect(0, 0, 1600, 1200);
    g.fillStyle = "rgba(0,0,0,.12)";
    g.beginPath();
    g.ellipse(800, 930, 520, 90, 0, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = `hsl(${h - 10}, 60%, 45%)`;
    g.fillRect(380, 520, 840, 400);
    g.fillStyle = "#fff6ea";
    g.fillRect(380, 500, 840, 60);
    for (let i = 0; i < 7; i++) {
      g.fillStyle = `hsl(${(h + i * 40) % 360}, 70%, 55%)`;
      g.beginPath();
      g.arc(450 + i * 117, 470, 34, 0, Math.PI * 2);
      g.fill();
    }
    const blob: Blob = await new Promise((r) => c.toBlob((b) => r(b!), "image/jpeg", 0.88));
    return Array.from(new Uint8Array(await blob.arrayBuffer()));
  }, hue);
  return Buffer.from(bytes);
}

test("S12 shop with photos + recordings", async ({ browser }) => {
  test.skip(ONLY === "report" || ONLY === "landing");
  test.setTimeout(300_000);
  fs.mkdirSync(OUT, { recursive: true });
  const owner = await page(browser, 1440, 900);
  await signIn(owner, ADMIN_EMAIL);
  const id = await describe(owner);
  await setAddress(owner, id, unique("meera"));
  await owner.goto(`/#/b/${id}`);
  const shopInput = owner.getByLabel("Add a shop photo");
  for (const hue of [20, 340, 45]) {
    const n = await owner.locator(".photo-grid img").count();
    await shopInput.setInputFiles({ name: "p.jpg", mimeType: "image/jpeg", buffer: await drawnPhoto(owner, hue) });
    await expect(owner.locator(".photo-grid img")).toHaveCount(n + 1);
  }
  for (const [i, hue] of [[0, 15], [1, 300]] as [number, number][]) {
    const name = (await owner.locator(".product").nth(i).locator("input").first().inputValue()).trim();
    await owner.getByLabel(`Add a photo of ${name}`).setInputFiles({ name: "i.jpg", mimeType: "image/jpeg", buffer: await drawnPhoto(owner, hue) });
    await expect(owner.locator(".item-thumb")).toHaveCount(i + 1);
  }
  await owner.waitForTimeout(400);
  await owner.locator(".photos-card").screenshot({ path: path.join(OUT, "20-review-photos-1440.png") });
  const html = await (await api(owner, "GET", `/api/businesses/${id}/preview`)).text();
  const state = path.join(OUT, ".state2.json");
  await owner.context().storageState({ path: state });
  await owner.context().close();
  for (const [w, h] of [[375, 812], [1440, 900]] as [number, number][]) {
    const p = await page(browser, w, h, state);
    await p.goto("/"); // same origin, so the photos' /photos/... URLs resolve
    await p.setContent(html, { waitUntil: "load" });
    await p.evaluate(() => document.querySelectorAll("img").forEach((i) => i.setAttribute("loading", "eager")));
    await p.waitForTimeout(800);
    await p.screenshot({ path: path.join(OUT, `21-shop-with-photos-${w}.png`), fullPage: true });
    await p.context().close();
  }
  fs.rmSync(state, { force: true });

  // recordings of the two interactive sections (1440 wide)
  const rec = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true,
    recordVideo: { dir: OUT, size: { width: 1440, height: 900 } } });
  const v = await rec.newPage();
  await v.goto("/#proof");
  await v.waitForTimeout(1200);
  await v.getByRole("button", { name: "Send a test order" }).click();
  await v.waitForTimeout(4500);
  for (const hop of ["Address", "Your shop", "Mail server", "Your inbox"]) {
    await v.getByRole("button", { name: new RegExp(`^${hop}`) }).click();
    await v.waitForTimeout(1300);
  }
  await v.locator("#watch").scrollIntoViewIfNeeded();
  await v.evaluate(() => document.getElementById("watch")!.scrollIntoView({ block: "start" }));
  await v.waitForTimeout(800);
  const strip = v.getByRole("slider", { name: "Checks in an example day" });
  await strip.hover({ position: { x: 300, y: 30 } });
  await v.waitForTimeout(700);
  await strip.hover({ position: { x: 900, y: 30 } });
  await v.waitForTimeout(700);
  await v.getByRole("button", { name: "Something breaks", exact: true }).click();
  await v.waitForTimeout(7000);
  const video = v.video()!;
  await rec.close();
  fs.renameSync(await video.path(), path.join(OUT, "30-proof-and-watch-1440.webm"));
});
