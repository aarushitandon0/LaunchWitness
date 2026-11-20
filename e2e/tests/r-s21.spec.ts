// S21: items sold by size / pack, minimum, a required choice, "Sold out today", and the landing's demo-shop strip.
// LW_S21_SHOTS=<dir> also saves the screenshots for docs/screenshots/s21/ (390 and 1440 px).
import { Browser, expect, Page, test } from "@playwright/test";
import { ADMIN_EMAIL, api, BASE, describe, launch, pickDate, readyForReal, setAddress, shopUrl, signIn, unique } from "./helpers";

const SHOTS = process.env.LW_S21_SHOTS || "";
const shot = async (page: Page, name: string, target?: { screenshot: Page["screenshot"] }) => {
  if (SHOTS) await (target ?? page).screenshot({ path: `${SHOTS}/${name}.png` });
};
const COLOURS = ["Red", "Pink", "White", "Yellow"];
const CROCHET = [
  { name: "Crochet roses", price_inr: 40, category: "Flowers", description: "Hand-made, single stem", unit: "piece", min_qty: 5,
    choice_label: "Colour", choices: COLOURS },
  { name: "Crochet bouquet", price_inr: 260, category: "Bouquets", description: "Wrapped, with a ribbon", option_kind: "pack",
    options: [{ label: "6 roses", price_inr: 260 }, { label: "12 roses", price_inr: 480 }], choice_label: "Colour", choices: COLOURS },
];

/** A real (pretend GoDaddy) live shop from Meera's description; `products` replaces her menu when given. */
async function liveShop(page: Page, prefix: string, products?: unknown[]): Promise<{ id: number; slug: string }> {
  await signIn(page, ADMIN_EMAIL);
  const id = await describe(page);
  const slug = unique(prefix);
  await setAddress(page, id, slug);
  await readyForReal(page, id);
  if (products) {
    const biz = await (await api(page, "GET", `/api/businesses/${id}`)).json();
    const r = await api(page, "PUT", `/api/businesses/${id}`, {
      profile: { ...biz.profile, name: "Loops by Lata", products, section_copy: { hero_line: "Crochet flowers that last", about: "", how_ordering: "" } },
      subdomain: slug,
    });
    expect(r.status(), await r.text()).toBe(200);
  }
  await launch(page, id, true);
  return { id, slug };
}

async function customer(browser: Browser, width = 390, js = true) {
  const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), javaScriptEnabled: js,
    viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: SHOTS ? 2 : 1 });
  const page = await ctx.newPage();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || /Content Security Policy|Refused to/i.test(m.text())) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  return { ctx, page, errors };
}

test("Meera's truffle cake once with ½ kg / 1 kg; 1 x 1 kg + 2 x ½ kg; thank-you and Orders show both lines", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { id, slug } = await liveShop(page, "s21m");
  for (const width of [390, 1440]) {
    const { ctx, page: c, errors } = await customer(browser, width);
    await c.goto(shopUrl(slug));
    const cake = c.locator('li.item[data-item="Chocolate truffle cake"]');
    await expect(cake).toHaveCount(1);
    await expect(cake.locator(".price")).toHaveText(/from\s*₹650/);
    await expect(cake.locator(".opt-l")).toHaveText(["½ kg ₹650", "1 kg ₹1,200"]);
    await cake.scrollIntoViewIfNeeded();
    if (width === 390) {
      await cake.locator(".q.opt").nth(1).locator(".add").click();
      await cake.locator(".q.opt").nth(0).locator(".add").click();
      await cake.locator(".q.opt").nth(0).locator(".plus").click();
      await expect(c.locator("#basket")).toContainText("2 × Chocolate truffle cake · ½ kg");
      await expect(c.locator("#basket")).toContainText("1 × Chocolate truffle cake · 1 kg");
      await expect(c.locator("#total")).toHaveText("₹2,500");
      await c.evaluate(() => window.scrollBy(0, -70));
      await shot(c, "meera-item-row-390");
      await cake.locator(".qv-open").click();
      await expect(c.locator("dialog.qv")).toBeVisible();
      await expect(c.locator("dialog.qv .qv-chip")).toHaveCount(2);
      await c.waitForTimeout(400);
      await shot(c, "meera-quick-view-390");
      await c.locator("dialog.qv .qv-close").click();
      await c.locator("#customer_name").fill("Asha Rao");
      await c.locator("#customer_phone").fill("98765 43210");
      await pickDate(c);
      await c.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
      await c.waitForLoadState("load");
      await expect(c.getByRole("heading", { name: /^Thank you, Asha!$/ })).toBeVisible();
      await expect(c.locator(".basket")).toContainText("2 × Chocolate truffle cake · ½ kg");
      await expect(c.locator(".basket")).toContainText("1 × Chocolate truffle cake · 1 kg");
      await expect(c.locator(".total")).toContainText("₹2,500");
    } else {
      await c.evaluate(() => window.scrollBy(0, -70));
      await shot(c, "meera-item-row-1440");
      await cake.locator(".qv-open").click();
      await c.waitForTimeout(400);
      await shot(c, "meera-quick-view-1440");
    }
    expect(errors, errors.join("\n")).toEqual([]);
    await ctx.close();
  }
  await page.goto(`/#/b/${id}/orders`);
  const card = page.locator(".order-card", { hasText: "Asha Rao" });
  await expect(card).toContainText("2 × Chocolate truffle cake · ½ kg");
  await expect(card).toContainText("1 × Chocolate truffle cake · 1 kg");
  await expect(card.locator(".order-total")).toContainText("₹2,500");
});

