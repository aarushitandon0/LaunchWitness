// (a) sign up -> pending -> team approves -> describe -> practice launch -> real launch (pretend GoDaddy on this
// server) -> a customer order through the public shop -> report -> share link opened logged out.
import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, api, approveUser, BASE, describe, launch, me, newSignedIn, pickDate, readyForReal, setAddress, shopUrl, statusOf, unique } from "./helpers";

test("a seller goes from sign-up to a live, proven, shared shop", async ({ browser }) => {
  const sellerCtx = await browser.newContext();
  const email = `${unique("seller")}@example.test`;
  const seller = await newSignedIn(sellerCtx, email);

  // The session cookie: __Host- prefixed, Secure, HttpOnly, SameSite=Lax, no Domain (on https).
  const cookies = await sellerCtx.cookies();
  const session = cookies.find((c) => c.name.endsWith("lw_session"))!;
  expect(session).toBeTruthy();
  if (BASE.startsWith("https://")) {
    expect(session.name).toBe("__Host-lw_session");
    expect(session.secure).toBe(true);
    expect(session.domain).toBe(new URL(BASE).hostname); // host-only: no Domain attribute was sent
  }
  expect(session.httpOnly).toBe(true);
  expect(session.sameSite).toBe("Lax");

  // New accounts wait for the team.
  expect((await me(seller)).user.status).toBe("pending");
  const id = await describe(seller);
  const slug = unique("e2e");
  await setAddress(seller, id, slug);
  const early = await api(seller, "POST", `/api/businesses/${id}/plans`, { mode: "sandbox", real: true });
  expect(early.status()).toBe(403); // pending: practice only

  // Practice launch: always labelled.
  await launch(seller, id, false);
  const practice = await (await api(seller, "GET", `/api/businesses/${id}/report`)).json();
  expect(practice.practice).toBe(true);
  await seller.goto(`/#/b/${id}/report`);
  await expect(seller.getByText(/practice/i).first()).toBeVisible();

  // The team approves the account.
  const adminCtx = await browser.newContext();
  const admin = await newSignedIn(adminCtx, ADMIN_EMAIL);
  expect((await me(admin)).user.role).toBe("admin");
  await approveUser(admin, email);
  await expect.poll(async () => (await me(seller)).user.status).toBe("approved");

  // Real launch needs the go-live checklist: the Launch page says what's missing and holds the button.
  await seller.goto(`/#/b/${id}/launch`);
  await expect(seller.getByText("Before your shop can go live, please finish:")).toBeVisible();
  await expect(seller.getByRole("button", { name: "Launch for real" })).toBeDisabled();
  const refused = await api(seller, "POST", `/api/businesses/${id}/plans`, { mode: "sandbox", real: true });
  expect(refused.status()).toBe(409); // the server decides, not the button
  await readyForReal(seller, id);
  await seller.reload();
  await expect(seller.getByRole("button", { name: "Launch for real" })).toBeEnabled();

  // Real launch (on this server GoDaddy is pretend; the shop really is served through Caddy).
  await launch(seller, id, true);
  const rep = await (await api(seller, "GET", `/api/businesses/${id}/report`)).json();
  expect(rep.run.status).toBe("done");
  expect(rep.proof.proven).toBeGreaterThan(0);

  // A customer, logged out, on the shop's own address.
  const customerCtx = await browser.newContext();
  const customer = await customerCtx.newPage();
  const res = await customer.goto(shopUrl(slug));
  expect(res!.status()).toBe(200);
  await expect(customer.locator('meta[name="lw-shop"]')).toHaveAttribute("content", /.+/);
  const probe = await customerCtx.newPage();
  for (const p of ["api/health", "internal/tls-ask?domain=x", "build", "assets/x.js", "r/abc"]) {
    expect(await statusOf(probe, shopUrl(slug) + p), `shop host must not serve /${p}`).toBe(404);
  }
  await customer.locator(".item .add").first().click(); // the basket script replaces the plain quantity box
  await customer.locator("#customer_name").fill("Riya E2E");
  await customer.locator("#customer_phone").fill("98765 43210");
  await pickDate(customer);
  await customer.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await customer.waitForLoadState("load");
  await expect(customer.getByText(/thank you|order is with/i).first()).toBeVisible();

  // The seller sees the order; the hidden test orders aren't in the list.
  const orders = await (await api(seller, "GET", `/api/businesses/${id}/orders`)).json();
  expect(orders.some((o: { customer_name: string }) => o.customer_name === "Riya E2E")).toBe(true);
  // My shops counts it as new; the Orders page shows it with a WhatsApp link to the customer; she confirms it.
  await seller.goto("/#/shops");
  await expect(seller.getByText("1 new")).toBeVisible();
  await seller.getByRole("link", { name: /Orders/ }).first().click();
  await expect(seller).toHaveURL(new RegExp(`#/b/${id}/orders$`));
  const card = seller.locator(".order-card", { hasText: "Riya E2E" });
  await expect(card.getByRole("link", { name: "Message on WhatsApp" })).toHaveAttribute("href", /^https:\/\/wa\.me\/919876543210\?text=/);
  await card.getByRole("button", { name: "Mark confirmed" }).click();
  await expect(card.locator(".order-status")).toHaveText("Confirmed");

  // Report page, then a share link opened by someone logged out: read-only, no customer data.
  await seller.goto(`/#/b/${id}/report`);
  await expect(seller.getByRole("heading").first()).toBeVisible();
  const share = await (await api(seller, "POST", `/api/businesses/${id}/share`)).json();
  const stranger = await (await browser.newContext()).newPage();
  const shared = await stranger.goto(share.url.replace(/^https?:\/\/[^/]+/, BASE));
  expect(shared!.status()).toBe(200);
  const html = await stranger.content();
  expect(html).not.toContain("Riya E2E");
  expect(html).not.toContain("98765");
  expect(html).toMatch(/practice|pretend/i); // this server's GoDaddy is pretend: the page says so
});
