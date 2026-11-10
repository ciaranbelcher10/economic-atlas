#!/usr/bin/env node
/* v1.9.120: Chartmaker Per capita through the page's REAL getSeries and REGISTRY shape (no stub).
 * Bug fixed: applyPerCapita/perCapitaNote read population points as {x,y} when REGISTRY holds
 * [period, value] pairs, so every economy reported "no World Bank population" and the chart was empty.
 * Also: the per capita note joins the toggle note with " · ".
 * Run: node tools/test_v19120.js
 */
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
function fn(src, name){
  const i = src.indexOf("function " + name + "("); if (i < 0) throw new Error("missing function " + name);
  let d = 0, j = src.indexOf("{", i);
  for (; j < src.length; j++){ if (src[j] === "{") d++; else if (src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1);
}
function varLit(src, name){
  const i = src.indexOf("var " + name + " ="); if (i < 0) throw new Error("missing var " + name);
  let d = 0, j = src.indexOf("{", i);
  for (; j < src.length; j++){ if (src[j] === "{") d++; else if (src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1) + ";";
}
const cm = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
const FILES = vm.runInNewContext("(" + cm.match(/var FILES\s*=\s*(\{[\s\S]*?\});/)[1] + ")");
const ctx = { console, window: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(ROOT, "percapita.js"), "utf8"), ctx);
ctx.EA_PC = ctx.window.EA_PC;
vm.runInContext(
  "var REGISTRY = {}, series = [], TOGGLE_STATE = {percap: true};\n" +
  ["CONCEPT_KEYS", "CONCEPT_UNIT", "CONCEPT_LABEL"].map(v => varLit(cm, v)).join("\n") + "\n" +
  "function resolveGDPPoints(reg, concept, country, raw){ return raw.points; }\n" +
  ["unitCompatible", "getSeries", "applyPerCapita", "perCapitaNote"].map(n => fn(cm, n)).join("\n") + "\n" +
  "this.setReg = function(r){ REGISTRY = r; }; this.setSeries = function(s){ series = s; };\n" +
  "this.applyPerCapita = applyPerCapita; this.perCapitaNote = perCapitaNote; this.getSeries = getSeries;", ctx);

// REGISTRY built exactly as loadAllCountryData does: raw payload.series entries, points untouched
const reg = {};
let withPop = 0, noPop = [];
for (const c of Object.keys(FILES)){
  const f = path.join(ROOT, FILES[c]); if (!fs.existsSync(f)) continue;
  const series = JSON.parse(fs.readFileSync(f, "utf8")).series || {};
  reg[c] = {};
  for (const k of Object.keys(series)){ const s = series[k]; if (s && Array.isArray(s.points) && s.points.length) reg[c][k] = s; }
}
ctx.setReg(reg);
ok(Object.keys(reg).length >= 60, "data files loaded for " + Object.keys(reg).length + " economies");

const PC = ctx.EA_PC;
for (const c of Object.keys(reg)){
  const g = ctx.getSeries(c, "gdp_level"); if (!g) continue;
  const pts = g.points.map(p => ({ x: p[0], y: p[1] }));
  const out = ctx.applyPerCapita(c, "gdp_level", { unit: g.unit, pts: pts.slice() }, true);
  const pop = reg[c].population;
  if (!pop){ noPop.push(c); ok(out.pcNoPop === true, c + ": no population, flagged"); continue; }
  withPop++;
  ok(out.perCapita === true && !out.pcNoPop, c + ": per capita applied (population is present)");
  ok(out.pts.length > 0, c + ": per capita series not empty");
  const idx = PC.popIndex(pop.points);
  const p0 = pts.find(p => idx[String(p.x).slice(0, 4)]);
  const q0 = p0 && out.pts.find(q => q.x === p0.x);
  ok(q0 && Math.abs(q0.y - p0.y * PC.scaleOf(g.unit) / idx[String(p0.x).slice(0, 4)]) < 1e-6 * Math.abs(q0.y), c + ": value = total / same-year population");
}
ok(withPop >= 55, "per capita works for " + withPop + " economies with population");
ok(noPop.every(c => /Taiwan/.test(c)), "only Taiwan lacks population (" + noPop.join(", ") + ")");

// UK annual 2025 per person matches the verified £43,815 (annual sum of quarters if quarterly)
{
  const g = ctx.getSeries("UK", "gdp_level");
  const y25 = g.points.filter(p => String(p[0]).startsWith("2025"));
  const total = y25.reduce((a, p) => a + p[1], 0);
  const per = total * PC.scaleOf(g.unit) / PC.popIndex(reg.UK.population.points)["2025"];
  const full = (g.freq === "years") || y25.length === 4;
  ok(!full || Math.abs(Math.round(per) - 43815) <= 1, "UK 2025 GDP per person = £43,815 (got " + Math.round(per) + ")");
}

// note: no "no World Bank population" for economies that have it
ctx.setSeries(["UK", "US", "Germany"].map(c => {
  const g = ctx.getSeries(c, "gdp_level");
  return { country: c, metric: "gdp_level", display: ctx.applyPerCapita(c, "gdp_level", { unit: g.unit, pts: g.points.map(p => ({ x: p[0], y: p[1] })) }, true) };
}));
const n = ctx.perCapitaNote();
ok(!/not available/.test(n) && /that year/.test(n), "note for UK, US, Germany is the exact-year wording (" + n.trim().slice(0, 60) + ")");

// gap in population (synthetic copy of UK without 2010): 2010 named as a missing year, not "not yet published"
{
  const uk = JSON.parse(JSON.stringify(reg.UK));
  uk.population.points = uk.population.points.filter(p => String(p[0]) !== "2010");
  ctx.setReg(Object.assign({}, reg, { UKGAP: uk }));
  const g = ctx.getSeries("UKGAP", "gdp_level");
  ctx.setSeries([{ country: "UKGAP", metric: "gdp_level", display: ctx.applyPerCapita("UKGAP", "gdp_level", { unit: g.unit, pts: g.points.map(p => ({ x: p[0], y: p[1] })) }, true) }]);
  const n2 = ctx.perCapitaNote();
  ok(/2010 not shown: no population figure/.test(n2) && !/2010[^.]*not yet published/.test(n2), "population gap year named as missing (" + n2.trim() + ")");
  ctx.setReg(reg);
}

// separator between the toggle note and the per capita note
ok(/tn && pn\) \? tn \+ " \\u00b7 " \+ pn : \(tn \|\| pn\)/.test(cm), "notes joined with ' · '");
ok(!/note\.textContent = buildToggleNote\(\) \+ perCapitaNote\(\)/.test(cm), "old unseparated join gone");

console.log(`test_v19120: ${checks} checks, ${failures} failed`);
process.exit(failures ? 1 : 0);
