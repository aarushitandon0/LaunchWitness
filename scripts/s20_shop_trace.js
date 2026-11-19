// S20: scroll performance of a shop page (works on /demo/<name> or any shop URL).
// Usage: cd e2e && NODE_PATH=$(pwd)/node_modules LW_CHROME=<chrome> node ../scripts/s20_shop_trace.js <url> [shots_dir]
// 1440: ~60 fps scroll target. 390 px at 4x CPU throttle: report long tasks (> 100 ms after load) and frame times.
const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const url = process.argv[2], shots = process.argv[3];
  const browser = await chromium.launch(process.env.LW_CHROME ? { executablePath: process.env.LW_CHROME } : {});
  const out = [];
  for (const [label, w, h, throttle, dpr] of [["1440", 1440, 900, 1, 1], ["390 @4x CPU", 390, 844, 4, 3]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr, ignoreHTTPSErrors: true });
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await page.goto(url, { waitUntil: "load" });
    await page.waitForTimeout(1500);
    if (throttle > 1) await cdp.send("Emulation.setCPUThrottlingRate", { rate: throttle });
    await page.evaluate(() => {
      window.__lt = []; window.__frames = [];
      new PerformanceObserver((l) => l.getEntries().forEach((e) => window.__lt.push(e.duration))).observe({ entryTypes: ["longtask"] });
      let last = performance.now();
      const tick = (t) => { window.__frames.push(t - last); last = t; requestAnimationFrame(tick); };
      requestAnimationFrame(tick);
    });
    const total = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
    for (let y = 0; y <= total; y += 60) { await page.evaluate((v) => window.scrollTo(0, v), y); await page.waitForTimeout(16); }
    const r = await page.evaluate(() => {
      const f = window.__frames.slice(5).sort((a, b) => a - b), n = f.length;
      return { frames: n, avg: f.reduce((a, b) => a + b, 0) / n, p95: f[Math.floor(n * 0.95)], over50: f.filter((x) => x > 50).length,
               longTasks: window.__lt.length, maxLong: Math.max(0, ...window.__lt) };
    });
    out.push(`${label}: ${JSON.stringify(r)}`);
    await ctx.close();
  }
  console.log(out.join("\n"));
  if (shots) { fs.mkdirSync(shots, { recursive: true }); fs.writeFileSync(shots + "/perf-trace.txt", out.join("\n") + "\n"); }
  await browser.close();
})();