test("JavaScript off: one box per size, the order goes through with the right total", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { slug } = await liveShop(page, "s21j");
  const { ctx, page: c } = await customer(browser, 390, false);
  await c.goto(shopUrl(slug));
  await c.locator("#qty_0_1").fill("1");
  await c.locator("#qty_0_0").fill("2");
  await c.locator("#customer_name").fill("Ravi Kumar");
  await c.locator("#customer_phone").fill("98765 43210");
  await pickDate(c);
  await c.locator("#customer_phone").press("Enter");
  await c.waitForLoadState("load");
  await expect(c.getByRole("heading", { name: /^Thank you, Ravi!$/ })).toBeVisible();
  await expect(c.locator(".basket")).toContainText("2 × Chocolate truffle cake · ½ kg");
  await expect(c.locator(".total")).toContainText("₹2,500");
  await ctx.close();
});

test("crochet roses: min 5 refused at 3, colour required, a bouquet by pack; Review options editor", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { id, slug } = await liveShop(page, "s21c", CROCHET);
  // Without JavaScript the server says what is wrong, in plain words, and keeps what she typed.
  const nojs = await customer(browser, 390, false);
  const c = nojs.page;
  await c.goto(shopUrl(slug));
  await expect(c.locator('li.item[data-item="Crochet roses"]')).toContainText("Min 5");
  await expect(c.locator('li.item[data-item="Crochet roses"] .price')).toContainText("₹40 per piece");
  await c.locator("#qty_0").fill("3");
  await c.locator("#choice_0").selectOption("Red");
  await c.locator("#customer_name").fill("Lata");
  await c.locator("#customer_phone").fill("98765 43210");
  await pickDate(c);
  await c.locator("#customer_phone").press("Enter");
  await c.waitForLoadState("load");
  await expect(c.getByRole("alert")).toContainText("Crochet roses: please order at least 5 (you chose 3)");
  await c.locator("#qty_0").fill("5");
  await c.locator("#choice_0").selectOption("");
  await pickDate(c);
  await c.locator("#customer_phone").press("Enter");
  await c.waitForLoadState("load");
  await expect(c.getByRole("alert")).toContainText("Please choose a colour for Crochet roses");
  await nojs.ctx.close();

  // With JavaScript: Add puts the minimum in, the colour box appears and is required, the basket shows the pick.
  const js = await customer(browser, 390);
  const p = js.page;
  await p.goto(shopUrl(slug));
  const roses = p.locator('li.item[data-item="Crochet roses"]');
  await expect(roses.locator(".choice")).toBeHidden();
  await roses.locator(".add").click();
  await expect(roses.locator("output")).toHaveText("5");
  await expect(roses.locator(".choice select")).toBeVisible();
  await roses.locator(".choice select").selectOption("Pink");
  const bouquet = p.locator('li.item[data-item="Crochet bouquet"]');
  await bouquet.locator(".q.opt").nth(1).locator(".add").click();
  await bouquet.locator(".choice select").selectOption("White");
  await expect(p.locator("#basket")).toContainText("5 × Crochet roses · Pink");
  await expect(p.locator("#basket")).toContainText("1 × Crochet bouquet · 12 roses · White");
  await expect(p.locator("#total")).toHaveText("₹680");
  await roses.scrollIntoViewIfNeeded();
  await p.evaluate(() => window.scrollBy(0, -70));
  await shot(p, "crochet-items-390");
  await p.locator("#customer_name").fill("Meena");
  await p.locator("#customer_phone").fill("98765 43210");
  await pickDate(p);
  await p.locator("#order-form").evaluate((f: HTMLFormElement) => f.requestSubmit());
  await p.waitForLoadState("load");
  await expect(p.locator(".basket")).toContainText("1 × Crochet bouquet · 12 roses · White");
  expect(js.errors, js.errors.join("\n")).toEqual([]);
  await js.ctx.close();

  // The owner's Review page: each item has its sizes / minimum / choices editor.
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/#/b/${id}`);
    await page.reload(); // S21B: a hash-only goto keeps the app's in-memory copy of Meera's menu from describe()
    const editor = page.locator(".product").nth(1).locator("details.sell-how");
    await editor.evaluate((d: HTMLDetailsElement) => { d.open = true; });
    await expect(editor.getByLabel("Item 2 size 2", { exact: true })).toHaveValue("12 roses");
    await expect(editor.getByLabel("Item 2 choice 4", { exact: true })).toHaveValue("Yellow");
    await editor.scrollIntoViewIfNeeded();
    await shot(page, `review-options-editor-${width}`, editor);
  }
});

