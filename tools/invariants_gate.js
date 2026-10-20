#!/usr/bin/env node
/* Invariants gate (v1.9.4): things that must always be true, checked before every deploy.
 *
 * DATA (every data-XX.json)
 *   - every series has at least one point, and every point is a finite number (no null, NaN, Infinity);
 *   - the file's sample flag is never true;
 *   - every currency series is in the country's own currency (the base of its fx_to_usd pair) or in US
 *     dollars. A third currency is allowed only if listed in THIRD_CURRENCY below, with its reason;
 *     a listed entry that no longer exists also fails, so the list cannot go stale.
 * COPY (every hand-written page: visible text, meta tags and JSON-LD; scripts and comments ignored)
 *   - every "N countries / economies / country pages / individual pages" claim says the real count.
 * RENDERED (every country page, loaded in jsdom with its real data files and chart libraries)
 *   - no "NaN", "undefined", "Infinity" or "null" in any visible text;
 *   - the page's "couldn't load" notice stays hidden;
 *   - no currency glyph (£ € ¥ ₩ ₪ ₹) is visible unless the page's own data uses it (a glyph right
 *     after a capital letter, like CN¥ or E£, is that other currency's own sign and does not count).
 *
 * Run: NODE_PATH=/tmp/node_modules node tools/invariants_gate.js
 * Needs (cd /tmp && npm i jsdom@24 d3@7.8.5 chart.js@4.4.1 topojson@3.0.2 hammerjs@2.0.8
 *        chartjs-plugin-zoom@2.0.1 world-atlas@2). Takes about three minutes.
 * Other tree (mutation checks): ATLAS_ROOT=/path node tools/invariants_gate.js
 * One page only (debugging): node tools/invariants_gate.js --page poland.html
 */
