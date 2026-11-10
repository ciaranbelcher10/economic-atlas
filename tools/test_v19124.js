#!/usr/bin/env node
/* v1.9.124: one GDP per person, in local currency and in US$, on every surface.
 *
 * For every economy with population, the latest GDP per person must print identically on:
 *   - the GDP per capita series itself (data file; US$ via the country page's own converter)
 *   - the country page GDP tile, Per capita on (the page's REAL buildDisplaySeries + pcCalendarYears)
 *   - Compare, Per capita on (REAL compare.html in jsdom)
 *   - Dashboard GDP tile, Per capita on (REAL dashboard.html in jsdom), and its GDP per capita tile
 *   - the GDP indicator page, Per capita on (REAL indicator-kit.js in jsdom)
 * first in local currency, then with Convert to USD$ on. Real data files, raw [period, value]
 * points, no stub loaders. Also: Dashboard toggle stored under eatlas_dashboard_percapita, glow
 * classes, CPI never touched, Taiwan has no per person figure, deficit eligible on the Dashboard.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19124.js
 */
const fs = require("fs"), vm = require("vm"), path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const digits = s => s == null ? null : Math.round(+String(s).replace(/[^\d.]/g, "")) * (/^[\u2212-]/.test(String(s)) ? -1 : 1);

/* economies: the indicator generator's country table */
const GEN = read("generate_indicator_pages.py");
const ECON = [];
for (const m of GEN.matchAll(/^    "([^"]+)":\s*\("([a-z]{2,3})", "([a-z-]+)", "[A-Z]{2}",/gm)){
  const f = "data-" + m[2] + ".json";
  if (!fs.existsSync(path.join(ROOT, f))) continue;
  const d = JSON.parse(read(f));
  if (!d.series || !d.series.gdp_level) continue;
  ECON.push({ country: m[1], file: f, page: m[3] + ".html", d });
}
ok(ECON.length >= 60, "economies: " + ECON.length);

/* ---------- 1. country page: its own code, loaded until nothing is undefined ---------- */
function fnSrc(src, name){
  const i = src.indexOf("\nfunction " + name + "("); if (i < 0) return null;
  let d = 0, j = src.indexOf("{", i);
  for (; j < src.length; j++){ if (src[j] === "{") d++; else if (src[j] === "}" && --d === 0) break; }
  return src.slice(i + 1, j + 1);
}
function declSrc(src, name){
  const m = new RegExp("^(?:const|let|var) " + name + "\\b[^]*?;\\s*$", "m").exec(src);
  if (!m) return null;
  // a multi-line literal: take balanced braces/brackets from the declaration start
  const i = m.index; let d = 0, j = i, started = false;
  for (; j < src.length; j++){
    const ch = src[j];
    if (ch === "{" || ch === "[" || ch === "(") { d++; started = true; }
    else if (ch === "}" || ch === "]" || ch === ")") d--;
    else if (ch === ";" && d === 0) break;
    else if (ch === "\n" && d === 0 && started) break;
  }
  return src.slice(i, j + 1);
}
function countryTile(page, data, dollar){
  const src = read(page);
  // the GDP tile's own per capita line from statTile(), run as written
  const tm = /if\(key === "gdp_level" && typeof PC_APPLIED !== "undefined" && PC_APPLIED\.has\("gdp_level"\) && series\)\n\s*(series = [^\n]+;)/.exec(src);
  if (!tm) throw new Error(page + ": statTile per capita line not found");
  const tileLine = tm[1];
  const names = ["buildDisplaySeries", "pcCalendarYears"];
  for (const n of ["COUNTRY_LABEL", "NATIVE_SYMBOL_OVERRIDE", "PC_ANNUAL_RATE"]) if (declSrc(src, n)) names.push(n);
  let code = "";
  const have = new Set();
  const ctxBase = () => {
    const c = { console, window: {}, Math, JSON, Set, Object, Array, String, Number, isFinite };
    c.window.EA_PC = require(path.join(ROOT, "percapita.js"));
    return c;
  };
  for (let tries = 0; tries < 80; tries++){
    for (const n of names) if (!have.has(n)){ const s = fnSrc(src, n) || declSrc(src, n); if (s){ code += s + "\n"; have.add(n); } }
    const ctx = ctxBase(); vm.createContext(ctx);
    try {
      vm.runInContext(code.replace(/^(const|let) /gm, "var ") +
        `\nvar PAGE_DATA = ${JSON.stringify(data)};\nvar TOGGLE_STATE = {real:false, dollar:${dollar}, capita:true};\n` +
        `var raw = PAGE_DATA.series;\nvar out = buildDisplaySeries(raw);\n` +
        `var series = out.gdp_level;\n${tileLine}\nvar gs = series;\nthis.res = gs && gs.points[gs.points.length - 1];`, ctx);
      return ctx.res ? { year: String(ctx.res[0]), value: ctx.res[1] } : null;
    } catch (e){
      const m = /(\w+) is not defined/.exec(String(e.message));
      if (!m || have.has(m[1]) || names.includes(m[1])) throw new Error(page + ": " + e.message);
      names.push(m[1]);
    }
  }
  throw new Error(page + ": could not load page code");
}

