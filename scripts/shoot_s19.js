// S19: viewport screenshots of every landing section at 390 and 1440. Usage: node scripts/shoot_s19.js <outdir> [reduced]
const { chromium } = require("playwright");
const out = process.argv[2], reduced = process.argv[3] === "reduced";
const base = process.env.LW_BASE || "http://localhost:8000";
const sections = [["hero", null], ["how", "#how"], ["proof", "#proof"], ["watch", "#watch"], ["pieces", "#pieces-title"], ["promises", "#promises-title"], ["check", "#check"], ["security", "#security"], ["contact", "#contact"]];
(async () => {
  const b = await chromium.launch();
  for (const [w, h] of [[390, 844], [1440, 900]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, reducedMotion: reduced ? "reduce" : "no-preference" });
    const p = await ctx.newPage();
    const errs = [];
    p.on("console", (m) => m.type() === "error" && errs.push(m.text()));
    p.on("pageerror", (e) => errs.push(String(e)));
    await p.goto(base + "/", { waitUntil: "networkidle" });
    await p.waitForTimeout(2500);
    for (const [name, sel] of sections) {
      if (sel) { await p.evaluate((s) => { const e = document.querySelector(s); e && e.scrollIntoView({ block: "start" }); }, sel); await p.waitForTimeout(1800); }
      await p.screenshot({ path: `${out}/${name}-${w}.png` });
    }
    console.log(w, "console errors:", errs.length, errs.slice(0, 3));
    await ctx.close();
  }
  await b.close();
})();
