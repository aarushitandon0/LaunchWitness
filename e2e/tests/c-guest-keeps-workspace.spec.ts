// (c) A guest tries it without signing in, then signs in: the practice shop comes along.
import { expect, test } from "@playwright/test";
import { api, describe, me, signIn, unique } from "./helpers";

test("guest practice is kept after signing in", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const id = await describe(page);
  expect((await me(page)).guest).toBe(true);
  expect((await ctx.cookies()).some((c) => c.name.endsWith("lw_guest"))).toBe(true);

  await signIn(page, `${unique("guest")}@example.test`);
  const mine = await (await api(page, "GET", "/api/businesses")).json();
  expect(mine.some((x: { id: number }) => x.id === id)).toBe(true);
  expect((await api(page, "GET", `/api/businesses/${id}`)).status()).toBe(200);

  // Someone else (a fresh browser) can't take it over.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/");
  expect([401, 404]).toContain((await api(other, "GET", `/api/businesses/${id}`)).status());
});
