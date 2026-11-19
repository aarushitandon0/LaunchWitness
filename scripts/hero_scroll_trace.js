// Landing hero: idle main-thread time + scroll smoothness, at 1440 px and at 390 px with a 4x CPU throttle (S19D).
// Usage (from e2e/, so Playwright resolves): NODE_PATH=$(pwd)/node_modules node ../scripts/hero_scroll_trace.js [url] [runs]
// Prints JSON per run. Frame times come from requestAnimationFrame during a scripted wheel scroll through the hero
// and the dark panel; idle is the CDP TaskDuration share over 3 s with the hero in view; CLS from layout-shift entries.
const { chromium } = require("playwright");

const URL_ = process.argv[2] || "https://launchwitness.com/";
const RUNS = Number(process.argv[3] || 2);
const CASES = [
  { name: "1440", width: 1440, height: 900, throttle: 1, mobile: false },
  { name: "390 x4", width: 390, height: 844, throttle: 4, mobile: true },
];

async function measure(browser, c) {
  const ctx = await browser.newContext({
    viewport: { width: c.width, height: c.height }, isMobile: c.mobile, hasTouch: c.mobile, deviceScaleFactor: c.mobile ? 3 : 1,
    ignoreHTTPSErrors: URL_.includes(".localhost"),
  });
  const page = await ctx.newPage();
  await page.addInitScript(() => {
    window.__cls = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
      .observe({ type: "layout-shift", buffered: true });
  });
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Performance.enable");
  if (c.throttle > 1) await cdp.send("Emulation.setCPUThrottlingRate", { rate: c.throttle });
  await page.goto(URL_, { waitUntil: "load" });
  await page.waitForTimeout(4000); // intro finishes

  const task = async () => (await cdp.send("Performance.getMetrics")).metrics.find((m) => m.name === "TaskDuration").value;
  const t0 = await task();
  await page.waitForTimeout(3000);
  const idle = ((await task()) - t0) / 3; // share of wall time the main thread was busy (throttled time counts as busy)

  await page.evaluate(() => {
    window.__frames = [];
    let last = performance.now();
    const tick = (t) => { window.__frames.push(t - last); last = t; if (window.__rec) requestAnimationFrame(tick); };
    window.__rec = true;
    requestAnimationFrame(tick);
  });
  const steps = 60;
  const total = await page.evaluate(() => Math.min(document.documentElement.scrollHeight - innerHeight, innerHeight * 2.5));
  await page.mouse.move(c.width / 2, c.height / 2);
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, total / steps);
    await page.waitForTimeout(40);
  }
  await page.waitForTimeout(500);
  const frames = await page.evaluate(() => { window.__rec = false; return window.__frames.slice(1); });
  const cls = await page.evaluate(() => window.__cls);
  await ctx.close();
  const sorted = [...frames].sort((a, b) => a - b);
  const avg = frames.reduce((a, b) => a + b, 0) / frames.length;
  return {
    case: c.name, idle_busy_pct: +(idle * 100).toFixed(1), frames: frames.length, avg_ms: +avg.toFixed(1),
    p95_ms: +sorted[Math.floor(sorted.length * 0.95)].toFixed(1), over_50ms: frames.filter((f) => f > 50).length,
    fps: +(1000 / avg).toFixed(0), cls: +cls.toFixed(4),
  };
}

(async () => {
  const browser = await chromium.launch(process.env.LW_CHROME ? { executablePath: process.env.LW_CHROME } : {});
  for (const c of CASES) for (let r = 0; r < RUNS; r++) console.log(JSON.stringify(await measure(browser, c)));
  await browser.close();
})();
