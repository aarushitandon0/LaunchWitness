// S15 screenshots: the order form and the shop-info sections of three themes at 375 and 1440 px.
// usage: node scripts/shoot_s15.js <html_dir> <png_dir>   (see scripts/render_s15_shots.py)
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
      const context = await browser.newContext({ viewport, deviceScaleFactor: 2 });
      const page = await context.newPage();
      await page.goto(base + file, { waitUntil: "networkidle" });
      await page.evaluate(() => document.fonts.ready);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 0) console.log(`WARNING ${name} ${label}: sideways overflow ${overflow}px`);
      // the shop-info sections
      await page.locator("#info").scrollIntoViewIfNeeded();
      await page.locator("#info").screenshot({ path: path.join(dst, `${name}-${label}-info.png`) });
      // the order form: two items, delivery chosen when offered, a PIN she doesn't serve (the polite message)
      const adds = await page.$$(".item .add");
      for (const b of adds.slice(0, 2)) await b.click();
      const delivery = page.locator('input[type="radio"][name="fulfilment"][value="delivery"]');
      const onlyDelivery = (await page.locator("#delivery-fields[data-only]").count()) > 0;
      if (await delivery.count() || onlyDelivery) {
        if (!onlyDelivery) await delivery.check();
        await page.fill("#delivery_address", "12 MG Road, Bengaluru");
        await page.fill("#delivery_pin", "560001");
      }
      const d = page.locator("#wanted_date");
      if (await d.count()) { const min = await d.getAttribute("min"); await d.fill(min); }
      await page.locator("#order").scrollIntoViewIfNeeded();
      await page.locator("#order").screenshot({ path: path.join(dst, `${name}-${label}-order.png`) });
      await context.close();
    }
    console.log(name);
  }
  await browser.close();
  server.close();
})();
