import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, api, describe, launch, setAddress, signIn, unique } from "./helpers";

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
  await expect(incident).toContainText("Your address leads to your website");
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
  await page.getByRole("button", { name: "Check with this in mind" }).click();
  await expect(page.getByText("Checking now.")).toBeVisible();
  await waitForRun(page, id, before);
  await page.reload();
  await expect(page.locator(".doctor-found").first()).toContainText("You said your shop doesn't open", { timeout: 30_000 });
  await expect(page.getByText(/4 left today/)).toBeVisible();
});
