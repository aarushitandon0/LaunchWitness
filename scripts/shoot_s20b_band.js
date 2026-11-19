// S20B: hero + signature strip at 390 and 1440. usage (from e2e/): NODE_PATH=$(pwd)/node_modules node ../scripts/shoot_s20b_band.js <html_dir from render_theme_shots.py> <png_dir> bakery kitchen gifts
const { chromium } = require("playwright");
const fs = require("fs"); const http = require("http"); const path = require("path");
const [src, dst, ...names] = process.argv.slice(2);
fs.mkdirSync(dst, { recursive: true });
const FONTS = path.resolve(process.cwd(), "../backend/app/sites/fonts");
const server = http.createServer((req, res) => {
  const url = decodeURI(req.url.split("?")[0]);
  const file = url.startsWith("/shop-assets/fonts/") ? path.join(FONTS, path.basename(url)) : path.join(src, path.basename(url));
  if (!fs.existsSync(file)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": file.endsWith(".woff2") ? "font/woff2" : "text/html; charset=utf-8" });
  fs.createReadStream(file).pipe(res);
});
(async () => {
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch(process.env.LW_CHROME ? { executablePath: process.env.LW_CHROME } : {});
  for (const name of names) for (const w of [390, 1440]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 }, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(base + name + ".html", { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    const band = await page.$(".motif-band"); const bb = await band.boundingBox();
    const top = Math.max(0, bb.y + bb.height + 120 - (w === 390 ? 844 : 900));
    await page.screenshot({ path: path.join(dst, `${name}-${w}.png`), clip: { x: 0, y: top, width: w, height: (w === 390 ? 844 : 900) }, fullPage: true });
    console.log(name, w, "band at", Math.round(bb.y), "h", bb.height);
    await ctx.close();
  }
  await browser.close(); server.close();
})();
