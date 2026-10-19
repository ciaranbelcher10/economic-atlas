#!/usr/bin/env node
/* Dollarise parity: the same figure must come out the same on every surface.
 *
 * Reference = the country page's own converters (convertSeriesToUSD for nominal series,
 * convertRealSeriesToUSD for real GDP; the conversion core is identical on all 61 non-US pages,
 * and this test checks that too). Each other surface's OWN functions are then run on the same
 * raw points from the same data file and must give the same dollar value at every period:
 *   - Compare    toUSDMillions()
 *   - Dashboard  toDisplayPoints()
 *   - ChartMaker computeDisplay()
 * Levels are compared, not just growth: nominal in every case, real GDP at its one rate.
 * A series that one surface converts and another leaves alone shows up as a value mismatch.
 *
 * Also checked: the country pages agree with each other (same conversion code), and every page
 * that ships a data file with an FX block is covered (no country silently skipped).
 *
 * Run:    node tools/test_dollarise_parity.js
 * Other tree (used by the mutation checks): ATLAS_ROOT=/path/to/tree node tools/test_dollarise_parity.js
 */
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = process.env.ATLAS_ROOT ? path.resolve(process.env.ATLAS_ROOT) : path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const perSurface = {compare: 0, dashboard: 0, chartmaker: 0}, skipped = [];
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = (c, m) => { checks++; if (!c) fail(m); };
const close = (a, b) => Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(a), Math.abs(b));

