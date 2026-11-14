// Screenshot rendered gallery pages at phone (375 px) and laptop (1440 px) width.
// usage: node scripts/shoot_site_gallery.js <html_dir> <png_dir>
// Adds two items to the basket first, and warns on any sideways scrolling.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const [src, dst] = process.argv.slice(2);
fs.mkdirSync(dst, { recursive: true });
const sizes = { phone: { width: 375, height: 812 }, laptop: { width: 1440, height: 900 } };

(async () => {
  const browser = await chromium.launch();
  for (const file of fs.readdirSync(src).filter((f) => f.endsWith(".html")).sort()) {
    const name = file.replace(/\.html$/, "");
    for (const [label, viewport] of Object.entries(sizes)) {
      const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
      const page = await context.newPage();
      await page.goto("file://" + path.resolve(src, file));
      const adds = await page.$$(".item .add");
      for (const b of adds.slice(0, 2)) await b.click();
      if (adds.length) await page.click(".item.chosen .plus");
      await page.evaluate(() => window.scrollTo(0, 0));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 0) console.log(`WARNING ${name} ${label}: sideways overflow ${overflow}px`);
      await page.screenshot({ path: path.join(dst, `${name}-${label}.png`), fullPage: true });
      if (label === "phone") await page.screenshot({ path: path.join(dst, `${name}-${label}-top.png`) });
      await context.close();
    }
    console.log(name);
  }
  await browser.close();
})();
