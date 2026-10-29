// Behavioural test for the live counts on about.html. Run: NODE_PATH=/tmp/node_modules node tools/test_about_page.js
const fs = require("fs"), path = require("path"), { JSDOM } = require("jsdom");
const ROOT = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "about.html"), "utf8");
const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "indicators", "manifest.json"), "utf8"));
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).find(s => s.includes("aboutCount"));
let fails = 0, runs = 0;
function ok(c, m) { runs++; if (!c) { fails++; console.log("FAIL", m); } }
if (!script) { console.log("FAIL no inline script reads aboutCount"); process.exit(1); }
const FALLBACK = "economic indicators across dozens of economies";
async function run(fetchImpl, withEl = true) {
  const dom = new JSDOM(`<!doctype html><body>${withEl ? `<span id="aboutCount">${FALLBACK}</span>` : ""}</body>`, { runScripts: "outside-only", url: "https://theeconomicatlas.com/about" });
  if (fetchImpl) dom.window.fetch = fetchImpl;
  dom.window.eval(script);
  await new Promise(r => setTimeout(r, 30));
  const el = dom.window.document.getElementById("aboutCount");
  return el ? el.textContent : null;
}
const resp = (body, okFlag = true) => () => Promise.resolve({ ok: okFlag, json: () => Promise.resolve(body) });
(async () => {
  // an independent count: economies are the keys, indicators are every listed slug
  const economies = Object.keys(manifest.indicators).length;
  const indicators = Object.values(manifest.indicators).reduce((a, v) => a + v.length, 0);
  const want = `${indicators.toLocaleString("en-GB")} indicators across ${economies} economies`;
  ok(await run(resp(manifest)) === want, `real manifest should read "${want}"`);
  ok(await run(resp({ indicators: { a: ["x", "y"], b: ["z"] } })) === "3 indicators across 2 economies", "counts must come from the manifest, not a constant");
  ok(await run(resp(manifest, false)) === FALLBACK, "a failed request keeps the fallback");
  ok(await run(() => Promise.reject(new Error("offline"))) === FALLBACK, "a network error keeps the fallback");
  ok(await run(resp({})) === FALLBACK, "a manifest without indicators keeps the fallback");
  ok(await run(resp({ indicators: {} })) === FALLBACK, "an empty manifest keeps the fallback");
  ok(await run(null) === FALLBACK, "no fetch support keeps the fallback");
  ok(await run(resp(manifest), false) === null, "a page without the span must not crash");
  console.log(`about page test: ${runs} checks, ${fails} failed`);
  process.exit(fails ? 1 : 0);
})();
