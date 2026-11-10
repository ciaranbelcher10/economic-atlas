#!/usr/bin/env node
/* v1.9.122: Per capita on the 62 country pages, and the Chartmaker axis title clear of its labels.
 *
 * Runs the REAL code on the REAL data path: each page's own pcSeries / pcCalendarYears / curFmt,
 * the real percapita.js, and each economy's real data-*.json (population as [period, value] pairs).
 *  1. Every country page: Per capita button third in the row, percapita.js?v=3 loaded before the
 *     page script, combination glow classes, period-line wording, idempotency marker.
 *  2. Every economy with population: the GDP tile with Per capita on equals the page's own
 *     GDP per capita tile (latest complete calendar year), including US/Japan (annual-rate
 *     quarters) and Poland/Turkey (trailing four-quarter sums).
 *  3. Eligible keys incl. deficit are divided by that year's population only; years without
 *     population are dropped; CPI and other non-currency keys are never touched.
 *  4. Per person formatting: whole units with the page's own symbol (A$, not $), never "£0m".
 *  5. Chartmaker: the rotated y title never overlaps the widest tick label (screen and PNG share it).
 * Run: node tools/test_v19122.js
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
function constLine(src, name){
  const m = new RegExp("^const " + name + "\\s*=.*$", "m").exec(src);
  return m ? m[0] : "";
}
const PC = require(path.join(ROOT, "percapita.js"));
const SKIP = new Set(["chartmaker.html", "compare.html", "dashboard.html"]);
const pages = fs.readdirSync(ROOT).filter(f => f.endsWith(".html") && !SKIP.has(f))
  .filter(f => fs.readFileSync(path.join(ROOT, f), "utf8").includes('id="toggleDollar"')).sort();
ok(pages.length === 62, "62 country pages, got " + pages.length);
ok(PC.ELIGIBLE.includes("deficit") && PC.ELIGIBLE.length === 8, "deficit eligible (8 keys)");

function dataFor(src){
  // the page's main data file: the fetched data-*.json whose series include population or GDP
  const files = [...new Set([...src.matchAll(/fetch\(\s*["'`]\/?(data-[a-z0-9-]+\.json)/g)].map(m => m[1]))];
  for (const fname of files){
    const p = path.join(ROOT, fname); if (!fs.existsSync(p)) continue;
    const d = JSON.parse(fs.readFileSync(p, "utf8")), S = d.series || d;
    if (S && (S.gdp_level || S.population)) return S;
  }
  return null;
}

let parityPages = 0, disabledPages = 0;
for (const f of pages){
  const src = fs.readFileSync(path.join(ROOT, f), "utf8");
  /* 1. markup */
  const iR = src.indexOf('id="toggleReal"'), iD = src.indexOf('id="toggleDollar"'), iC = src.indexOf('id="toggleCapita"');
  ok(iR > 0 && iR < iD && iD < iC, f + ": order Adjust for inflation | Convert to USD$ | Per capita");
  ok(/>Per capita\n <\/button>/.test(src), f + ": button label");
  // v1.9.125: percapita.js is now v4 (population wording); the page must load the current version once
  ok(src.split('<script src="percapita.js?v=4"></script>').length === 2 && !/percapita\.js\?v=[0-3]\b/.test(src), f + ": percapita.js?v=4 loaded exactly once");
  ok(src.split("v1.9.122 per capita").length - 1 >= 1, f + ": migration marker");
  for (const [c, col] of [["fx-pc", "#E06A5A"], ["fx-real-pc", "#E8853A"], ["fx-dollar-pc", "#8E63C9"], ["fx-all", "#8A5A3C"]])
    ok(src.includes(".stat." + c + ", .panel." + c + "{border-color:" + col), f + ": glow " + c);
  ok(src.includes(' \\u00b7 per person, " + String(last[0]).slice(0, 4) + " population"'), f + ": period line wording");
  ok(src.includes("applyPerCapitaHighlighting();"), f + ": highlighting called");

  /* 2-4. real code, real data */
  const S = dataFor(src);
  if (!S){ ok(false, f + ": data file not found"); continue; }
  const ctx = { console, window: { EA_PC: PC }, PAGE_DATA: { series: S }, TOGGLE_STATE: { real: false, dollar: false, capita: true },
                ISO_GLYPH: {}, EA_group: s => String(s) };
  ctx.window.window = ctx.window;
  vm.createContext(ctx);
  const lab = constLine(src, "COUNTRY_LABEL"), nso = constLine(src, "NATIVE_SYMBOL_OVERRIDE"), iso = constLine(src, "ISO_GLYPH");
  vm.runInContext([lab, nso, iso].filter(Boolean).join("\n") + "\n" +
    ["pcPopulation", "pcSeries", "pcCalendarYears", "currencySymbol", "scaleOf", "curFmt"].map(n => fn(src, n)).join("\n") +
    "\n" + constLine(src, "PC_ANNUAL_RATE") + "\nthis.api = {pcSeries, pcCalendarYears, curFmt, pcPopulation};", ctx);
  const A = ctx.api;
  const pop = A.pcPopulation();
  if (!pop.length){ disabledPages++; ok(f === "taiwan.html", f + ": only Taiwan lacks population"); continue; }
  ok(Array.isArray(pop[0]) && pop[0].length === 2, f + ": population is [period, value] pairs");

  // 3. each eligible key: exact-year division, drop years with no population
  const idx = PC.popIndex(pop);
  for (const k of PC.ELIGIBLE){
    const s = S[k];
    if (!s || !/(m|bn|tn)$/.test(String(s.unit).replace(/\s*\(.*\)\s*$/, ""))) continue;
    const r = A.pcSeries(s);
    const scale = PC.scaleOf(s.unit);
    const bad = r.series.points.filter(([p, v]) => {
      const raw = s.points.find(q => q[0] === p);
      return !raw || Math.abs(raw[1] * scale / idx[String(p).slice(0, 4)] - v) > 1e-6 * Math.abs(v || 1);
    });
    ok(bad.length === 0, `${f} ${k}: every point / its own year's population (${bad.length} bad)`);
    ok(r.series.points.every(([p]) => idx[String(p).slice(0, 4)]), `${f} ${k}: no point from a year without population`);
    ok(/ per person$/.test(r.series.unit), `${f} ${k}: unit says per person`);
  }
  ok(!PC.eligible("cpi") && !PC.eligible("gdp_per_capita") && !PC.eligible("debt_gdp"), "non-currency keys never eligible");

  // 2. GDP tile parity with the page's own GDP per capita tile
  if (S.gdp_level && S.gdp_per_capita && S.gdp_per_capita.points.length){
    let g = S.gdp_level;
    if (S.gdp_level_annual) g = S.gdp_level_annual;          // Poland/Turkey show the trailing sum
    const r = A.pcSeries(g);
    const shown = { ...r.series, pcRolling: /trailing 4-quarter sum/i.test(String(g.label || "")) };
    const cy = A.pcCalendarYears(shown).points;
    const want = S.gdp_per_capita.points[S.gdp_per_capita.points.length - 1];
    const got = cy.find(p => p[0] === String(want[0]));
    ok(got && Math.round(got[1]) === Math.round(want[1]),
      `${f}: GDP tile per person ${got && Math.round(got[1])} = GDP per capita tile ${want[1]} (${want[0]})`);
    if (got) parityPages++;
  }

  // 4. formatting: whole units, page symbol, no "m"
  const unit = (S.gdp_level ? PC.unitLabel(S.gdp_level.unit) : "£ per person");
  const txt = A.curFmt(43815.4, unit, 1, true);
  ok(/43,815$/.test(txt) && !/m$/.test(txt), `${f}: per person format "${txt}"`);
  ok(A.curFmt(-19.2, unit, 1) .startsWith("\u2212"), `${f}: negative per person keeps the minus sign`);
  if (nso && /"A\$"/.test(nso)) ok(A.curFmt(1000, "$ per person", 0) === "A$1,000", `${f}: A$ kept on per person`);
}
ok(disabledPages === 1, "exactly one economy without population (Taiwan), got " + disabledPages);
ok(parityPages === 61, "GDP tile parity on 61 economies, got " + parityPages);

