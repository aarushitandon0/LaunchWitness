// S19B: the landing page by hand, scripted. Every top-bar / Product-menu link lands on its section (in view), the CTAs
// go to the right pages, Back/Forward/refresh work on #/new, #/try and /demo/meera, "Check any address" answers for
// google.com, both demos play, reduced motion shows everything, no console errors or CSP violations.
// Usage: LW_BASE=https://launchwitness.localhost node scripts/s19b_landing_check.js <shots_dir>
const { chromium } = require("playwright");
const out = process.argv[2];
const base = process.env.LW_BASE || "http://localhost:8000";
const results = [];
const ok = (name, pass, info = "") => { results.push({ name, pass, info }); console.log(`${pass ? "PASS" : "FAIL"}  ${name}${info ? "  (" + info + ")" : ""}`); };

async function page(b, w, h, opts = {}) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, ignoreHTTPSErrors: true, ...opts });
  const p = await ctx.newPage();
  p.bad = [];
  p.on("console", (m) => (m.type() === "error" || /content.security/i.test(m.text())) && p.bad.push(m.text()));
  p.on("pageerror", (e) => p.bad.push(String(e)));
  return [ctx, p];
}

async function inView(p, sel) {
  return p.evaluate((s) => { const e = document.querySelector(s); if (!e) return "missing"; const r = e.getBoundingClientRect(); return r.top < innerHeight * 0.6 && r.bottom > 0 ? "yes" : `top=${Math.round(r.top)}`; }, sel);
}

