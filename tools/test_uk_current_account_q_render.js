#!/usr/bin/env node
/* UK quarterly current account (v1.9.8): rendered page.
 *
 *   A. Real data (no quarterly series yet, or after the bot adds it): uk.html renders with no errors.
 *   B. Synthetic quarterly points injected IN MEMORY (never written to disk, never committed):
 *      the "Current account, quarterly" panel appears next to the annual one, the annual panel and its
 *      hero tile are unchanged, there is no hero tile for the quarterly series, the panel's info text
 *      is the one in INFO_CONTENT, and the page shows no NaN/undefined.
 *
 * Needs jsdom 24 and the chart libraries in NODE_PATH (see invariants_gate.js for the install line).
 * Run from the repo root:  NODE_PATH=/tmp/node_modules node tools/test_uk_current_account_q_render.js
 */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(process.env.ATLAS_ROOT || path.join(__dirname, ".."));
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const jsdomDir = path.join(NM, "jsdom");
if (!fs.existsSync(path.join(jsdomDir, "package.json"))) { console.error("jsdom not found in " + NM); process.exit(2); }
const {JSDOM, VirtualConsole, ResourceLoader} = require(jsdomDir);
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");

const LIB = {"d3.min.js": "d3/dist/d3.min.js", "chart.umd.min.js": "chart.js/dist/chart.umd.js", "topojson.min.js": "topojson/dist/topojson.min.js",
             "hammer.min.js": "hammerjs/hammer.min.js", "chartjs-plugin-zoom.min.js": "chartjs-plugin-zoom/dist/chartjs-plugin-zoom.min.js"};
const SUPA = "window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:null}).then(r)}};return {from:function(){return q},auth:{getSession:function(){return Promise.resolve({data:{session:null}})},onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}}}}}}};";
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
function render(p, transform) {
  const vc = new VirtualConsole(), errs = [];
  vc.on("jsdomError", e => errs.push(String(e.message || e).split("\n")[0]));
  const dom = new JSDOM(read(p), {runScripts: "dangerously", resources: new Loader(), url: "https://example.test/" + p, virtualConsole: vc, pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u) => { u = String(u);
        if (/countries-110m\.json/.test(u)) return Promise.resolve({ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(NM + "world-atlas/countries-110m.json")))});
        const f = path.join(ROOT, u.replace(/^https:\/\/example\.test\//, "").split("?")[0]);
        if (/^https?:/.test(u) || !fs.existsSync(f)) return Promise.resolve({ok: false, status: 404, json: () => Promise.reject(new Error("404")), text: () => Promise.reject(new Error("404"))});
        let t = fs.readFileSync(f, "utf8"); if (transform) t = transform(path.basename(f), t);
        return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)), text: () => Promise.resolve(t)}); };
      w.matchMedia = () => ({matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
      w.scrollTo = () => {}; w.HTMLCanvasElement.prototype.getContext = () => null;
      w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
    }});
  return {dom, errs};
}
const wait = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const hasReal = !!JSON.parse(read("data-uk.json")).series.current_account_q;

  // A. real data
  const A = render("uk.html"); await wait(2500);
  const dA = A.dom.window.document;
  ok(dA.getElementById("loadFail").hidden, "A: uk.html shows the couldn't-load notice with real data " + A.errs.slice(0, 2).join(" | "));
  ok(!!dA.querySelector('.panel[data-key="current_account"]'), "A: annual current account panel missing");
  ok(!!dA.querySelector('.stat[data-key="current_account"]'), "A: annual current account hero tile missing");
  ok(!!dA.querySelector('.panel[data-key="current_account_q"]') === hasReal,
     "A: quarterly panel present=" + !!dA.querySelector('.panel[data-key="current_account_q"]') + " but data has it=" + hasReal);
  const tilesA = dA.querySelectorAll("#hero > .stat").length;

  // B. synthetic quarterly series, in memory only
  const SYN = [["2024-Q3", -2.0], ["2024-Q4", -1.5], ["2025-Q1", -2.5], ["2025-Q2", -3.0], ["2025-Q3", -2.2], ["2025-Q4", -1.8], ["2026-Q1", -2.4], ["2026-Q2", -2.9]];
  const B = render("uk.html", (name, txt) => {
    if (name !== "data-uk.json") return txt;
    const j = JSON.parse(txt);
    j.series.current_account_q = {label: "Current account balance, % of GDP, quarterly (AA6H)", unit: "%", freq: "quarters", points: SYN};
    return JSON.stringify(j);
  });
  await wait(2500);
  const dB = B.dom.window.document, textB = visibleText(dB);
  ok(dB.getElementById("loadFail").hidden, "B: couldn't-load notice shows with the quarterly series " + B.errs.slice(0, 2).join(" | "));
  const panel = dB.querySelector('.panel[data-key="current_account_q"]');
  ok(!!panel, "B: quarterly panel did not render");
  if (panel) {
    ok(/Current account, quarterly/.test(panel.querySelector("h2").textContent), "B: panel title wrong: " + panel.querySelector("h2").textContent);
    ok(!!panel.querySelector("h2 .infoBtn, h2 [data-key], h2 button, h2 .info"), "B: panel has no info icon");
    ok(/Q3 2024 to Q2 2026/.test(panel.querySelector(".range").textContent), "B: range text wrong: " + panel.querySelector(".range").textContent);
    ok(/ONS series AA6H \(PNBP\)/.test(panel.querySelector(".src").textContent) && /quarterly/.test(panel.querySelector(".src").textContent), "B: source line wrong: " + panel.querySelector(".src").textContent);
    const annual = dB.querySelector('.panel[data-key="current_account"]');
    ok(annual && annual.parentElement === panel.parentElement && annual.compareDocumentPosition(panel) & 4, "B: quarterly panel should follow the annual one in the same section");
  }
  ok(!!dB.querySelector('.panel[data-key="current_account"]'), "B: annual panel vanished");
  ok(!!dB.querySelector('.stat[data-key="current_account"]'), "B: annual hero tile vanished");
  ok(!dB.querySelector('.stat[data-key="current_account_q"]'), "B: the quarterly series must not get a hero tile");
  const tilesB = dB.querySelectorAll("#hero > .stat").length;
  ok(tilesB === tilesA && tilesB <= 10, `B: hero tiles changed (${tilesA} to ${tilesB}) or exceed 10`);
  const annualTile = t => (t.querySelector('.stat[data-key="current_account"]') || {}).textContent;
  ok(annualTile(dA) === annualTile(dB), "B: annual tile text changed when the quarterly series was added");
  const bad = textB.match(/\b(NaN|undefined|Infinity|null)\b/g);
  ok(!bad, "B: visible text contains " + (bad ? [...new Set(bad)].join(", ") : ""));

  console.log(`test_uk_current_account_q_render: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
