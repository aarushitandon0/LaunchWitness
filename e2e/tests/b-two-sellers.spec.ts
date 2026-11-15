// (b) Two sellers in two browsers can't reach each other's shops, reports, orders, previews or share links by URL.
import { expect, test } from "@playwright/test";
import { api, describe, newSignedIn, setAddress, unique } from "./helpers";

test("seller B can't open anything of seller A's by URL", async ({ browser }) => {
  const a = await newSignedIn(await browser.newContext(), `${unique("sellera")}@example.test`);
  const b = await newSignedIn(await browser.newContext(), `${unique("sellerb")}@example.test`);
  const id = await describe(a);
  await setAddress(a, id, unique("e2ea"));
  const share = await api(a, "POST", `/api/businesses/${id}/share`);
  expect(share.status()).toBe(200);

  const reads = ["", "/preview", "/orders", "/export", "/names", "/plans", "/report", "/share"];
  for (const p of reads) {
    expect((await api(a, "GET", `/api/businesses/${id}${p}`)).status(), `A reads own ${p}`).toBe(200);
    expect((await api(b, "GET", `/api/businesses/${id}${p}`)).status(), `B reads A's ${p}`).toBe(404);
  }
  const writes: [string, string, unknown][] = [
    ["PUT", "", { profile: {}, subdomain: "stolen-name" }],
    ["POST", "/plans", { mode: "sandbox" }],
    ["POST", "/checks", undefined],
    ["POST", "/share", undefined],
    ["DELETE", "/share", undefined],
    ["DELETE", "", undefined],
  ];
  for (const [method, p, data] of writes) {
    expect((await api(b, method, `/api/businesses/${id}${p}`, data)).status(), `B ${method} A's ${p}`).toBe(404);
  }
  // A's own list doesn't leak into B's, and A's shop still exists.
  const listB = await (await api(b, "GET", "/api/businesses")).json();
  expect(listB.some((x: { id: number }) => x.id === id)).toBe(false);
  expect((await api(a, "GET", `/api/businesses/${id}`)).status()).toBe(200);

  // The pages themselves: B gets "not found", never A's data.
  await b.goto(`/#/b/${id}/report`);
  await b.waitForLoadState("networkidle");
  await expect(b.getByText(/Meera/)).toHaveCount(0);
});