test("Sold out today: one tap on Orders, no box on the shop, the server refuses it", async ({ page, browser }) => {
  test.setTimeout(300_000);
  const { id, slug } = await liveShop(page, "s21s");
  await page.goto(`/#/b/${id}/orders`);
  await page.locator("details.soldout summary").click();
  await page.getByRole("button", { name: "Pineapple cake: sold out today" }).click();
  await expect(page.getByRole("button", { name: "Pineapple cake: sold out today" })).toHaveAttribute("aria-pressed", "true");
  const { ctx, page: c } = await customer(browser, 390);
  await c.goto(shopUrl(slug));
  const row = c.locator('li.item[data-item="Pineapple cake"]');
  await expect(row).toContainText("Sold out today");
  await expect(row.locator("input")).toHaveCount(0);
  const index = await row.getAttribute("data-i");
  // A hand-made POST with a box for the sold-out item (the page has none): the page's own form carries it, since the
  // shop's CSP allows no fetch and Node can't resolve *.localhost.
  await c.locator("#customer_name").fill("Sneaky");
  await c.locator("#customer_phone").fill("98765 43210");
  await pickDate(c);
  await c.locator("#order-form").evaluate((f: HTMLFormElement, i) => {
    const x = document.createElement("input");
    x.type = "hidden"; x.name = `qty_${i}`; x.value = "1";
    f.appendChild(x);
    f.requestSubmit();
  }, index);
  await c.waitForLoadState("load");
  await expect(c.getByRole("alert")).toContainText("Pineapple cake is sold out today");
  await ctx.close();
});

test("landing: a strip of at least 6 demo shops, each opens its labelled demo with no UPI ID; reduced motion is still", async ({ browser }) => {
  test.setTimeout(180_000);
  for (const motion of ["no-preference", "reduce"] as const) {
    for (const width of [390, 1440]) {
      const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), reducedMotion: motion,
        viewport: { width, height: width < 600 ? 844 : 900 } });
      const page = await ctx.newPage();
      const errors: string[] = [];
      page.on("console", (m) => { if (m.type() === "error" || /Content Security Policy|Refused to/i.test(m.text())) errors.push(m.text()); });
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto("/");
      const strip = page.locator("#demos");
      await strip.scrollIntoViewIfNeeded();
      await expect(strip.getByRole("heading", { name: "See shops made with LaunchWitness" })).toBeVisible();
      await expect(strip).toContainText("Demo shops: tap one to open it. Orders there are not real.");
      const cards = strip.locator('a.demo-card:not([tabindex="-1"])');
      expect(await cards.count()).toBeGreaterThanOrEqual(6);
      await expect(strip.locator("img").first()).toHaveJSProperty("complete", true);
      const row = strip.locator(".demo-row");
      await page.waitForTimeout(1200);
      const a = await row.evaluate((e) => e.scrollLeft);
      await page.waitForTimeout(1500);
      const b = await row.evaluate((e) => e.scrollLeft);
      if (motion === "reduce") {
        expect(b).toBe(a);
        await expect(strip.locator('a.demo-card[tabindex="-1"]')).toHaveCount(0); // no looping copy
      } else {
        expect(b).toBeGreaterThan(a); // drifting
        await row.hover();
        await page.waitForTimeout(300);
        const c1 = await row.evaluate((e) => e.scrollLeft);
        await page.waitForTimeout(1000);
        expect(await row.evaluate((e) => e.scrollLeft)).toBe(c1); // paused under the pointer
      }
      if (motion === "no-preference") await shot(page, `landing-demo-strip-${width}`, strip);
      if (motion === "reduce" && width === 1440) {
        const hrefs = await cards.evaluateAll((els) => els.map((e) => (e as HTMLAnchorElement).getAttribute("href")!));
        for (const href of hrefs) {
          expect(href).toMatch(/^\/demo\/[a-z]+$/);
          const r = await page.evaluate(async (u) => { const x = await fetch(u); return { s: x.status, html: await x.text() }; }, href); // S21B: in the page (Node cannot resolve *.localhost on Windows)
          expect(r.s, href).toBe(200);
          const html = r.html;
          expect(html).toContain("Demo shop: orders here are not real");
          expect(html).not.toMatch(/upi:\/\/|[A-Za-z0-9._-]+@ok(axis|icici|sbi|hdfcbank)/);
        }
        await expect(cards.first()).toHaveAttribute("target", "_blank");
        await cards.first().focus();
        await expect(cards.first()).toBeFocused();
      }
      expect(errors, errors.join("\n")).toEqual([]);
      await ctx.close();
    }
  }
});