/* ---------- 2. indicator kit ---------- */
const KIT = read("indicator-kit.js"), PCJS = read("percapita.js");
const GDP_RAW = (/^GDP_RAW_COUNTRIES = \{([^}]*)\}/m.exec(GEN) || [, ""])[1].match(/"([^"]+)"/g).map(s => s.slice(1, -1));
function kitTile(e, dollar){
  const S = e.d.series, s = S.gdp_level;
  const dom = new JSDOM(`<body><div id="indFigure"></div><span id="indPeriod"></span><span id="indDelta"></span><span id="indRange"></span>
    <span id="indLed"></span><div id="indActions"></div><button id="indToggleDollar"></button><button id="indTogglePc"></button><p id="indPcNote" hidden></p></body>`,
    { runScripts: "outside-only" });
  const w = dom.window; w.fetch = () => Promise.reject(new Error("offline")); w.matchMedia = () => ({ matches: false });
  w.eval(PCJS); w.eval(KIT);
  const raw = GDP_RAW.includes(e.country);
  const pts = w.EATLAS_FMT.annualise(s.points.filter(p => p && p[1] != null), s.freq, raw);
  const fx = e.country === "US" || e.country === "Switzerland" ? null : e.d.fx_to_usd;
  w.EATLAS_IND.initIndicator({ key: "gdp_level", country: e.country, unit: s.unit, freq: s.freq, upIsGood: true, chart: "line",
    annualise: true, gdpRaw: raw, dataUrl: "x", points: pts, realPoints: null, fx: fx,
    population: S.population.points.filter(p => p[1]).map(p => [String(p[0]), p[1]]), title: "t" });
  if (dollar && fx) w.document.getElementById("indToggleDollar").click();
  w.document.getElementById("indTogglePc").click();
  return { year: w.document.getElementById("indPeriod").textContent, text: w.document.getElementById("indFigure").textContent };
}

/* ---------- 3. Dashboard and Compare in jsdom ---------- */
function bootPage(file, url){
  const html = require("./inline_local_scripts")(read(file), ROOT);
  const store = {}, errs = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if (!/supabase|EATLAS_PREFS|Not implemented|\bd3\b|is not defined: undefined/i.test(m)) errs.push(m); });
  const NM = process.env.NODE_PATH || "/tmp/node_modules";
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, url,
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get(){ return function(){ return { addColorStop(){} }; }; } });
      function C(c, cfg){ this.data = (cfg && cfg.data) || { datasets: [] }; this.options = (cfg && cfg.options) || {}; }
      C.prototype.update = function(){}; C.prototype.destroy = function(){}; C.prototype.resetZoom = function(){}; C.register = function(){};
      win.Chart = C;
      if (/compare/.test(file)){ win.eval(fs.readFileSync(NM + "/d3/dist/d3.min.js", "utf8")); win.eval(fs.readFileSync(NM + "/topojson/dist/topojson.min.js", "utf8")); }
      Object.defineProperty(win, "localStorage", { configurable: true, value: { getItem: k => (k in store ? store[k] : null),
        setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; }, clear(){}, key: () => null, get length(){ return 0; } } });
      win.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.fetch = u => { const f = String(u).split("/").pop().split("?")[0];
        const p = /countries-110m/.test(String(u)) ? NM + "/world-atlas/countries-110m.json" : path.join(ROOT, f);
        if (!fs.existsSync(p)) return Promise.reject(new Error("no " + f));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) }); };
      win.EATLAS_PREFS = { isLoggedIn: () => true, registerBanner(){}, get(){ return null; }, set(){} };
    } });
  return { dom, win: dom.window, store, errs };
}