function fn(src, name){
  const i = src.indexOf("function " + name + "("); if(i < 0) throw new Error("missing function " + name);
  let d = 0, j = src.indexOf("{", i);
  for(; j < src.length; j++){ if(src[j] === "{") d++; else if(src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1);
}
function varLit(src, name){
  const i = src.indexOf("var " + name + " ="); if(i < 0) throw new Error("missing var " + name);
  let d = 0, j = src.indexOf("{", i);
  for(; j < src.length; j++){ if(src[j] === "{") d++; else if(src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1) + ";";
}
function grab(src, start, endRe){
  const i = src.indexOf(start); if(i < 0) throw new Error("missing " + start);
  const rest = src.slice(i), m = rest.search(endRe);
  return rest.slice(0, m < 0 ? rest.length : m);
}
function load(src, names, pre, post){
  const ctx = {console};
  vm.createContext(ctx);
  vm.runInContext((pre || "") + "\n" + names.map(n => fn(src, n)).join("\n") + "\n" + (post || "") + "\n" +
    names.map(n => `this.${n}=${n};`).join(""), ctx);
  return ctx;
}
const norm0 = s => s.replace(/\/\/[^\n]*/g, "").replace(/\s+/g, " ").trim();
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");

const cmpSrc = read("compare.html"), dashSrc = read("dashboard.html"), cmSrc = read("chartmaker.html");
const FILES = vm.runInNewContext("(" + cmpSrc.match(/var FILES\s*=\s*(\{[\s\S]*?\});/)[1] + ")");
const glyphOf = src => grab(src, "var DOLLAR_GLYPH_LOCAL_CURRENCY_COUNTRIES", /;/) + ";"; // each page's OWN list

const C = load(cmpSrc, ["monthKey", "rateForPeriod", "scaleOf", "isAlreadyUSDUnit", "isBeforeFxFloor", "realFxYearFor", "toUSDValue", "toUSDMillions", "unitCompatible"],
  glyphOf(cmpSrc) + varLit(cmpSrc, "CONCEPT_UNIT") + "var FX_RATES = {}, REGISTRY = {}; function resolveKey(c, k){ return REGISTRY[c] && REGISTRY[c][k] ? k : null; }" +
  "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };");
const D = load(dashSrc, ["monthKey", "rateForPeriod", "scaleOf", "isRealGDPKey", "realFxYearFor", "usdRateFor", "toUSDValue", "toDisplayPoints", "isCurrencyUnit", "isAlreadyUSD"],
  glyphOf(dashSrc) + "var FX_RATES = {}, REGISTRY = {}, dollarise = true;" + "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };");
const M = load(cmSrc, ["monthKey", "rateForPeriod", "nearestFxYear", "scaleOf", "isAlreadyUSDUnit", "toUSDValue", "toUSDMillions", "forceUSDUnit", "computeDisplay", "unitCompatible"],
  glyphOf(cmSrc) + varLit(cmSrc, "CONCEPT_UNIT") + "var FX_RATES = {}, REGISTRY = {}; function getSeries(){ return null; }" +
  "this.setData = function(f){ FX_RATES = f; };");

ok(norm0(fn(cmpSrc, "unitCompatible")) === norm0(fn(cmSrc, "unitCompatible")), "ChartMaker's unitCompatible differs from Compare's");

/* country pages: one per data file */
const pages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && read(f).includes("function convertSeriesToUSD(") && f !== "us.html");
const pageFor = {};
for(const p of pages){ const m = read(p).match(/data-([a-z]{2})\.json/); if(m) pageFor["data-" + m[1] + ".json"] = p; }

/* the conversion core must be the same text on every non-US country page */
const CORE = ["convertSeriesToUSD", "convertRealSeriesToUSD", "realFxYear", "rateForPeriod", "monthKey", "scaleOf", "isCurrencyUnit"];
const norm = s => s.replace(/\/\/[^\n]*/g, "").replace(/\s+/g, " ").trim();
for(const n of CORE){
  const ref = norm(fn(read("uk.html"), n));
  for(const p of pages) ok(norm(fn(read(p), n)) === ref, `${p}: ${n} differs from the other country pages`);
}

function pageCtx(p, data){
  const src = read(p);
  const nso = (src.match(/^const NATIVE_SYMBOL_OVERRIDE\s*=\s*[^;\n]*;/m) || [""])[0];
  const code = [
    nso,
    grab(src, "const CURRENCY_KEYS", /\n/),
    ...["scaleOf", "isCurrencyUnit", "isAlreadyUSD", "monthKey", "rateForPeriod", "convertSeriesToUSD", "realFxYear", "realFxRateYear", "convertRealSeriesToUSD"].map(n => fn(src, n)),
  ].join("\n");
  const ctx = {PAGE_DATA: data, console};
  vm.createContext(ctx);
  vm.runInContext(code + "\nthis.CURRENCY_KEYS=CURRENCY_KEYS;this.scaleOf=scaleOf;this.isCurrencyUnit=isCurrencyUnit;this.isAlreadyUSD=isAlreadyUSD;" +
    "this.convertSeriesToUSD=convertSeriesToUSD;this.convertRealSeriesToUSD=convertRealSeriesToUSD;", ctx);
  ctx.hasNativeOverride = !!nso;
  return ctx;
}

const EXTRA_KEYS = ["debt_interest", "gdp_real_annual", "gdp_level_annual"]; // keys another surface treats as currency
// Synthetic edge case no live country reaches today: the FX history ends (2022-12) before the real
// series does (2025), so every surface has to pick a rate year by "nearest". They must pick alike.
const rateWalk = []; for(let y = 2020; y <= 2022; y++) for(let m = 1; m <= 12; m++) rateWalk.push([`${y}-${String(m).padStart(2, "0")}`, 1 + 0.013 * ((y - 2020) * 12 + m)]);
const SYNTH = {country: "Testland", file: null, page: "uk.html", data: {fx_to_usd: {pair: "TST/USD", rate: 1.5, direction: "multiply", history: rateWalk},
  series: {gdp_real: {unit: "TSTm", points: [["2025-Q1", 100], ["2025-Q2", 101], ["2025-Q3", 103], ["2025-Q4", 104]]},
           gdp_level: {unit: "TSTm", points: [["2025-Q1", 120], ["2025-Q2", 123], ["2025-Q3", 127], ["2025-Q4", 130]]}}}};
const jobs = [];
for(const [country, file] of Object.entries(FILES)){
  if(country === "US") continue;
  const data = JSON.parse(read(file));
  if(!data.fx_to_usd || !data.fx_to_usd.rate){ skipped.push(country + " (no fx block)"); continue; }
  if(!pageFor[file]){ fail(`${country}: no country page found for ${file}`); continue; }
  jobs.push({country, file, page: pageFor[file], data});
}
jobs.push(SYNTH);
let tested = 0;
for(const {country, page: p, data} of jobs){
  const fx = data.fx_to_usd, s = data.series || {};
  const P = pageCtx(p, data);
  const fxr = {[country]: fx}, reg = {[country]: s};
  C.setData(fxr, reg); D.setData(fxr, reg); M.setData(fxr);
  tested++;

  const keys = [...new Set([...P.CURRENCY_KEYS, ...EXTRA_KEYS])].filter(k => s[k] && s[k].points && s[k].points.length);
  for(const key of keys){
    const raw = s[key], isReal = key === "gdp_real" || key === "gdp_real_annual";
    if(!P.isCurrencyUnit(raw.unit)) continue;
    // gdp_level_annual / gdp_real_annual only ever reach the screen as the "GDP (Annual)" card, i.e. in
    // gdp_level's place, so the pages convert them under the gdp_level rules (real view: one rate)
    const pageKey = /_annual$/.test(key) ? "gdp_level" : key;
    const pageConverts = P.CURRENCY_KEYS.includes(pageKey) && !P.isAlreadyUSD(raw.unit, pageKey);
    // expected dollar value per period, in the series' own scale; null = left out (before the floor)
    let exp;
    if(pageConverts){
      const conv = isReal ? P.convertRealSeriesToUSD(raw, fx) : P.convertSeriesToUSD(raw, fx);
      exp = new Map(conv.points.map(q => [q[0], q[1]]));
    } else {
      exp = new Map(raw.points.map(q => [q[0], q[1]]));
    }
    const scale = P.scaleOf(raw.unit) / 1e6, label = `${country} ${key}`;
    // Compare and ChartMaker only ever ask for gdp_level / gdp_real and swap the annual points in
    // themselves (resolveGDPPoints), so that is the concept they are driven with for annual series
    const concept = key === "gdp_level_annual" ? "gdp_level" : key === "gdp_real_annual" ? "gdp_real" : key;

    // A surface only shows a series whose unit fits the metric (unitCompatible). One it does not
    // offer cannot disagree; it is checked as "not offered" instead.
    const cOffers = C.unitCompatible(concept, raw), mOffers = M.unitCompatible(concept, raw);
    ok(cOffers === mOffers, `${label}: Compare ${cOffers ? "offers" : "hides"} it but ChartMaker ${mOffers ? "offers" : "hides"} it`);
    // ---- Compare
    if(cOffers) for(const [per, v] of raw.points){
      const got = C.toUSDMillions(country, v, raw.unit, concept, String(per));
      const e = exp.has(per) ? exp.get(per) * scale : null;
      perSurface.compare++;
      if(e === null) ok(got === null, `${label} ${per}: Compare shows a dollar figure the page leaves out`);
      else ok(got !== null && close(got, e), `${label} ${per}: Compare ${got} vs page ${e}`);
    }
    // ---- Dashboard
    const dpts = new Map(D.toDisplayPoints(raw.points, raw.unit, country, key));
    for(const [per] of raw.points){
      const got = dpts.has(per) ? dpts.get(per) : null, e = exp.has(per) ? exp.get(per) : null;
      perSurface.dashboard++;
      if(e === null) ok(got === null, `${label} ${per}: Dashboard shows a dollar figure the page leaves out`);
      else ok(got !== null && close(got, e), `${label} ${per}: Dashboard ${got} vs page ${e}`);
    }
    // ---- ChartMaker
    if(!mOffers) continue;
    const cm = M.computeDisplay(country, concept, raw.unit, raw.points.map(q => ({x: q[0], y: q[1]})), false, true);
    const mpts = new Map(cm.pts.map(q => [q.x, q.y]));
    for(const [per] of raw.points){
      const got = mpts.has(per) ? mpts.get(per) : null, e = exp.has(per) ? exp.get(per) * scale : null;
      perSurface.chartmaker++;
      if(e === null) ok(got === null, `${label} ${per}: ChartMaker shows a dollar figure the page leaves out`);
      else ok(got !== null && close(got, e), `${label} ${per}: ChartMaker ${got} vs page ${e}`);
    }
  }
}

const nativePages = new Set(), nameOfFile = {};
for(const [c, f] of Object.entries(FILES)) nameOfFile[f] = c;
// The override only decides a conversion where a convertible series is literally $-prefixed (AUD, CAD,
// MXN, ZAR, BRL). Chile and Colombia define it for display only: their series are CLPm / COPm.
const dollarPrefixed = f => { const sr = JSON.parse(read(f)).series || {};
  return ["gdp_level", "gdp_real", "trade_balance", "exports", "imports"].some(k => sr[k] && /^\$/.test(sr[k].unit || "")); };
for(const [f, p] of Object.entries(pageFor)) if(/^const NATIVE_SYMBOL_OVERRIDE\s*=/m.test(read(p)) && dollarPrefixed(f)) nativePages.add(nameOfFile[f]);
const listOf = src => new Set(Object.keys(vm.runInNewContext("(" + src.match(/DOLLAR_GLYPH_LOCAL_CURRENCY_COUNTRIES\s*=\s*(\{[^}]*\})/)[1] + ")")));
for(const [n, src] of [["Compare", cmpSrc], ["Dashboard", dashSrc], ["ChartMaker", cmSrc]]){
  const l = listOf(src);
  ok([...nativePages].sort().join() === [...l].sort().join(),
     `${n}'s \$-glyph country list [${[...l].sort()}] differs from the pages that define NATIVE_SYMBOL_OVERRIDE [${[...nativePages].sort()}]`);
}

