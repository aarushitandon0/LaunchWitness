// S21: thumbnails for the landing page's demo strip. Opens each demo shop (the list in
// frontend/src/landing/demoShops.ts) at 390 x 780 like a phone, with reduced motion so nothing is mid-animation,
// screenshots the first screen and saves it as WebP (<= 60 KB) in frontend/public/demos/<slug>.webp.
// S21B: also a laptop picture: the first screen in a 1440 x 900 window, saved at 960 x 600 (<= 80 KB) as
// frontend/public/demos/<slug>-laptop.webp (the landing shows it in a laptop frame from 1024 px wide).
//
//   cd e2e && node ../scripts/make_demo_thumbs.js [base_url]        (default http://localhost:8000)
//
// Run it after any change to the shops' look, so the cards show the real pages. Uses the pre-installed Playwright
// (or LW_CHROME=<path> for a full Chrome). The WebP is encoded by the browser itself (canvas), so nothing else is needed.
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const BASE = (process.argv[2] || "http://localhost:8000").replace(/\/$/, "");
const OUT = path.join(ROOT, "frontend", "public", "demos");
const LIMIT = 60 * 1024;
const W = 390, H = 780;

const slugs = [...fs.readFileSync(path.join(ROOT, "frontend", "src", "landing", "demoShops.ts"), "utf8")
  .matchAll(/slug: "([a-z]+)"/g)].map((m) => m[1]);

const SIZES = [
  { suffix: "", vw: W, vh: H, w: W, h: H, limit: LIMIT },
  { suffix: "-laptop", vw: 1440, vh: 900, w: 960, h: 600, limit: 80 * 1024 },
];

(async () => {
  const browser = await chromium.launch(process.env.LW_CHROME ? { executablePath: process.env.LW_CHROME } : {});
  fs.mkdirSync(OUT, { recursive: true });
  for (const size of SIZES) {
    const ctx = await browser.newContext({ viewport: { width: size.vw, height: size.vh }, deviceScaleFactor: 1,
                                           reducedMotion: "reduce" });
    const page = await ctx.newPage();
    const enc = await ctx.newPage();
    for (const slug of slugs) {
      const r = await page.goto(`${BASE}/demo/${slug}`, { waitUntil: "networkidle" });
      if (!r || r.status() !== 200) throw new Error(`${slug}: HTTP ${r && r.status()}`);
      await page.evaluate(() => document.fonts.ready);
      const png = await page.screenshot({ type: "png" });
      let q = 0.8, data = null;
      for (; q >= 0.3; q -= 0.1) {
        data = await enc.evaluate(async ({ src, q, w, h }) => {
          const img = new Image();
          img.src = src;
          await img.decode();
          const c = document.createElement("canvas");
          c.width = w; c.height = h;
          const g = c.getContext("2d");
          g.imageSmoothingQuality = "high";
          g.drawImage(img, 0, 0, w, h);
          return c.toDataURL("image/webp", q);
        }, { src: "data:image/png;base64," + png.toString("base64"), q, w: size.w, h: size.h });
        if (!data.startsWith("data:image/webp")) throw new Error("this browser can't encode WebP");
        if (Buffer.from(data.split(",")[1], "base64").length <= size.limit) break;
      }
      const buf = Buffer.from(data.split(",")[1], "base64");
      if (buf.length > size.limit) throw new Error(`${slug}${size.suffix}: still ${buf.length} bytes at the lowest quality`);
      fs.writeFileSync(path.join(OUT, `${slug}${size.suffix}.webp`), buf);
      console.log(`${slug}${size.suffix}.webp  ${(buf.length / 1024).toFixed(1)} KB  (quality ${q.toFixed(1)})`);
    }
    await ctx.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