(async () => {
  /* reference: the data file's GDP per capita, and its US$ figure by the UK page's own converter */
  const ref = {};
  for (const e of ECON){
    const g = e.d.series.gdp_per_capita, pop = e.d.series.population;
    if (!g || !g.points.length || !pop || !pop.points.length) continue;
    const last = g.points[g.points.length - 1];
    ref[e.country] = { year: String(last[0]), native: Math.round(last[1]) };
  }
  ok(Object.keys(ref).length === 61, "61 economies with GDP per capita: " + Object.keys(ref).length);

  /* country pages */
  let cpN = 0, cpU = 0;
  for (const e of ECON){
    const r = ref[e.country]; if (!r) continue;
    const t = countryTile(e.page, e.d, false);
    ok(t && t.year === r.year && Math.round(t.value) === r.native, `${e.country} country page native ${t && Math.round(t.value)} = ${r.native} (${r.year})`);
    cpN++;
    if (e.d.fx_to_usd && e.country !== "US"){
      const u = countryTile(e.page, e.d, true);
      r.usd = u ? Math.round(u.value) : null;   // the country page's dollar figure, checked against every other surface below
      cpU++;
    } else r.usd = r.native;
  }
  ok(cpN === 61 && cpU >= 59, `country pages checked: ${cpN} native, ${cpU} in US$`);

  /* indicator kit */
  for (const e of ECON){
    const r = ref[e.country]; if (!r) continue;
    const n = kitTile(e, false);
    ok(n.year === r.year && digits(n.text) === r.native, `${e.country} indicator page native ${n.text} = ${r.native}`);
    const u = kitTile(e, true);
    ok(u.year === r.year && digits(u.text) === r.usd, `${e.country} indicator page US$ ${u.text} = country page ${r.usd}`);
  }

  /* Dashboard */
  const D = bootPage("dashboard.html", "https://theeconomicatlas.com/dashboard.html");
  await new Promise(r => D.win.addEventListener("load", r, { once: true }));
  for (let i = 0; i < 200 && !(D.win.EATLAS_DASH && D.win.document.querySelector("#dashGrid")); i++) await sleep(50);
  await sleep(1500);
  const dw = D.win, dd = dw.document;
  const ids = Object.keys(ref).flatMap(c => [c + "::gdp_level", c + "::gdp_per_capita"]).concat(["UK::cpi", "UK::deficit", "Taiwan::gdp_level"]);
  ids.forEach(id => dw.EATLAS_DASH.ensurePinned(id)); await sleep(800);
  const tile = id => [...dd.querySelectorAll(".tile")].find(t => t.dataset.id === id);
  const val = id => { const t = tile(id); return t ? t.querySelector(".value").textContent.trim() : null; };
  const cpiBefore = val("UK::cpi"), twBefore = val("Taiwan::gdp_level");
  const btn = dd.getElementById("perCapitaBtn");
  ok(btn && btn.previousElementSibling && btn.previousElementSibling.id === "dollariseBtn", "Dashboard: Per capita third, after Convert to USD$");
  btn.click(); await sleep(400);
  ok(D.store.eatlas_dashboard_percapita === "1", "Dashboard: choice stored under eatlas_dashboard_percapita");
  for (const c of Object.keys(ref)){
    const r = ref[c];
    ok(digits(val(c + "::gdp_level")) === r.native, `${c} Dashboard GDP tile native ${val(c + "::gdp_level")} = ${r.native}`);
    ok(/ per person, \d{4} population$/.test(tile(c + "::gdp_level").querySelector(".period").textContent), `${c} Dashboard period names the population year`);
  }
  ok(tile("UK::gdp_level").classList.contains("fx-pc"), "Dashboard: coral glow on a per capita tile");
  ok(val("UK::cpi") === cpiBefore && !/fx-/.test(tile("UK::cpi").className), "Dashboard: CPI untouched");
  ok(val("Taiwan::gdp_level") === twBefore, "Dashboard: Taiwan (no population) unchanged");
  ok(!tile("UK::deficit") || /per person/.test(tile("UK::deficit").querySelector(".period").textContent) || !/m$|bn$/.test(val("UK::deficit")),
     "Dashboard: deficit is eligible (" + val("UK::deficit") + ")");
  dd.getElementById("dollariseBtn").click(); await sleep(500);
  for (const c of Object.keys(ref)){
    const r = ref[c];
    ok(digits(val(c + "::gdp_level")) === r.usd, `${c} Dashboard GDP tile US$ ${val(c + "::gdp_level")} = country page ${r.usd}`);
    ok(digits(val(c + "::gdp_per_capita")) === r.usd, `${c} Dashboard GDP per capita tile US$ ${val(c + "::gdp_per_capita")} = ${r.usd}`);
  }
  ok(tile("UK::gdp_level").classList.contains("fx-dollar-pc") && /fx-dollar-pc/.test(btn.className), "Dashboard: purple with USD$");
  dd.getElementById("makeRealBtn").click(); await sleep(400);
  ok(tile("UK::gdp_level").classList.contains("fx-all"), "Dashboard: brown with all three");
  ok(D.errs.length === 0, "Dashboard: no page errors: " + D.errs.slice(0, 3).join("; "));

  /* Compare: one economy alone (local currency), then with the US (US$) */
  const Cp = bootPage("compare.html", "https://theeconomicatlas.com/compare");
  await new Promise(r => Cp.win.addEventListener("load", r, { once: true }));
  for (let i = 0; i < 200 && Cp.win.document.getElementById("mainContent").style.display === "none"; i++) await sleep(50);
  await sleep(800);
  const api = Cp.win.EATLAS_COMPARE;
  api.setSelected(["UK"]); await sleep(300);
  if (!api.getMetrics().includes("gdp_level")) api.addMetric("gdp_level");
  await sleep(500);
  const pcb = () => Cp.win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .card-percap-btn');
  if (!api.getPercap("gdp_level")) { pcb().click(); await sleep(300); }
  ok(api.getPercap("gdp_level") === true, "Compare: Per capita on");
  for (const c of Object.keys(ref)){
    const r = ref[c];
    api.setSelected([c]); await sleep(120);
    const n = api.displayValue(c, "gdp_level");
    ok(n && String(n.year) === r.year && Math.round(n.value * 1e6) === r.native, `${c} Compare native ${n && Math.round(n.value * 1e6)} = ${r.native}`);
    if (c === "US") continue;
    api.setSelected([c, "US"]); await sleep(120);
    const u = api.displayValue(c, "gdp_level");
    ok(u && Math.round(u.value * 1e6) === r.usd && /^\$/.test(api.displayString(u)), `${c} Compare US$ ${u && api.displayString(u)} = country page ${r.usd}`);
  }
  /* Compare line chart with Per capita on: each point is that quarter's rolling year over that year's population */
  api.setSelected(["UK"]); await sleep(200);
  const lb = Cp.win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .charttoggle button[data-mode="line"]');
  if (lb){ lb.click(); await sleep(400); }
  const ds = ((api.chartData("gdp_level") || {datasets: []}).datasets || []).find(d => d.label === "UK");
  const uk = ECON.find(e => e.country === "UK").d.series, PC = require(path.join(ROOT, "percapita.js"));
  const q = uk.gdp_level.points.filter(p => /^2025-Q/.test(p[0])), pop25 = PC.popIndex(uk.population.points)["2025"];
  const want = q.reduce((a, p) => a + p[1], 0) * PC.scaleOf(uk.gdp_level.unit) / pop25;
  const pt = ds && ds.data.find(p => p.x === "2025-Q4");
  ok(pt && Math.abs(pt.y * 1e6 - want) < 1, `Compare line, Per capita: UK 2025-Q4 ${pt && pt.y * 1e6} = rolling year / 2025 population ${want}`);
  ok(ds && !ds.data.some(p => /^2026/.test(p.x)), "Compare line, Per capita: no 2026 points (population not yet published)");
  ok(Cp.errs.length === 0, "Compare: no page errors: " + Cp.errs.slice(0, 3).join("; "));

  console.log(`test_v19124: ${checks} checks, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