// S21B: the strip's pictures are real images (a stale build used to answer them with the app's page: broken icons).
// Laptop frame + 1440-wide picture from 1024 px; phone frame + 390 picture below, and a phone never fetches the laptop one.
test("landing strip: every picture is a real image, laptop frames on a laptop, phone frames on a phone", async ({ browser }) => {
  test.setTimeout(120_000);
  for (const width of [390, 1023, 1024, 1440]) {
    const ctx = await browser.newContext({ ignoreHTTPSErrors: BASE.includes(".localhost"), reducedMotion: "reduce",
      viewport: { width, height: 900 } });
    const page = await ctx.newPage();
    const fetched: string[] = [];
    page.on("request", (r) => { if (r.url().includes("/demos/")) fetched.push(r.url()); });
    await page.goto("/");
    const strip = page.locator("#demos");
    await strip.scrollIntoViewIfNeeded();
    // bring every card on screen once, so each lazy picture loads
    const row = strip.locator(".demo-row");
    for (let x = 0; x <= 6000; x += 300) {
      await row.evaluate((e, left) => { e.scrollLeft = left; }, x);
      await page.waitForTimeout(60);
    }
    const imgs = strip.locator("a.demo-card img");
    const n = await imgs.count();
    expect(n).toBeGreaterThanOrEqual(6);
    const laptop = width >= 1024;
    for (let i = 0; i < n; i++) {
      const img = imgs.nth(i);
      await expect(img).toHaveJSProperty("complete", true);
      const info = await img.evaluate((e: HTMLImageElement) => ({ src: e.currentSrc, w: e.naturalWidth, h: e.naturalHeight,
        alt: e.alt, attrW: e.getAttribute("width"), box: e.parentElement!.parentElement!.getBoundingClientRect() }));
      expect(info.w, info.src).toBeGreaterThan(0);
      expect(info.src).toMatch(laptop ? /\/demos\/[a-z]+-laptop\.webp$/ : /\/demos\/[a-z]+\.webp$/);
      expect(info.src.includes("-laptop")).toBe(laptop);
      expect([info.w, info.h]).toEqual(laptop ? [960, 600] : [390, 780]);
      const ratio = info.box.width / info.box.height;
      if (laptop) expect(ratio).toBeGreaterThan(1.4); else expect(ratio).toBeLessThan(0.7);
      const r = await page.evaluate(async (u) => { const x = await fetch(u); return { s: x.status, t: x.headers.get("content-type") || "" }; }, info.src); // in the page: Node cannot resolve *.localhost on Windows
      expect(r.s, info.src).toBe(200);
      expect(r.t, info.src).toMatch(/^image\//);
    }
    const alts = await strip.locator('a.demo-card:not([tabindex="-1"]) img').evaluateAll((els) => els.map((e) => (e as HTMLImageElement).alt));
    expect(alts.every((a) => a.length > 3)).toBe(true); // alt = the shop's name
    if (!laptop) expect(fetched.filter((u) => u.includes("-laptop"))).toEqual([]);
    expect(await page.evaluate(async () => (await fetch("/demos/nobody.webp")).status)).toBe(404);
    await shot(page, `landing-strip-frames-${width}`, strip);
    await ctx.close();
  }
});