const fs = require("fs"), path = require("path");
const ROOT = process.env.ATLAS_ROOT ? path.resolve(process.env.ATLAS_ROOT) : path.resolve(__dirname, "..");
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const {JSDOM, VirtualConsole, ResourceLoader} = require("jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const only = process.argv.includes("--page") ? process.argv[process.argv.indexOf("--page") + 1] : null;

// Third-currency series, by data file and key. Each needs a reason; each is an open item to fix at source.
const THIRD_CURRENCY = {
  "data-pl.json:trade_balance": "Eurostat publishes Poland's goods trade in euros. Open item: switch to GUS (PLN) or the IMF (USD).",
};
const GLYPH = {"\u00a3": "GBP", "\u20ac": "EUR", "\u00a5": "JPY", "\u20a9": "KRW", "\u20aa": "ILS", "\u20b9": "INR"};
const DOLLAR_LOCAL = {au: "AUD", br: "BRL", ca: "CAD", mx: "MXN", za: "ZAR"};
function currencyOf(unit, code) {
  const m = /^([A-Z]{3})(m|bn|tn)?$/.exec(unit);
  if (m) return m[1];
  if (GLYPH[unit[0]]) return GLYPH[unit[0]];
  if (unit[0] === "$") return DOLLAR_LOCAL[code] || "USD";
  return null;
}

// ---------------------------------------------------------------- DATA
const dataFiles = fs.readdirSync(ROOT).filter(f => /^data-[a-z]{2}\.json$/.test(f)).sort();
const thirdSeen = new Set();
for (const f of dataFiles) {
  const d = JSON.parse(read(f)), code = f.slice(5, 7);
  ok(d.sample !== true, `${f}: sample flag is true`);
  const own = ((d.fx_to_usd || {}).pair || "USD/").split("/")[0];
  for (const [k, s] of Object.entries(d.series || {})) {
    const pts = s.points || [];
    ok(pts.length > 0, `${f} ${k}: empty series`);
    const bad = pts.filter(p => typeof p[1] !== "number" || !Number.isFinite(p[1]));
    ok(bad.length === 0, `${f} ${k}: ${bad.length} point(s) not a finite number, e.g. ${JSON.stringify(bad[0])}`);
    const u = s.unit || "";
    if (u === "%" || u === "index" || u === "") continue;
    const c = currencyOf(u, code);
    ok(c !== null, `${f} ${k}: unit "${u}" names no currency this gate recognises`);
    if (c && c !== own && c !== "USD") {
      thirdSeen.add(`${f}:${k}`);
      ok(THIRD_CURRENCY[`${f}:${k}`], `${f} ${k}: unit ${u} is ${c}, but the country's currency is ${own} (add to THIRD_CURRENCY with a reason, or fix the source)`);
    }
  }
}
for (const k of Object.keys(THIRD_CURRENCY)) ok(thirdSeen.has(k), `THIRD_CURRENCY lists ${k}, which is no longer a third-currency series: remove the entry`);

// ---------------------------------------------------------------- COPY
const countryPages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && /fetch\("data-[a-z]{2}\.json"/.test(read(f))).sort();
const N = countryPages.length;
ok(N === dataFiles.length, `${N} country pages but ${dataFiles.length} data files`);
for (const f of fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && !/^(404|markets)\.html$/.test(f))) {
  const s = read(f)
    .replace(/<script(?![^>]*application\/ld\+json)[\s\S]*?<\/script>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ").replace(/<style[\s\S]*?<\/style>/gi, " ");
  const re = /\b(\d{1,3})\+?\s+(?:[a-z-]+\s+){0,2}(countries|economies|country pages|individual pages)\b/gi;
  let m;
  while ((m = re.exec(s))) ok(Number(m[1]) === N, `${f}: says "${m[0]}" but there are ${N} country pages`);
}

// ---------------------------------------------------------------- RENDERED
const LIB = {"d3.min.js": "d3/dist/d3.min.js", "chart.umd.min.js": "chart.js/dist/chart.umd.js", "topojson.min.js": "topojson/dist/topojson.min.js",
             "hammer.min.js": "hammerjs/hammer.min.js", "chartjs-plugin-zoom.min.js": "chartjs-plugin-zoom/dist/chartjs-plugin-zoom.min.js"};
const SUPA = "window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:[]}).then(r)}};return {auth:{getSession:function(){return Promise.resolve({data:{session:null}})},onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}}},from:function(){return q}}}};";
class Loader extends ResourceLoader {
  fetch(url) { const b = url.split("/").pop().split("?")[0];
    if (LIB[b]) return Promise.resolve(fs.readFileSync(NM + LIB[b]));
    if (/supabase/.test(url)) return Promise.resolve(Buffer.from(SUPA));
    return Promise.resolve(Buffer.from("")); }
}
process.on("unhandledRejection", () => {});
function visibleText(d) {
  const w = d.createTreeWalker(d.body, 4), out = [];
  while (w.nextNode()) {
    const t = w.currentNode; let n = t.parentElement, shown = true;
    while (n) { if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(n.tagName) || n.hidden || (n.style && n.style.display === "none")) { shown = false; break; } n = n.parentElement; }
    if (shown && t.nodeValue.trim()) out.push(t.nodeValue);
  }
  return out.join(" ");
}
(async () => {
  for (const p of (only ? [only] : countryPages)) {
    const code = (read(p).match(/fetch\("data-([a-z]{2})\.json"/) || [])[1];
    const own = new Set(Object.values(JSON.parse(read(`data-${code}.json`)).series || {}).map(s => (s.unit || "")[0]).filter(g => GLYPH[g]));
    const vc = new VirtualConsole(), errs = [];
    vc.on("jsdomError", e => errs.push(String(e.message || e).split("\n")[0]));
    const dom = new JSDOM(read(p), {runScripts: "dangerously", resources: new Loader(), url: "https://example.test/" + p, virtualConsole: vc, pretendToBeVisual: true,
      beforeParse(w) {
        w.fetch = (u) => { u = String(u);
          if (/countries-110m\.json/.test(u)) return Promise.resolve({ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(NM + "world-atlas/countries-110m.json")))});
          const f = path.join(ROOT, u.replace(/^https:\/\/example\.test\//, "").split("?")[0]);
          if (/^https?:/.test(u) || !fs.existsSync(f)) return Promise.resolve({ok: false, status: 404, json: () => Promise.reject(new Error("404"))});
          const t = fs.readFileSync(f, "utf8"); return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)), text: () => Promise.resolve(t)}); };
        w.matchMedia = () => ({matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
        w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
        w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
        w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      }});
    await new Promise(r => setTimeout(r, 2500));
    const d = dom.window.document, text = visibleText(d);
    const lf = d.getElementById("loadFail");
    ok(lf && lf.hidden, `${p}: the "couldn't load" notice shows with real data (a render error?) ${errs.slice(0, 2).join(" | ")}`);
    const bad = text.match(/\b(NaN|undefined|Infinity|null)\b/g);
    ok(!bad, `${p}: visible text contains ${bad ? [...new Set(bad)].join(", ") : ""}`);
    for (const g of Object.keys(GLYPH)) {
      // A symbol right after a capital letter is another currency's own sign (CN\u00a5 yuan, E\u00a3 Egyptian pound).
      const re = new RegExp("(?<![A-Z])" + g), hit = re.exec(text);
      if (own.has(g) || !hit) { checks++; continue; }
      const i = hit.index;
      ok(false, `${p}: shows ${g} but its data uses no ${GLYPH[g]} series: "...${text.slice(Math.max(0, i - 60), i + 30).replace(/\s+/g, " ")}..."`);
    }
    dom.window.close();
  }
  console.log(`${dataFiles.length} data files, ${N} country pages, ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
