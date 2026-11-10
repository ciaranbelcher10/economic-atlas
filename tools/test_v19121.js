#!/usr/bin/env node
/* v1.9.121: Chartmaker per capita polish.
 *  1. Missing-year runs read "1955 to 1959" (percapita.js listYears); every missing year still named.
 *  2. Per capita axis title says "per person" (syncAutoYAxisTitle), only when every live series is per capita.
 *  3. The y axis never has just two labels (czmAxisBounds, currentYTickStep): index 0 on a per capita
 *     range gave £0 and £100,000 only.
 * Run: node tools/test_v19121.js
 */
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const eq = (a, b, m) => ok(a === b, `${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
function fn(src, name){
  const i = src.indexOf("function " + name + "("); if (i < 0) throw new Error("missing function " + name);
  let d = 0, j = src.indexOf("{", i);
  for (; j < src.length; j++){ if (src[j] === "{") d++; else if (src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1);
}
const cm = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
const PC = require(path.join(ROOT, "percapita.js"));

/* 1. year lists */
eq(PC.listYears(["2026"]), "2026", "one year");
eq(PC.listYears(["2025", "2026"]), "2025 and 2026", "two consecutive years stay listed");
eq(PC.listYears(["1955", "1956", "1957", "1958", "1959"]), "1955 to 1959", "run of five");
eq(PC.listYears(["1957", "1958", "1959"]), "1957 to 1959", "run of three");
eq(PC.listYears(["1990", "1995", "2001"]), "1990, 1995 and 2001", "separate years");
eq(PC.listYears(["1955", "1956", "1957", "1960", "1970", "1971"]), "1955 to 1957, 1960, 1970 and 1971", "mixed runs");
eq(PC.listYears([]), "", "empty");
eq(PC.note(["1955", "1956", "1957", "1958", "1959", "2026"], "2025"),
  "Per capita: each value divided by that year\u2019s population (World Bank). 2026 not shown: population for 2026 not yet published. 1955 to 1959 not shown: no population figure for those years.",
  "UK note as seen live, shortened");

/* 2. axis title */
const doc = { el: { value: "" }, getElementById(){ return this.el; } };
const ctx = { console, document: doc, style: {}, yAxisTitleTouched: false, series: [],
  UNIT_AXIS_LABEL: { "%": "%", pp: "Percentage points", index: "Index" } };
vm.createContext(ctx);
vm.runInContext(fn(cm, "syncAutoYAxisTitle") + "\nthis.sync = syncAutoYAxisTitle;", ctx);
ctx.isCurrencySeries = () => true;
ctx.currencyAxisTitle = () => "Pounds sterling";
ctx.effectiveUnits = () => ["£"];
const title = ser => { ctx.series = ser; ctx.sync(); return ctx.style.yAxisTitle; };
eq(title([{ transform: "raw", display: { perCapita: true } }]), "Pounds sterling per person", "per capita title");
eq(title([{ transform: "raw", display: { perCapita: false } }]), "Pounds sterling", "total title unchanged");
eq(title([{ transform: "raw", display: { perCapita: true } }, { transform: "raw", display: { perCapita: false } }]), "Pounds sterling", "mixed: no per person claim");
eq(title([{ transform: "raw", display: { perCapita: true } }, { missing: true, transform: "raw" }]), "Pounds sterling per person", "missing series ignored");
ctx.currencyAxisTitle = () => "";
eq(title([{ transform: "raw", display: { perCapita: true } }]), "", "no currency name: nothing invented");
ok(doc.el.value === ctx.style.yAxisTitle, "input box mirrors the title");

/* 3. never a two-label axis */
const ax = {}; vm.createContext(ax);
vm.runInContext(["niceNum", "niceTicksFromStep", "niceStepCandidates", "defaultStepIdxFor", "czmAxisBounds", "niceLogTicks"].map(n => fn(cm, n)).join("\n") +
  "\nthis.bounds = czmAxisBounds; this.cands = niceStepCandidates; this.ticks = niceTicksFromStep;", ax);
const b = ax.bounds(0, 44000, 0, false, false, 0, false);
ok(b.ticks.length >= 3 && b.maxV < 100000, "UK per capita range at index 0: " + JSON.stringify(b.ticks));
let worst = 99;
for (const [lo, hi] of [[0, 44000], [0, 770000], [-39447, 12000], [0, 3.8], [1.2, 9.7], [0, 90294], [100, 2500000]]){
  const n = ax.cands(lo, hi).length;
  for (let i = 0; i < n + 2; i++){ worst = Math.min(worst, ax.bounds(lo, hi, i, false, false, 0, false).ticks.length); }
}
ok(worst >= 3, "no index on any range gives fewer than 3 labels (worst " + worst + ")");
const mid = ax.bounds(0, 44000, 2, false, false, 0, false);
eq(JSON.stringify(mid.ticks), JSON.stringify(ax.ticks(0, 44000, ax.cands(0, 44000)[2]).ticks), "a readable chosen step is left alone");
ok(/ticks\.length < 3\) i = defaultStepIdxFor\(r\.lo, r\.hi, 5\)/.test(fn(cm, "currentYTickStep")), "saved step follows the same rule");

console.log(`test_v19121: ${checks} checks, ${failures} failed`);
process.exit(failures ? 1 : 0);
