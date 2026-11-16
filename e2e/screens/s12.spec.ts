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
