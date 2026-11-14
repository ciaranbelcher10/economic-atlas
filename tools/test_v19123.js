#!/usr/bin/env node
/* v1.9.123: Per capita on the indicator pages.
 *
 * Runs the REAL indicator-kit.js (initIndicator, in jsdom) and the REAL percapita.js on the REAL
 * data files, with each page's config built the way generate_indicator_pages.py builds it
 * (clean points, GDP annualised, US/Japan raw, population as [period, value] pairs).
 *  1. GDP and real GDP pages, Per capita on: the headline is the latest complete calendar year,
 *     and on GDP it equals the economy's GDP per capita series (same figure as the country page).
 *  2. Every other eligible metric: the headline is the latest period that has a population,
 *     divided by that year's population only; the note names dropped years.
 *  3. Per person formatting: whole units, the page's own symbol (A$ on Australia), axis "k".
 *  4. Generator: the button only where the unit is currency and population exists; percapita.js
 *     loaded before the page boots; KIT_VERSION bumped; PC_ELIGIBLE equals percapita.js ELIGIBLE.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19123.js
 */
const fs = require("fs"), path = require("path");
const { JSDOM } = require("jsdom");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };

const KIT = fs.readFileSync(path.join(ROOT, "indicator-kit.js"), "utf8");
const PCJS = fs.readFileSync(path.join(ROOT, "percapita.js"), "utf8");
const GEN = fs.readFileSync(path.join(ROOT, "generate_indicator_pages.py"), "utf8");
const PC = require(path.join(ROOT, "percapita.js"));

/* 4. generator */
const genElig = (/^PC_ELIGIBLE = \{([^}]*)\}/m.exec(GEN) || [, ""])[1].match(/"([a-z_]+)"/g).map(s => s.slice(1, -1)).sort();
ok(JSON.stringify(genElig) === JSON.stringify(PC.ELIGIBLE.slice().sort()), "generator PC_ELIGIBLE = percapita.js ELIGIBLE");
ok(/^KIT_VERSION = "13"$/m.test(GEN), "KIT_VERSION bumped to 13 (indicator-kit.js changed, v1.9.128)");
ok(/^PERCAPITA_VERSION = "5"$/m.test(GEN), "indicator pages load percapita.js v5 (v1.9.128)");
ok(/boot = f'<script src="\.\.\/percapita\.js\?v=\{PERCAPITA_VERSION\}"><\/script>\\n' \+ boot/.test(GEN), "percapita.js before the boot script");
ok(/if key in PC_ELIGIBLE and re\.search\(r"\(tn\|bn\|m\|k\)\$"/.test(GEN), "button only for currency units");
const GDP_RAW = (/^GDP_RAW_COUNTRIES = \{([^}]*)\}/m.exec(GEN) || [, ""])[1].match(/"([^"]+)"/g).map(s => s.slice(1, -1));
ok(GDP_RAW.join() === "US,Japan", "GDP_RAW_COUNTRIES read from the generator");

/* data files: the generator's own country table, "Name": ("iso2", "slug", ...) */
const econ = [];
for (const m of GEN.matchAll(/^    "([^"]+)":\s*\("([a-z]{2,3})", "[a-z-]+", "[A-Z]{2}",/gm)){
  const f = "data-" + m[2] + ".json";
  if (!fs.existsSync(path.join(ROOT, f))) continue;
  const d = JSON.parse(fs.readFileSync(path.join(ROOT, f), "utf8"));
  if (d.series && d.series.gdp_level) econ.push({ f, d, S: d.series, country: m[1] });
}
ok(econ.length >= 60, "economies with data files: " + econ.length);

