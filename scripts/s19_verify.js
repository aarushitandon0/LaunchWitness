// S19 verification: frame times + layout shift while scrolling at 390 px, mid-animation hero/proof frames, CSP/console listener,
// and a short recording. Usage: node scripts/s19_verify.js <outdir>   (needs the app on LW_BASE, default http://localhost:8000)
const { chromium } = require("playwright");
const out = process.argv[2];
const base = process.env.LW_BASE || "http://localhost:8000";
(async () => {
  const b = await chromium.launch();
  // 1) frame time + CLS, phone width, 5 s of scrolling
  {
    const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
    const p = await ctx.newPage();
    const bad = [];
    p.on("console", (m) => (m.type() === "error" || /content security/i.test(m.text())) && bad.push(m.text()));
    p.on("pageerror", (e) => bad.push(String(e)));
    await p.addInitScript(() => {
      window.__f = []; window.__cls = 0;
      new PerformanceObserver((l) => l.getEntries().forEach((e) => !e.hadRecentInput && (window.__cls += e.value))).observe({ type: "layout-shift", buffered: true });
      let last = performance.now();
      const loop = (t) => { window.__f.push(t - last); last = t; requestAnimationFrame(loop); };
      requestAnimationFrame(loop);
    });
    await p.goto(base + "/", { waitUntil: "networkidle" });
    await p.waitForTimeout(3000); // let the load animation finish first; measured separately below
    await p.evaluate(() => { window.__f = []; });
    const H = await p.evaluate(() => document.documentElement.scrollHeight);
    const t0 = Date.now();
    while (Date.now() - t0 < 5000) {
      const y = ((Date.now() - t0) / 5000) * (H - 844);
      await p.evaluate((y) => window.scrollTo(0, y), y);
      await p.waitForTimeout(16);
    }
    const f = await p.evaluate(() => window.__f.slice(2));
    const cls = await p.evaluate(() => window.__cls);
    const n = f.length, s = [...f].sort((a, c) => a - c);
    console.log(JSON.stringify({ frames: n, avg_ms: +(f.reduce((a, c) => a + c, 0) / n).toFixed(1), p95_ms: +s[Math.floor(n * 0.95)].toFixed(1), slow_gt33: f.filter((x) => x > 33).length, slow_gt50: f.filter((x) => x > 50).length, cls: +cls.toFixed(4), bad_console: bad }));
    await ctx.close();
  }
  // 2) hero frames at 0.3 / 0.8 / 1.5 s after load (1440)
  {
    const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await ctx.newPage();
    await p.goto(base + "/", { waitUntil: "commit" });
    const t0 = Date.now();
    for (const t of [300, 800, 1500, 2600]) {
      await p.waitForTimeout(Math.max(0, t - (Date.now() - t0)));
      await p.screenshot({ path: `${out}/hero-load-${t}ms.png` });
    }
    // proof pulse frames
    await p.evaluate(() => document.querySelector("#proof").scrollIntoView({ block: "start" }));
    const t1 = Date.now();
    for (const t of [500, 1100, 1700, 2600]) {
      await p.waitForTimeout(Math.max(0, t - (Date.now() - t1)));
      await p.screenshot({ path: `${out}/proof-pulse-${t}ms.png` });
    }
    await ctx.close();
  }
  // 3) recording: load hero, scroll to the proof section (<= 15 s)
  {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 720 }, recordVideo: { dir: out + "/vid", size: { width: 1280, height: 720 } } });
    const p = await ctx.newPage();
    await p.goto(base + "/", { waitUntil: "networkidle" });
    await p.waitForTimeout(4500);
    const H = await p.evaluate(() => document.querySelector("#proof").offsetTop);
    for (let i = 0; i <= 60; i++) { await p.evaluate((y) => window.scrollTo(0, y), (i / 60) * H); await p.waitForTimeout(60); }
    await p.waitForTimeout(3500);
    await ctx.close();
  }
  await b.close();
})();