(async () => {
  const b = await chromium.launch();
  for (const [w, h] of [[390, 844], [1440, 900]]) {
    const [ctx, p] = await page(b, w, h);
    await p.goto(base + "/", { waitUntil: "networkidle" });
    await p.waitForTimeout(2500);
    await p.screenshot({ path: `${out}/landing-hero-${w}.png` });
    // Product menu: open, read every link, follow each
    const toggle = p.locator(".product-button:visible").first();
    const links = [];
    if (await toggle.count()) {
      await toggle.click();
      for (const a of await p.locator(".product-panel:visible a").all()) links.push([(await a.innerText()).trim(), await a.getAttribute("href")]);
      await p.keyboard.press("Escape");
    }
    ok(`${w}: Product menu has links`, links.length > 0, `${links.length}`);
    for (const [label, href] of links) {
      await p.goto(base + "/", { waitUntil: "networkidle" });
      await toggle.click();
      await p.locator(".product-panel:visible a", { hasText: label }).first().click();
      await p.waitForTimeout(1200);
      const url = p.url();
      if (href.startsWith("#") && !href.startsWith("#/")) {
        const v = await inView(p, href);
        ok(`${w}: menu "${label}" -> ${href} in view`, v === "yes", v);
      } else {
        ok(`${w}: menu "${label}" -> ${href}`, url.includes(href.replace(/^\//, "")), url.replace(base, ""));
      }
    }
    // CTAs
    for (const [label, sel, want] of [["Start", ".pill-cta", "#/new"], ["Try it", 'a[href="#/try"]', "#/try"], ["See a demo shop", 'a.dotlink[href="/demo/meera"]', "/demo/meera"]]) {
      await p.goto(base + "/", { waitUntil: "networkidle" });
      const loc = p.locator(sel).first();
      if (!(await loc.isVisible())) { ok(`${w}: ${label} visible`, false); continue; }
      await loc.click();
      await p.waitForLoadState("networkidle");
      ok(`${w}: ${label} -> ${want}`, p.url().includes(want), p.url().replace(base, ""));
    }
    // Back / Forward / refresh
    await p.goto(base + "/", { waitUntil: "networkidle" });
    for (const path of ["/#/new", "/#/try", "/demo/meera"]) {
      await p.goto(base + path, { waitUntil: "networkidle" });
      await p.waitForTimeout(1000);  // a hash route re-renders after the URL changes
      const before = [p.url(), (await p.locator("h1").first().innerText()).trim()];
      await p.reload({ waitUntil: "networkidle" });
      await p.waitForTimeout(1000);
      const after = [p.url(), (await p.locator("h1").first().innerText()).trim()];
      ok(`${w}: refresh ${path} keeps the page`, before.join() === after.join() && before[1].length > 0,
         `${before[0].replace(base, "")} "${before[1].replace(/\s+/g, " ").slice(0, 40)}"`);
    }
    await p.goBack({ waitUntil: "networkidle" });
    ok(`${w}: Back from /demo/meera -> #/try`, p.url().endsWith("#/try"), p.url().replace(base, ""));
    await p.goBack({ waitUntil: "networkidle" });
    // a guest on #/new is sent to sign in first (#/signin?next=new), so Back lands on either
    ok(`${w}: Back -> #/new (guest: its sign-in step)`, /#\/new$|#\/signin\?next=new$/.test(p.url()), p.url().replace(base, ""));
    await p.goForward({ waitUntil: "networkidle" });
    ok(`${w}: Forward -> #/try`, p.url().endsWith("#/try"), p.url().replace(base, ""));
    // Check any address: google.com
    await p.goto(base + "/#check", { waitUntil: "networkidle" });
    await p.waitForTimeout(800);
    const card = p.locator(".check-card");
    await card.locator("input").first().fill("google.com");
    await card.locator("button[type=submit]").click();
    await p.locator(".check-result").first().waitFor({ timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(1500);
    const text = (await p.locator(".check-result").first().innerText().catch(() => "")).replace(/\s+/g, " ");
    ok(`${w}: Check any address answers for google.com`, text.length > 40, text.slice(0, 120));
    await card.scrollIntoViewIfNeeded();
    await p.screenshot({ path: `${out}/check-google-${w}.png` });
    // demos play
    await p.goto(base + "/", { waitUntil: "networkidle" });
    const send = p.getByRole("button", { name: /send a test order/i });
    await send.scrollIntoViewIfNeeded();
    await send.click();
    await p.waitForTimeout(6000);
    const status = await p.locator("text=/Test order reached hop/").count();
    ok(`${w}: "Send a test order" plays`, status > 0);
    await p.screenshot({ path: `${out}/proof-played-${w}.png` });
    const brk = p.getByRole("button", { name: "Something breaks", exact: true });
    if (await brk.count()) {
      await brk.scrollIntoViewIfNeeded();
      await brk.click();
      await p.waitForTimeout(7000);
      const steps = await p.locator("text=/Checked again: working/").count();
      ok(`${w}: "Something breaks" plays`, steps > 0);
      await p.screenshot({ path: `${out}/watch-played-${w}.png` });
    } else ok(`${w}: "Something breaks" button`, false, "not found");
    ok(`${w}: no console errors / CSP violations`, p.bad.length === 0, p.bad.slice(0, 2).join(" | "));
    await ctx.close();
  }
  // reduced motion: every section's heading and text visible (opacity 1), screenshots
  for (const [w, h] of [[390, 844], [1440, 900]]) {
    const [ctx, p] = await page(b, w, h, { reducedMotion: "reduce" });
    await p.goto(base + "/", { waitUntil: "networkidle" });
    await p.waitForTimeout(1000);
    const hidden = await p.evaluate(() => [...document.querySelectorAll("main h1, main h2, main h3, main p, main li")]
      .filter((e) => e.offsetParent !== null && e.textContent.trim() && +getComputedStyle(e).opacity < 0.99)
      .map((e) => e.textContent.trim().slice(0, 40)));
    ok(`${w}: reduced motion shows everything at full opacity`, hidden.length === 0, hidden.slice(0, 3).join(" | "));
    await p.screenshot({ path: `${out}/reduced-full-${w}.png`, fullPage: true });
    ok(`${w}: reduced motion: no console errors`, p.bad.length === 0, p.bad.slice(0, 2).join(" | "));
    await ctx.close();
  }
  await b.close();
  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length} of ${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})();