function page(cfg){
  const dom = new JSDOM(`<!doctype html><body>
    <div id="indFigure"></div><span id="indPeriod"></span><span id="indDelta"></span><span id="indRange"></span>
    <span id="indLed"></span><div id="indActions"></div><canvas id="indChart"></canvas>
    <button id="indTogglePc"></button><p id="indPcNote" hidden></p></body>`, { runScripts: "outside-only" });
  const w = dom.window;
  w.fetch = () => Promise.reject(new Error("offline"));
  w.matchMedia = () => ({ matches: false });
  w.eval(PCJS); w.eval(KIT);
  w.EATLAS_IND.initIndicator(cfg);
  return w;
}
const clean = s => (s.points || []).filter(p => p && p[1] != null);
let gdpParity = 0, otherPages = 0, auChecked = false;
for (const e of econ){
  const pop = (e.S.population && e.S.population.points || []).filter(p => p[1]).map(p => [String(p[0]), p[1]]);
  if (!pop.length) continue;
  const country = e.country;
  for (const key of PC.ELIGIBLE){
    const s = e.S[key];
    if (!s || !/(tn|bn|m|k)$/.test(String(s.unit || "").replace(/\s*\(.*\)\s*$/, ""))) continue;
    const ann = key === "gdp_level" || key === "gdp_real", raw = GDP_RAW.includes(country);
    // build the config as the generator does
    const tmp = new JSDOM("", { runScripts: "outside-only" }).window; tmp.eval(KIT);
    let pts = clean(s);
    if (ann) pts = tmp.EATLAS_FMT.annualise(pts, s.freq, raw);
    if (pts.length < 2) continue;
    const w = page({ key, country, unit: s.unit, freq: s.freq, upIsGood: true, chart: "line", annualise: ann, gdpRaw: raw,
                     dataUrl: "x", points: pts, realPoints: null, fx: null, population: pop, title: country + " " + key });
    const before = w.document.getElementById("indFigure").textContent;
    w.document.getElementById("indTogglePc").click();
    const fig = w.document.getElementById("indFigure").textContent, per = w.document.getElementById("indPeriod").textContent;
    const note = w.document.getElementById("indPcNote");
    ok(fig !== before && /\d/.test(fig) && !/(tn|bn|m)$/.test(fig), `${country} ${key}: per person headline "${fig}"`);
    ok(!note.hidden && /^Per capita: each value divided by that year/.test(note.textContent), `${country} ${key}: note shown`);
    const num = +fig.replace(/[^\d.]/g, "") * (/^\u2212/.test(fig) ? -1 : 1);
    if (ann){
      ok(/^\d{4}$/.test(per), `${country} ${key}: GDP per capita is a calendar year (${per})`);
      if (key === "gdp_level" && e.S.gdp_per_capita){
        const g = e.S.gdp_per_capita.points.find(p => String(p[0]) === per);
        ok(g && Math.round(g[1]) === num, `${country} GDP page ${fig} = GDP per capita ${g && g[1]} (${per})`);
        if (g) gdpParity++;
      }
    } else {
      // latest period with a population, divided by that year's population only
      const idx = PC.popIndex(pop), scale = PC.scaleOf(s.unit);
      const last = clean(s).filter(p => idx[String(p[0]).slice(0, 4)]).pop();
      const want = Math.round(Math.abs(last[1] * scale / idx[String(last[0]).slice(0, 4)]));
      ok(Math.abs(num) === want, `${country} ${key}: ${fig} = ${want} (${last[0]})`);
      otherPages++;
    }
    if (country === "Australia" && key === "gdp_level"){ ok(/^A\$/.test(fig), "Australia keeps A$ per person: " + fig); auChecked = true; }
    // turning it off restores the original figure
    w.document.getElementById("indTogglePc").click();
    ok(w.document.getElementById("indFigure").textContent === before && w.document.getElementById("indPcNote").hidden, `${country} ${key}: off restores`);
  }
}
/* a part year never becomes a calendar year, even when its population exists (synthetic, both GDP shapes) */
for (const raw of [true, false]){
  const q = ["2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2","2025-Q3","2025-Q4","2026-Q1","2026-Q2","2026-Q3"];
  const pts = q.map((p, i) => [p, 1000 + i]);   // $bn
  const w = page({ key: "gdp_level", country: raw ? "US" : "Testland", unit: "$bn", freq: "quarters", upIsGood: true, chart: "line",
                   annualise: true, gdpRaw: raw, dataUrl: "x", points: pts, realPoints: null, fx: null,
                   population: [["2024", 1e6], ["2025", 1e6], ["2026", 1e6]], title: "t" });
  w.document.getElementById("indTogglePc").click();
  const per = w.document.getElementById("indPeriod").textContent, fig = w.document.getElementById("indFigure").textContent;
  ok(per === "2025", `${raw ? "annual-rate" : "trailing-sum"} GDP: latest complete year 2025, not the part year 2026 (got ${per})`);
  const want = raw ? (1004 + 1005 + 1006 + 1007) / 4 * 1e9 / 1e6 : 1007 * 1e9 / 1e6;
  ok(fig === "$" + Math.round(want).toLocaleString("en-GB"), `${raw ? "mean" : "Q4 trailing sum"} of 2025 per person: ${fig}`);
}
ok(gdpParity >= 60, "GDP page parity on " + gdpParity + " economies");
ok(otherPages >= 90, "other per capita pages checked: " + otherPages);
ok(auChecked, "Australia checked");

/* 3. formatter */
const fw = new JSDOM("", { runScripts: "outside-only" }).window; fw.eval(KIT);
const F = fw.EATLAS_FMT;
ok(F.unitKind("£ per person") === "pp" && F.unitKind("$ per £1") === "fx", "per person is not mistaken for an FX unit");
ok(F.fmtNum(43815.4, { unit: "£ per person", mode: "value" }) === "£43,815", "value £43,815");
ok(F.fmtNum(-19.4, { unit: "£ per person", mode: "value" }) === "\u2212£19", "negative keeps the minus");
ok(F.fmtNum(5402077, { unit: "¥ per person", mode: "axis" }) === "¥5402k", "axis shortens large values");
ok(F.fmtNum(103412, { unit: "$ per person", key: "gdp_level", country: "Australia" }) === "A$103,412", "A$ on Australia GDP");
ok(F.fmtNum(103412, { unit: "$ per person", key: "gdp_level", country: "Australia", dollarised: true }) === "$103,412", "US$ once converted");

console.log(`test_v19123: ${checks} checks, ${failures} failed`);
process.exit(failures ? 1 : 0);
