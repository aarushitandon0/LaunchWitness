import { expect, test, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { ADMIN_EMAIL, api, describe, launch, setAddress, signIn, unique } from "./helpers";

// The symptom conversation's last saved answer (captured live in S13; it used to be a placeholder that echoed "You said").
const FIXTURES = path.join(__dirname, "..", "..", "backend", "tests", "fixtures", "claude");
const symptomFinding = (): string => {
  const last = fs.readdirSync(FIXTURES).filter((f) => /^investigate_site_points_symptom_t\d+\.json$/.test(f)).sort().pop()!;
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, last), "utf-8")).finding;
};

// S12 flows: a staged fault shows the Doctor's trace + the incident; the symptom box answers;
// the landing hop track and "Something breaks" play.

async function practiceShop(page: Page): Promise<number> {
  const id = await describe(page);
  await setAddress(page, id, unique("s12"));
  await launch(page, id, false);
  return id;
}

async function waitForRun(page: Page, id: number, after: number) {
  await expect
    .poll(async () => {
      const r = await (await api(page, "GET", `/api/businesses/${id}/report`)).json();
      return r.run && r.run.id > after && r.run.status === "done";
    }, { timeout: 60_000 })
    .toBe(true);
}

test("a staged fault shows the Doctor's trace and becomes one incident", async ({ page }) => {
  await signIn(page, ADMIN_EMAIL);
  const id = await practiceShop(page);
  const before = (await (await api(page, "GET", `/api/businesses/${id}/report`)).json()).run.id;
  await page.goto(`/#/b/${id}/report`);
  await page.getByRole("button", { name: /Address leads nowhere/ }).click();
  await expect(page.getByText(/Armed: address leads nowhere/)).toBeVisible();
  await page.getByRole("button", { name: "Run checks now" }).click();
  await waitForRun(page, id, before);
  await page.reload();
  const timeline = page.getByRole("list", { name: "What we did, in order" }).first();
  await expect(timeline).toContainText("Looked up where your address leads → it leads nowhere", { timeout: 30_000 });
  await expect(timeline).toContainText("Pointed your address at your shop again");
  await expect(timeline).toContainText("Checked again: working");
  const incident = page.locator(".incident").first();
  // The incident card shows once the reloaded report has replayed the run; 5 s could lose that race.
  await expect(incident).toContainText("Your address leads to your website", { timeout: 30_000 });
  await expect(incident).toContainText("Fixed");
});

test("the symptom box answers", async ({ page }) => {
  await signIn(page, ADMIN_EMAIL);
  const id = await practiceShop(page);
  const before = (await (await api(page, "GET", `/api/businesses/${id}/report`)).json()).run.id;
  await page.goto(`/#/b/${id}/report`);
  await page.getByRole("button", { name: /Address leads nowhere/ }).click();
  await page.getByRole("button", { name: "My shop doesn't open" }).click();
  await expect(page.getByLabel("What went wrong")).toHaveValue("My shop doesn't open");
  const left = Number((await page.getByText(/left today/).innerText()).match(/\d+/)![0]);
  await page.getByRole("button", { name: "Check with this in mind" }).click();
  await expect(page.getByText("Checking now.")).toBeVisible();
  await waitForRun(page, id, before);
  await page.reload();
  await expect(page.locator(".doctor-found").first()).toContainText(symptomFinding(), { timeout: 30_000 });
  // The box is hidden while the reloaded report replays the run check by check; 5 s could lose that race.
  await expect(page.getByText(new RegExp(`${left - 1} left today|None left today`))).toBeVisible({ timeout: 30_000 });
});

test("the hop track plays and a hop opens its panel (keyboard too)", async ({ page }) => {
  await page.goto("/#proof");
  const track = page.locator("#proof");
  await track.getByRole("button", { name: "Send a test order" }).click();
  await expect(track.getByRole("button", { name: "Send it again" })).toBeVisible({ timeout: 10_000 });
  await expect(track.locator(".hoptrack-hop.done")).toHaveCount(6);
  await expect(track.getByText("Example").first()).toBeVisible();
  await expect(track.getByText("proven when you tap")).toBeVisible();
  await track.getByRole("button", { name: /Mail server/ }).focus();
  await expect(track.locator(".hoppanel-card")).toContainText("our mail service refused our own sign-in");
  await page.keyboard.press("Tab");
  await expect(track.locator(".hoppanel-card")).toContainText("Your inbox");
  await track.getByRole("button", { name: /^Address/ }).click();
  await expect(track.locator(".hoppanel-card")).toContainText("We pointed your address at your shop again");
});