/* 5. Chartmaker: title clear of tick labels */
const cm = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
const cx = { G: { padL: 60 }, czmState: { yTitle: "Pounds sterling per person", yTitlePos: "along", fmtY: v => "\u00a3" + v.toLocaleString("en-GB") },
             AFS: () => 11, estProseWidth: (t, fs) => String(t).length * fs * 0.62,
             czmAxisTickLabel: (v, all, f) => f(v) };
vm.createContext(cx);
vm.runInContext("var CZM_BASE_PADL = 60;\n" + ["czmYLabelWidth", "czmFitLeftPad", "czmYTitleX"].map(n => fn(cm, n)).join("\n") +
  "\nthis.fit = czmFitLeftPad; this.tx = czmYTitleX;", cx);
for (const ticks of [[0, 20000, 40000, 60000], [0, 1, 2, 3, 4], [-40000, 0, 40000, 800000], [0, 5000000, 10000000]]){
  for (const titled of [true, false]){
    cx.czmState.yTitle = titled ? "Pounds sterling per person" : "";
    const gm = cx.fit(() => ({ yTickValues: ticks }));
    const labelLeft = cx.G.padL - 10 - gm.yLabelW;
    const tx = cx.tx(gm);
    if (titled) ok(tx + 7 <= labelLeft, `title (x ${tx}) clear of labels (left ${labelLeft.toFixed(1)}) for ${ticks.join("/")}`);
    ok(labelLeft >= 2, `labels inside the canvas for ${ticks.join("/")}`);
    ok(tx >= 8, "title inside the canvas");
  }
}
cx.czmState.yTitle = "Pounds sterling"; cx.fit(() => ({ yTickValues: [0, 1, 2, 3, 4] }));
ok(cx.G.padL === 60, "short labels keep the 60px margin (no layout change for ordinary charts)");
ok(/function czmBuildSVGSnapshotH\(theme, forExport\)\{\n  G\.padL = CZM_BASE_PADL;/.test(cm), "horizontal bars reset the margin");
ok((cm.match(/var gm = czmFitLeftPad\(/g) || []).length === 2, "line and vertical bar renderers both fit the margin");
ok((cm.match(/var yTitleX = czmYTitleX\(gm\)/g) || []).length === 2, "both renderers place the title clear");
ok(cm.includes("percapita.js?v=4"), "Chartmaker loads percapita.js v4");

console.log(`test_v19122: ${checks} checks, ${failures} failed`);
process.exit(failures ? 1 : 0);
