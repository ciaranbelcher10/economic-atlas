// v1.8.3: the v1.7.55 Real/Dollarise rules, ported to Compare, Dashboard and
// ChartMaker, checked on every country's real data file:
//   1. real GDP in dollars grows exactly as the published local real series
//      (one rate, the latest year's), in all three views;
//   2. nominal currency points before fx.floor have no dollar value;
//   3. after the floor, all three views give the same dollar figure for the
//      same nominal point (no view drifts from the others).
// Run: node tools/test_views_dollarise.js
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
function fn(src, name){
  const i = src.indexOf("function " + name + "("); if(i < 0) throw new Error("missing function " + name);
  let d = 0, j = src.indexOf("{", i);
  for(; j < src.length; j++){ if(src[j] === "{") d++; else if(src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1);
}
function load(file, names, extra){
  const src = fs.readFileSync(path.join(ROOT, file), "utf8");
  const ctx = {console};
  vm.createContext(ctx);
  vm.runInContext(names.map(n => fn(src, n)).join("\n") + "\n" + (extra || "") + "\n" +
    names.map(n => `this.${n}=${n};`).join(""), ctx);
  return {ctx, src};
}
let fails = 0, checks = 0;
function ok(c, msg){ checks++; if(!c){ fails++; console.log("FAIL", msg); } }

const cmpSrc = fs.readFileSync(path.join(ROOT, "compare.html"), "utf8");
const FILES = vm.runInNewContext("(" + cmpSrc.match(/var FILES\s*=\s*(\{[\s\S]*?\});/)[1] + ")");

const C = load("compare.html", ["monthKey", "rateForPeriod", "toUSDValue", "isBeforeFxFloor", "realFxYearFor"],
  "var FX_RATES = {}, REGISTRY = {}; function resolveKey(c, k){ return REGISTRY[c] && REGISTRY[c][k] ? k : null; }" +
  "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };");
const D = load("dashboard.html", ["monthKey", "rateForPeriod", "isRealGDPKey", "realFxYearFor", "usdRateFor",
  "toUSDValue", "toDisplayPoints", "isCurrencyUnit", "isAlreadyUSD", "foreignCurrencyOf"],
  (src => (src.match(/var CURRENCY_GLYPH_CODE[^\n]*/) || [""])[0])(fs.readFileSync(path.join(ROOT, "dashboard.html"), "utf8")) + "\n" + "var FX_RATES = {}, REGISTRY = {}, dollarise = true, DOLLAR_GLYPH_LOCAL_CURRENCY_COUNTRIES = {Australia:1, Canada:1, Mexico:1, \"South Africa\":1, Brazil:1};" +
  "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };");
const M = load("chartmaker.html", ["monthKey", "rateForPeriod", "nearestFxYear", "toUSDValue"],
  "var FX_RATES = {}; this.setData = function(f){ FX_RATES = f; };");

let tested = 0;
for(const [country, file] of Object.entries(FILES)){
  if(country === "US") continue;
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, file), "utf8"));
  const fx = data.fx_to_usd, s = data.series || {};
  if(!fx || !fx.rate) continue;
  const fxr = {[country]: fx}, reg = {[country]: s};
  C.ctx.setData(fxr, reg); D.ctx.setData(fxr, reg); M.ctx.setData(fxr);
  tested++;
  // 1. real GDP growth preserved
  for(const rk of ["gdp_real", "gdp_real_annual"]){
    const real = s[rk];
    if(!real || real.points.length < 2) continue;
    const pts = real.points, yr = String(pts[pts.length - 1][0]).slice(0, 4);
    const conv = {
      compare: rk === "gdp_real" ? pts.map(p => C.ctx.toUSDValue(country, p[1], String(p[0]), "gdp_real")) : null,
      dashboard: D.ctx.toDisplayPoints(pts, real.unit, country, rk).map(p => p[1]),
      chartmaker: pts.map(p => M.ctx.toUSDValue(country, p[1], String(p[0]), yr)),
    };
    for(const [view, v] of Object.entries(conv)){
      if(!v) continue;
      if(D.ctx.isAlreadyUSD(real.unit, country, rk) && view === "dashboard") continue;
      ok(v.length === pts.length && v.every(x => x != null), `${country} ${view}: real ${rk} lost points`);
      let worst = 0;
      for(let i = 1; i < pts.length; i++) worst = Math.max(worst, Math.abs(pts[i][1] / pts[i-1][1] - v[i] / v[i-1]));
      ok(worst < 1e-9, `${country} ${view}: real ${rk} dollar growth off by ${worst}`);
    }
  }
  // 2 + 3. nominal level: floor honoured, views agree
  const nom = s.gdp_level;
  if(nom && !D.ctx.isAlreadyUSD(nom.unit, country, "gdp_level")){
    const fk = fx.floor ? C.ctx.monthKey(String(fx.floor)) : null;
    const dpts = new Map(D.ctx.toDisplayPoints(nom.points, nom.unit, country, "gdp_level"));
    for(const [p, v] of nom.points){
      const pre = fk !== null && C.ctx.monthKey(String(p)) < fk;
      const c = C.ctx.toUSDValue(country, v, String(p), "gdp_level");
      const m = M.ctx.toUSDValue(country, v, String(p), null);
      const d = dpts.has(p) ? dpts.get(p) : null;
      if(pre){
        ok(c === null && m === null && d === null, `${country}: ${p} is before the ${fx.floor} floor but has a dollar value`);
      } else {
        ok(c != null && m != null && d != null && Math.abs(c / m - 1) < 1e-12 && Math.abs(d / m - 1) < 1e-12,
           `${country}: views disagree on ${p} (${c}, ${d}, ${m})`);
      }
    }
  }
}
// the Compare footnote and Dashboard note describe the rule
ok(/Real GDP is the exception: it is converted at one rate/.test(cmpSrc), "Compare footnote names the real-GDP rule");
ok(/real GDP at its latest year&#39;s rate|real GDP at its latest year's rate/.test(fs.readFileSync(path.join(ROOT, "dashboard.html"), "utf8")),
   "Dashboard toggle note names the real-GDP rule");
console.log(`${tested} countries, ${checks} checks, ${fails} failures`);
process.exit(fails ? 1 : 0);