/* ChartMaker's real getSeries() (the one lookup behind its pickers, add-series list and saved charts)
   must hide every series whose unit does not fit the metric, e.g. UK/US borrowing in £m/$m under
   "Government deficit, % of GDP". GDP's annual swap is stubbed: it does not affect what is offered. */
const G = load(cmSrc, ["unitCompatible", "getSeries"],
  varLit(cmSrc, "CONCEPT_KEYS") + varLit(cmSrc, "CONCEPT_UNIT") + varLit(cmSrc, "CONCEPT_LABEL") +
  "var REGISTRY = {}; function resolveGDPPoints(reg, c, country, raw){ return raw.points; } this.setReg = function(r){ REGISTRY = r; };");
const CK = vm.runInNewContext("(" + varLit(cmSrc, "CONCEPT_KEYS").replace(/^var CONCEPT_KEYS =\s*/, "").replace(/;$/, "") + ")");
let offeredChecks = 0;
for(const [country, file] of Object.entries(FILES)){
  const sr = JSON.parse(read(file)).series || {};
  G.setReg({[country]: sr});
  for(const [concept, cands] of Object.entries(CK)){
    const fits = cands.filter(k => sr[k]).some(k => C.unitCompatible(concept, sr[k]));
    offeredChecks++;
    ok(!!G.getSeries(country, concept) === fits, `${country} ${concept}: ChartMaker ${fits ? "hides" : "offers"} it but its unit ${fits ? "fits" : "does not fit"} the metric`);
  }
}
ok(offeredChecks > 1000, `only ${offeredChecks} ChartMaker offer checks ran`);

const withData = Object.keys(FILES).filter(c => c !== "US").length;
ok(tested - 1 + skipped.length === withData, `covered ${tested} + skipped ${skipped.length} != ${withData} countries`);
console.log(`${tested - 1} countries + 1 synthetic edge case, ${checks} checks (Compare ${perSurface.compare}, Dashboard ${perSurface.dashboard}, ChartMaker ${perSurface.chartmaker} points), ${failures} failures` +
  (skipped.length ? `, skipped: ${skipped.join(", ")}` : ""));
process.exit(failures ? 1 : 0);
