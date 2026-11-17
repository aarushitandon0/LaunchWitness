// S13 flows on the real stack: (1) an order placed while email is down is kept, shows "retrying" on the Orders page
// and becomes "sent" once mail works again (the team's practice "mail down" switch: pretend mail server only);
// (2) a sign-in link asked for while the mail server is unreachable says "We're having trouble sending email" (never
// "sent"), and the link still arrives once mail is back (local Docker stack only: the test stops/starts Mailpit).
import { execFileSync } from "child_process";
import { expect, test, type Page } from "@playwright/test";
import { ADMIN_EMAIL, api, BASE, describe, launch, MAIL, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

const MAILPIT = process.env.LW_MAILPIT_CONTAINER || "launchwitness-local-mailpit-1";

async function emailLine(page: Page, id: number, name: string): Promise<string> {
  await page.goto(`/#/b/${id}/orders`);
  await page.reload(); // the same hash URL doesn't reload the app: fetch the orders again
  const card = page.locator(".order-card", { hasText: name });
  await expect(card).toBeVisible();
  return (await card.locator(".order-email").innerText()).trim();
}

async function setMailDown(page: Page, down: boolean) {
  const r = await api(page, "PUT", "/api/admin/practice-mail", { down });
  expect(r.status(), await r.text()).toBe(200);
  expect((await r.json()).down).toBe(down);
}

test("an order placed while email is down is kept, retried, then sent", async ({ page, browser }) => {
  test.setTimeout(300_000);
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique("s13");
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  await launch(page, id, true); // pretend GoDaddy on this stack; the shop is served through Caddy

  await setMailDown(page, true);
  try {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost") });
    const customer = await ctx.newPage();
    await customer.goto(shopUrl(slug));
    await customer.locator(".item .add").first().click();
    await customer.locator("#customer_name").fill("Kavya Outbox");
    await customer.locator("#customer_phone").fill("98765 43210");
    await pickDate(customer);
    await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
    await customer.waitForLoadState("load");
    // The customer is told the order is in, whatever the mail server does.
    await expect(customer.getByText(/thank you|order is with/i).first()).toBeVisible();
    await ctx.close();

    expect(await emailLine(page, id, "Kavya Outbox")).toMatch(/^Email to you: retrying/);
  } finally {
    await setMailDown(page, false);
  }
  // Backoff 30 s (+-20%) then the 20 s sender job: "sent" within about a minute.
  await expect.poll(() => emailLine(page, id, "Kavya Outbox"), { timeout: 150_000, intervals: [5_000] })
    .toBe("Email to you: sent");
  const orders = await (await api(page, "GET", `/api/businesses/${id}/orders`)).json();
  expect(orders.find((o: { customer_name: string }) => o.customer_name === "Kavya Outbox").email_status).toBe("sent");
});

function docker(...args: string[]) {
  execFileSync("docker", args, { stdio: "ignore", timeout: 60_000 });
}

function mailpitRunning(): boolean {
  try {
    return execFileSync("docker", ["inspect", "-f", "{{.State.Running}}", MAILPIT], { timeout: 10_000 }).toString().trim() === "true";
  } catch {
    return false;
  }
}

test("sign-in while the mail server is down says so, then the link arrives", async ({ page }) => {
  test.skip(!MAIL || !BASE.includes("launchwitness.localhost") || !mailpitRunning(),
    "needs the local Docker stack (it stops and starts the Mailpit container)");
  test.setTimeout(300_000);
  const email = `${unique("slowmail")}@example.test`;
  docker("stop", MAILPIT);
  try {
    await page.goto("/#/signin");
    await page.getByPlaceholder("you@gmail.com").fill(email);
    await page.getByRole("button", { name: "Email me a link" }).click();
    await expect(page.getByRole("heading", { name: "Your email is on its way, slowly" })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("status")).toContainText("We're having trouble sending email");
    await expect(page.getByRole("heading", { name: "Check your email" })).toHaveCount(0);
    await expect(page.getByText(/\bsent\b/i)).toHaveCount(0);
  } finally {
    docker("start", MAILPIT);
  }
  // The outbox keeps trying: the link arrives once Mailpit is back (backoff 30 s + the 20 s job).
  await expect.poll(async () => {
    const r = await page.request.get(`${MAIL}/api/v1/search?query=${encodeURIComponent(`to:"${email}"`)}`).catch(() => null);
    if (!r || !r.ok()) return 0;
    return ((await r.json()).messages || []).length;
  }, { timeout: 150_000, intervals: [5_000] }).toBeGreaterThan(0);
});
