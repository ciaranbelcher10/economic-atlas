// v1.7.55: with "Make it real" and "Dollarise" both on, the real GDP shown
// in dollars must grow at exactly the published local real rate. Also checks
// the nominal dollar view honours fx.floor and the banner reports it.
// Run: node tools/test_real_dollarise.js
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const PAGES = {egypt:"eg", nigeria:"ng", vietnam:"vn", uk:"uk", poland:"pl", switzerland:"ch", turkey:"tr", argentina:"ar", japan:"jp", peru:"pe", "hong-kong":"hk", iceland:"is", pakistan:"pk"};
function grab(src, start, endRe){
  const i = src.indexOf(start); if(i<0) throw new Error("missing "+start);
  const rest = src.slice(i); const m = rest.search(endRe);
  return rest.slice(0, m<0 ? rest.length : m);
}
function fn(src, name){
  const i = src.indexOf("function "+name+"("); if(i<0) throw new Error("missing function "+name);
  let d=0, j=src.indexOf("{", i);
  for(; j<src.length; j++){ if(src[j]==="{") d++; else if(src[j]==="}" && --d===0) break; }
  return src.slice(i, j+1);
}
let fails = 0, checks = 0;
function ok(c, msg){ checks++; if(!c){ fails++; console.log("FAIL", msg); } }
for(const [page, cc] of Object.entries(PAGES)){
  const src = fs.readFileSync(path.join(ROOT, page+".html"), "utf8");
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, `data-${cc}.json`), "utf8"));
  const code = [
    grab(src, "const CURRENCY_KEYS", /\n/),
    ...["scaleOf","isCurrencyUnit","isAlreadyUSD","convertSeriesToUSD","monthKey","rateForPeriod",
        "hasPreHistoryPoints","realFxYear","convertRealSeriesToUSD","hasPreFloorPoints","buildDisplaySeries"].map(n=>fn(src,n)),
    /NATIVE_SYMBOL_OVERRIDE\s*=/.test(src) ? (src.match(/(?:const|let|var) NATIVE_SYMBOL_OVERRIDE\s*=[^;]*;/)||[""])[0] : "",
  ].join("\n");
  const stub = new Proxy(function(){}, {get:(t,k)=> k===Symbol.toPrimitive ? ()=>"" : stub, apply:()=>stub});
  const ctx = {TOGGLE_STATE:{real:true, dollar:true}, PAGE_DATA:data, console, document:stub, window:stub, localStorage:stub};
  vm.createContext(ctx);
  vm.runInContext(code + "\nthis.buildDisplaySeries=buildDisplaySeries; this.monthKey=monthKey;", ctx);
  if(typeof data.series.gdp_real === "undefined" || !data.fx_to_usd) { console.log("skip", page); continue; }
  const out = ctx.buildDisplaySeries(data.series);
  const loc = data.series.gdp_real.points, usd = out.gdp_real.points;
  ok(loc.length === usd.length, `${page}: gdp_real lost points in dollar view`);
  let worst = 0;
  for(let i=1;i<loc.length;i++){
    const g1 = loc[i][1]/loc[i-1][1], g2 = usd[i][1]/usd[i-1][1];
    worst = Math.max(worst, Math.abs(g1-g2));
  }
  ok(worst < 1e-9, `${page}: real dollar growth differs from local real growth by ${worst}`);
  // the headline gdp_level slot (swapped to real) must match too
  const lvl = out.gdp_level.points, base = (data.series.gdp_real_annual || data.series.gdp_real).points;
  if(lvl.length===base.length && lvl.length>1){
    const n = lvl.length-1;
    ok(Math.abs(lvl[n][1]/lvl[n-1][1] - base[n][1]/base[n-1][1]) < 1e-9, `${page}: headline real dollar growth off`);
  }
  ok(/^\$/.test(out.gdp_real.unit), `${page}: unit not dollarised (${out.gdp_real.unit})`);
  // nominal view honours the floor
  ctx.TOGGLE_STATE.real = false;
  const nom = ctx.buildDisplaySeries(data.series);
  if(data.fx_to_usd.floor && nom.gdp_level){
    const fk = ctx.monthKey(String(data.fx_to_usd.floor));
    ok(nom.gdp_level.points.every(([p])=>ctx.monthKey(p)>=fk), `${page}: nominal dollars before floor`);
  }
  console.log(`ok   ${page.padEnd(12)} real-$ growth max diff ${worst.toExponential(1)}, ref year ${out.gdp_real.real_fx_year}`);
}
// banner text
for(const page of ["egypt","nigeria","vietnam","uk"]){
  const src = fs.readFileSync(path.join(ROOT, page+".html"), "utf8");
  ok(src.includes("const histStart = (fx.floor"), `${page}: banner floor start missing`);
  ok(src.includes("hasPreFloorPoints(s[k], fx)"), `${page}: floor note check missing`);
}
console.log(`${checks} checks, ${fails} failure(s)`);
process.exit(fails ? 1 : 0);
