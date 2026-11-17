// Screenshot rendered theme pages at phone (375 px) and laptop (1440 px), with the real fonts (S14).
// usage: node scripts/shoot_themes.js <html_dir> <png_dir>
// Serves <html_dir> and the themes' woff2 files from a small local server (the pages ask for /shop-assets/fonts/...),
// adds two items to the basket first, and warns on any sideways scrolling.
const { chromium } = require("playwright");
const fs = require("fs");
const http = require("http");
const path = require("path");

const [src, dst] = process.argv.slice(2);
fs.mkdirSync(dst, { recursive: true });
const FONTS = path.resolve(__dirname, "../backend/app/sites/fonts");
const sizes = { "375": { width: 375, height: 812 }, "1440": { width: 1440, height: 900 } };

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
  for (const file of fs.readdirSync(src).filter((f) => f.endsWith(".html")).sort()) {
    const name = file.replace(/\.html$/, "");
    for (const [label, viewport] of Object.entries(sizes)) {
      const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
      const page = await context.newPage();
      await page.goto(base + file, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(dst, `${name}-${label}-top.png`) }); // before the basket bar appears
      const adds = await page.$$(".item .add");
      for (const b of adds.slice(0, 2)) await b.click();
      if (adds.length) await page.click(".item.chosen .plus");
      await page.evaluate(() => window.scrollTo(0, 0));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 0) console.log(`WARNING ${name} ${label}: sideways overflow ${overflow}px`);
      await page.screenshot({ path: path.join(dst, `${name}-${label}.png`), fullPage: true });
      await context.close();
    }
    console.log(name);
  }
  await browser.close();
  server.close();
})();
