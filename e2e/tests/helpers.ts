import { expect, type BrowserContext, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

export const BASE = process.env.LW_BASE || "https://launchwitness.localhost";
export const MAIL = process.env.LW_MAIL ?? (BASE.includes("launchwitness.localhost") ? "http://localhost:8025" : "");
export const ADMIN_EMAIL = process.env.LW_ADMIN_EMAIL || "admin@launchwitness.localhost";
const u = new URL(BASE);
export const APP_DOMAIN = u.hostname;
export const PORT = u.port ? `:${u.port}` : "";
export const shopUrl = (slug: string) => `${u.protocol}//${slug}.${APP_DOMAIN}${PORT}/`;

const SELLER = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "..", "backend", "tests", "fixtures", "sellers", "meera_cakes.json"), "utf-8"),
);

export const unique = (prefix: string) => `${prefix}${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`;

/** Latest email to `to` in Mailpit (the local stack's catch-all). */
async function mailTo(page: Page, to: string, after: number): Promise<string> {
  for (let i = 0; i < 40; i++) {
    const r = await page.request.get(`${MAIL}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const msgs = (await r.json()).messages || [];
    const fresh = msgs.find((m: { Created: string }) => Date.parse(m.Created) >= after - 2000);
    if (fresh) {
      const full = await (await page.request.get(`${MAIL}/api/v1/message/${fresh.ID}`)).json();
      return full.Text as string;
    }
    await page.waitForTimeout(500);
  }
  throw new Error(`no email to ${to} in Mailpit`);
}

/** Sign in through the real pages: ask for a link, open it, press "Sign in". */
export async function signIn(page: Page, email: string, opts: { stay?: boolean } = {}): Promise<void> {
  const started = Date.now();
  if (!opts.stay) await page.goto("/#/signin"); // stay: already on the sign-in page (e.g. sent there by "Start")
  await page.getByPlaceholder("you@gmail.com").fill(email);
  await page.getByRole("button", { name: "Email me a link" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  let link: string;
  if (MAIL) {
    const text = await mailTo(page, email, started);
    const m = text.match(/https?:\/\/\S+#\/signin\/confirm\?token=[\w-]+\S*/);
    expect(m, "the email carries a sign-in link").toBeTruthy();
    link = m![0];
  } else {
    link = BASE + (await page.getByRole("link", { name: "Open the sign-in link" }).getAttribute("href"))!;
  }
  await page.goto(link);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect.poll(async () => (await me(page)).user?.email).toBe(email);
}

/** The answer to an API call made by the page itself. */
export class Res {
  constructor(private code: number, private body: string) {}
  status() { return this.code; }
  text() { return Promise.resolve(this.body); }
  json() { return Promise.resolve(JSON.parse(this.body)); }
}

async function onApp(page: Page) {
  if (!page.url().startsWith(BASE)) await page.goto("/");
}

/** An API call made by the page with fetch(), exactly like our frontend: the browser's own cookies and Origin,
 * plus the CSRF token from /api/auth/me. (Node can't resolve *.localhost on Windows; the browser can.) */
export async function api(page: Page, method: string, url: string, data?: unknown): Promise<Res> {
  await onApp(page);
  const [code, body] = await page.evaluate(
    async ([method, url, data]) => {
      const m = await (await fetch("/api/auth/me", { credentials: "same-origin" })).json();
      const headers: Record<string, string> = {};
      if (m.csrf) headers["X-CSRF-Token"] = m.csrf;
      if (data !== null) headers["Content-Type"] = "application/json";
      const r = await fetch(url as string, {
        method: method as string, headers, credentials: "same-origin",
        body: data === null ? undefined : JSON.stringify(data),
      });
      return [r.status, await r.text()] as [number, string];
    },
    [method, url, data === undefined ? null : data] as const,
  );
  return new Res(code, body);
}

export async function me(page: Page) {
  return (await api(page, "GET", "/api/auth/me")).json();
}

/** Status code of a GET to any URL, made by the browser (a top-level navigation). */
export async function statusOf(page: Page, url: string): Promise<number> {
  const r = await page.goto(url);
  return r ? r.status() : 0;
}

/** Describe the business on the real page; returns the new shop id. Signed in: #/new. Guest: #/try (no account). */
export async function describe(page: Page, opts: { guest?: boolean; here?: boolean } = {}): Promise<number> {
  if (!opts.here) await page.goto(opts.guest ? "/#/try" : "/#/new");
  await expect(page.getByRole("heading", { name: "Describe your business" })).toBeVisible();
  await page.getByLabel("About your business").fill(SELLER.description);
  await page.getByLabel("Price list", { exact: true }).fill(SELLER.price_list);
  await page.getByRole("button", { name: "Make my website" }).click();
  await page.waitForURL(/#\/b\/\d+$/);
  return Number(page.url().match(/#\/b\/(\d+)/)![1]);
}

export async function setAddress(page: Page, id: number, slug: string) {
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const r = await api(page, "PUT", `/api/businesses/${id}`, { profile: biz.profile, subdomain: slug });
  expect(r.status(), await r.text()).toBe(200);
}

export async function launch(page: Page, id: number, real: boolean) {
  const r = await api(page, "POST", `/api/businesses/${id}/plans`, { mode: "sandbox", real });
  expect(r.status(), await r.text()).toBe(201);
  const plan = await r.json();
  const a = await api(page, "POST", `/api/plans/${plan.id}/approve`, { approved_by: "e2e" });
  expect(a.status(), await a.text()).toBe(200);
  await expect
    .poll(async () => (await (await api(page, "GET", `/api/plans/${plan.id}`)).json()).status, { timeout: 60_000 })
    .toBe("done");
  // checks run right after the plan: wait for the report to have a finished run
  await expect
    .poll(async () => (await (await api(page, "GET", `/api/businesses/${id}/report`)).json()).run?.status, { timeout: 60_000 })
    .toBe("done");
  return plan.id as number;
}

export async function newSignedIn(context: BrowserContext, email: string): Promise<Page> {
  const page = await context.newPage();
  await signIn(page, email);
  return page;
}

export async function approveUser(admin: Page, email: string) {
  const users = await (await api(admin, "GET", "/api/admin/users")).json();
  const user = users.find((x: { email: string }) => x.email === email);
  expect(user, `user ${email} is listed for the team`).toBeTruthy();
  const r = await api(admin, "POST", `/api/admin/users/${user.id}/approve`);
  expect(r.status(), await r.text()).toBe(200);
}

/** The S10.5 go-live checklist, done as the owner would (details, preview, WhatsApp + UPI checks, two promises). */
export async function readyForReal(page: Page, id: number) {
  const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
  const profile = {
    ...biz.profile, whatsapp: "98765 43210", upi_id: "meera.cakes@okaxis", upi_display_name: "Meera Joshi",
    pickup_available: true, area: "Baner, Pune", delivery_areas: "Baner, Aundh", hours: "Tue-Sun, 10am-7pm",
  };
  expect((await api(page, "PUT", `/api/businesses/${id}`, { profile, subdomain: biz.subdomain })).status()).toBe(200);
  expect((await api(page, "GET", `/api/businesses/${id}/preview`)).status()).toBe(200);
  for (const body of [{ what: "whatsapp" }, { what: "upi" }, { what: "agreements", own_goods: true, terms: true }]) {
    const r = await api(page, "POST", `/api/businesses/${id}/confirm`, body);
    expect(r.status(), await r.text()).toBe(200);
  }
  expect((await (await api(page, "GET", `/api/businesses/${id}/golive`)).json()).ready).toBe(true);
}