test("“Something breaks” plays the monitor's real sequence", async ({ page }) => {
  await page.goto("/#watch");
  const sec = page.locator("#watch");
  await sec.getByRole("button", { name: "Something breaks", exact: true }).click();
  const seq = sec.getByRole("list", { name: "What happens when something breaks" });
  await expect(seq).toContainText("We check again a minute later", { timeout: 10_000 });
  await expect(seq).toContainText("Checked again: working", { timeout: 10_000 });
  await expect(seq).toContainText("No email this time", { timeout: 10_000 });
  const strip = sec.getByRole("slider", { name: "Checks in an example day" });
  await strip.focus();
  await page.keyboard.press("Home");
  await expect(strip).toHaveAttribute("aria-valuetext", /^00:00: Quick check/);
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });
  test("both sections jump straight to the end state", async ({ page }) => {
    await page.goto("/#proof");
    await page.locator("#proof").getByRole("button", { name: "Send a test order" }).click();
    await expect(page.locator("#proof .hoptrack-hop.done")).toHaveCount(6);
    await page.locator("#watch").getByRole("button", { name: "Something breaks", exact: true }).click();
    await expect(page.locator("#watch .bs")).toHaveCount(6);
  });
});

test("a photo uploaded on Review shows on the shop, re-encoded", async ({ page }) => {
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  await setAddress(page, id, unique("photo"));
  await page.goto(`/#/b/${id}`);
  // a real JPEG made in the browser (canvas), so nothing binary lives in the repo
  const jpeg = await page.evaluate(async () => {
    const c = document.createElement("canvas");
    c.width = 900;
    c.height = 600;
    const g = c.getContext("2d")!;
    g.fillStyle = "#c97b4a";
    g.fillRect(0, 0, 900, 600);
    g.fillStyle = "#fff";
    g.fillRect(300, 200, 300, 200);
    const blob: Blob = await new Promise((r) => c.toBlob((b) => r(b!), "image/jpeg", 0.9));
    return Array.from(new Uint8Array(await blob.arrayBuffer()));
  });
  const buffer = Buffer.from(jpeg);
  await page.getByLabel("Add a shop photo").setInputFiles({ name: "cake.jpg", mimeType: "image/jpeg", buffer });
  await expect(page.locator(".photo-grid img")).toHaveCount(1);
  const src = await page.locator(".photo-grid img").getAttribute("src");
  expect(src).toMatch(/^\/photos\/[0-9a-f]{32}-480\.webp$/);
  // fetched by the browser (Node can't resolve *.localhost)
  const r = await page.evaluate(async (u) => {
    const res = await fetch(u);
    const b = new Uint8Array(await res.arrayBuffer());
    return { status: res.status, type: res.headers.get("content-type"), cache: res.headers.get("cache-control"),
      riff: String.fromCharCode(...b.slice(0, 4)) + String.fromCharCode(...b.slice(8, 12)) };
  }, src!);
  expect(r).toEqual({ status: 200, type: "image/webp", cache: "public, max-age=31536000, immutable", riff: "RIFFWEBP" });
  const first = (await page.locator(".product input").first().inputValue()).trim();
  await page.getByLabel(`Add a photo of ${first}`).setInputFiles({ name: "item.jpg", mimeType: "image/jpeg", buffer });
  await expect(page.locator(".item-thumb")).toHaveCount(1);
  // the owner's preview shows both, lazy and sized
  const html = await (await api(page, "GET", `/api/businesses/${id}/preview`)).text();
  // S14: the first shop photo is the hero image (large, loaded at once); the item's photo is a lazy thumbnail card
  expect(html).toContain(`src="${src!.replace("-480", "-1200")}"`);
  expect(html).toContain('fetchpriority="high"');
  expect(html).toContain('class="thumb"');
  expect((html.match(/loading="lazy"/g) || []).length).toBe(1);
});
