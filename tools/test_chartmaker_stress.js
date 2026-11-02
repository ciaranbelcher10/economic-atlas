#!/usr/bin/env node
/* ChartMaker stress and export smoke test (v1.9.50, Phase 3).
 *  A. 62 countries on one line chart: renders, no NaN/undefined, sources cited; PNG and CSV exports.
 *  B. The same 62 as a bar chart.
 *  C. Mixed frequencies (monthly, quarterly, annual) on one chart.
 *  D. Every country, one at a time, for the core indicators it has: render, PNG SVG and CSV.
 * CSV checks: quoted labels, one column per live series, a notes block with unit, transform and
 * source for each series. Run: NODE_PATH=/tmp/node_modules node tools/test_chartmaker_stress.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = (c, m) => { checks++; if (!c) fail(m); };
const eq = (a, b, m) => ok(a === b, `${m}: expected ${JSON.stringify(b).slice(0, 120)}, got ${JSON.stringify(a).slice(0, 120)}`);
// SVG comparison that reports the first difference instead of dumping two whole charts
const sameSvg = (a, b, m) => { if(a === b) return ok(true, m); let i = 0; while(i < a.length && a[i] === b[i]) i++;
  ok(false, `${m}: first difference at ${i}: saved "${b.slice(Math.max(0, i - 40), i + 60)}" vs reopened "${a.slice(Math.max(0, i - 40), i + 60)}"`); };
/* ---------------------------- layer 2: jsdom ---------------------------- */
const { JSDOM, VirtualConsole } = require("jsdom");
const bootErrors = [];
const savedPayloads = []; let savedRows = [];
let seedStorage = null;   // v1.9.37: lets a test start a page with a browser draft already present
async function boot(){
  const html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8"), ROOT);
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => {
    const msg = String(e && e.message || e).split("\n")[0];
    if(/supabase|EATLAS_PREFS|Not implemented|\bd3\b|is not defined: undefined/i.test(msg)) return;
    bootErrors.push(msg);
  });
  const chain = result => new Proxy({}, { get: (t, k) => k === "then" ? (f, r) => Promise.resolve(result()).then(f, r) : () => chain(result) });
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/chartmaker.html",
    beforeParse(win){
      if (seedStorage) { try { Object.keys(seedStorage).forEach(k => win.localStorage.setItem(k, seedStorage[k])); } catch (e) {} }
      win.confirm = () => true;
      win.HTMLCanvasElement.prototype.getContext = () => ({ canvas: {}, clearRect(){}, save(){}, restore(){}, beginPath(){}, moveTo(){}, lineTo(){},
        stroke(){}, fill(){}, arc(){}, fillRect(){}, measureText: () => ({ width: 10 }), fillText(){}, setTransform(){}, scale(){}, translate(){}, closePath(){},
        createLinearGradient: () => ({ addColorStop(){} }) });
      function ChartStub(canvas, config){ this.canvas = canvas; this.config = config; this.data = (config && config.data) || { datasets: [] }; this.options = (config && config.options) || {}; }
      ChartStub.prototype.update = function(){}; ChartStub.prototype.destroy = function(){}; ChartStub.prototype.resetZoom = function(){}; ChartStub.register = function(){};
      win.Chart = ChartStub;
      win.fetch = u => {
        const file = String(u).split("/").pop().split("?")[0];
        const p = path.join(ROOT, file);
        if(!fs.existsSync(p)) return Promise.reject(new Error("no such file " + file));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} }));
      // a logged-in person with a backend that remembers what is saved
      win.EATLAS_PREFS = { isLoggedIn: () => true, registerBanner(){}, onLogin(){} };
      win.sb = { auth: { getUser: () => Promise.resolve({ data: { user: { id: "u1" } } }) },
        from: () => ({ insert: p => { savedPayloads.push(p); return Promise.resolve({ error: null }); },
                       select: () => chain(() => ({ data: savedRows, error: null })), delete: () => chain(() => ({})) }) };
    },
  });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  await new Promise(r => setTimeout(r, 900));
  return win;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function page(){
  const win = await boot(), doc = win.document, $ = s => doc.querySelector(s);
  const click = el => el.dispatchEvent(new win.Event("click", { bubbles: true }));
  const rows = () => [...doc.querySelectorAll("#cmSeriesList .cm-seriesitem")];
  async function until(get, what, ms){
    const t0 = Date.now();
    for(;;){ const v = get(); if(v) return v; if(Date.now() - t0 > (ms || 8000)) throw new Error("timed out waiting for " + what); await sleep(40); }
  }
  // v1.9.37: drives the new chooser (tick the country, pick the indicator version, Add)
  const BASE_OF = { "Unemployment rate": "unemployment", "GDP level": "gdp_level", "GDP growth (annual, real)": "gdp_growth", "FDI, % of GDP": "fdi", "Real GDP level": "gdp_real" };
  async function add(country, metric){
    const n = $("#cmStarterNote") && !$("#cmStarterNote").hidden ? 0 : rows().length;
    click($("#cmAddBtn"));
    // v1.9.38: the chooser opens with the chart's countries ticked; pick the version first, then keep
    // only what is already on the chart for it plus the country being added
    const vb = await until(() => [...doc.querySelectorAll("#cmzInds button[data-base]")].filter(b => b.dataset.base === (BASE_OF[metric] || metric))[0], "indicator " + metric);
    click(vb);
    [...doc.querySelectorAll("#cmzCountries label")].forEach(l => {
      const i = l.querySelector("input"), keep = i.dataset.c === country || /On chart/.test(l.textContent);
      if(i.checked !== keep){ i.checked = keep; i.dispatchEvent(new win.Event("change", { bubbles: true })); }
    });
    click($("#cmzAdd"));
    await until(() => rows().length === n + 1, "series " + country + " " + metric + " added");
  }

  const svg = () => $("#cmSvgBox").innerHTML;
  const fire = (el, type) => el.dispatchEvent(new win.Event(type, { bubbles: true }));
  async function openSaved(name){
    click($("#cmOpenBtn")); await sleep(400);
    const r = [...doc.querySelectorAll(".cm-savedrow")].filter(x => x.querySelector(".cm-savedname").textContent === name)[0];
    if(!r) throw new Error("saved chart not listed: " + name);
    click(r.querySelector("button.open")); await sleep(300);
  }
  // choose a whole group and one indicator version in the chooser, then Add
  async function addGroup(group, base){
    click($("#cmAddBtn"));
    const gb = await until(() => [...doc.querySelectorAll("#cmzGroups button")].filter(b => b.textContent.startsWith(group + " ("))[0], "group " + group);
    click(gb);
    const vb = await until(() => [...doc.querySelectorAll("#cmzInds button[data-base]")].filter(b => b.dataset.base === base)[0], "version " + base);
    click(vb);
    const cov = $("#cmzCov").textContent, label = $("#cmzAdd").textContent, groupBtn = gb.textContent, vtext = vb.textContent;
    click($("#cmzAdd")); await sleep(250);
    return { cov, label, groupBtn, vtext };
  }
  return { win, doc, $, click, add, addGroup, svg, fire, until, openSaved };
}

// ---- export capture: Blob parts and object URLs, so the PNG's SVG and the CSV text can be read
function captureExports(win){
  const got = [];
  const B = win.Blob;
  win.Blob = function(parts, opts){ const b = new B(parts, opts); b._text = parts.map(String).join(""); b._type = (opts && opts.type) || ""; return b; };
  win.URL.createObjectURL = b => { got.push(b); return "blob:x" + got.length; };
  win.URL.revokeObjectURL = () => {};
  win.Image = function(){ return {}; };     // the PNG raster step is the browser's; its SVG input is checked here
  return {
    last(type){ for(let i = got.length - 1; i >= 0; i--) if(got[i]._type.indexOf(type) === 0) return got[i]._text; return null; },
    clear(){ got.length = 0; }
  };
}
// RFC 4180 reader, enough to prove the file splits into the columns it claims
function parseCSV(t){
  const rows = []; let row = [], cell = "", q = false;
  for(let i = 0; i < t.length; i++){
    const c = t[i];
    if(q){ if(c === '"'){ if(t[i + 1] === '"'){ cell += '"'; i++; } else q = false; } else cell += c; continue; }
    if(c === '"') q = true; else if(c === ","){ row.push(cell); cell = ""; }
    else if(c === "\n"){ row.push(cell); rows.push(row); row = []; cell = ""; } else cell += c;
  }
  if(cell !== "" || row.length){ row.push(cell); rows.push(row); }
  return rows;
}
const BAD = /NaN|undefined|Infinity|\[object/;
function checkCSV(text, liveLabels, allLabels, tag){
  ok(!!text, tag + ": CSV produced");
  if(!text) return;
  const rows = parseCSV(text), blank = rows.findIndex(r => r.length === 1 && r[0] === "");
  const data = rows.slice(0, blank), notes = rows.slice(blank + 1);
  eq(JSON.stringify(data[0]), JSON.stringify(["period"].concat(liveLabels)), tag + ": header is period plus one quoted label per series");
  ok(data.length > 1, tag + ": has data rows");
  ok(data.every(r => r.length === liveLabels.length + 1), tag + ": every data row has the same number of columns");
  ok(data.slice(1).every(r => r.slice(1).every(v => v === "" || isFinite(+v))), tag + ": every value is a number or empty");
  ok(liveLabels.every((l, j) => data.slice(1).filter(r => r[j + 1] !== "").length >= 2), tag + ": every series column holds values");
  eq(JSON.stringify(notes[0]), JSON.stringify(["Series", "Unit", "Transform", "Source"]), tag + ": notes block header");
  const nr = notes.slice(1, 1 + allLabels.length);
  eq(JSON.stringify(nr.map(r => r[0])), JSON.stringify(allLabels), tag + ": a notes row per series");
  ok(nr.every(r => r.length === 4 && r[2] && r[3] && !/See theeconomicatlas/.test(r[3])), tag + ": every series has a transform and a specific source: " + JSON.stringify(nr.filter(r => !r[3] || /See theeconomicatlas/.test(r[3])).slice(0, 3)));
  ok(nr.every((r, i) => liveLabels.indexOf(r[0]) === -1 || r[1]), tag + ": every series with data has a unit");
  ok(/^Downloaded from The Economic Atlas/.test((notes[1 + allLabels.length] || [""])[0]), tag + ": download line");
  ok(!BAD.test(text) && !/\u2014/.test(text), tag + ": no NaN, undefined or em dash in the file");
}
function checkSVG(svg, tag, wantSource){
  ok(!!svg && /<svg/.test(svg), tag + ": SVG built");
  if(!svg) return;
  ok(!BAD.test(svg), tag + ": no NaN or undefined in the SVG" + (BAD.test(svg) ? " near " + svg.slice(Math.max(0, svg.search(BAD) - 80), svg.search(BAD) + 40) : ""));
  if(wantSource) ok(/>Source: /.test(svg) && !/see theeconomicatlas\.com\/methodology for full data sources/.test(svg), tag + ": cites a specific source");
}
const labels = P => [...P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem")].map(r => r);
async function addMany(P, countries, base){
  P.click(P.$("#cmAddBtn"));
  const vb = await P.until(() => [...P.doc.querySelectorAll("#cmzInds button[data-base]")].find(b => b.dataset.base === base), "indicator " + base);
  P.click(vb);
  [...P.doc.querySelectorAll("#cmzCountries label")].forEach(l => {
    const i = l.querySelector("input"), want = countries.indexOf(i.dataset.c) !== -1;
    if(i.checked !== want){ i.checked = want; i.dispatchEvent(new P.win.Event("change", { bubbles: true })); }
  });
  P.click(P.$("#cmzAdd")); await sleep(150);
}
const removeAll = async P => { for(const b of [...P.doc.querySelectorAll("#cmSeriesList .cm-rm")]) { P.click(b); } await sleep(60); };
async function exportBoth(P, cap){
  cap.clear();
  P.click(P.$("#cmPngBtn")); P.click(P.$("#cmCsvBtn")); await sleep(30);
  return { png: cap.last("image/svg+xml"), csv: cap.last("text/csv") };
}
function seriesInfo(P){
  // label text as the CSV writes it, and whether the row is a "no data" row
  return [...P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem")].map(r => ({
    missing: /No data|not available|no data/i.test(r.textContent),
    label: (r.querySelector("input[type=text]") || {}).value || (r.querySelector(".cm-serieslabel, .lbl") || r).textContent.trim()
  }));
}

(async () => {
  let P = await page(), cap = captureExports(P.win);
  P.click(P.$("#cmAddBtn")); await sleep(200);
  const ALL = [...P.doc.querySelectorAll("#cmzCountries input")].map(i => i.dataset.c);
  P.click(P.$("#cmzClose") || P.$("#cmAddBtn")); await sleep(50);
  eq(ALL.length, 62, "chooser lists all 62 economies");

  // A. 62 on one line chart
  let t0 = Date.now();
  await addMany(P, ALL, "unemployment");
  const tA = Date.now() - t0;
  const nRows = P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length;
  ok(nRows >= 40, `40+ series on one chart (${nRows})`);
  ok(tA < 20000, `62-country add and render finishes in under 20 seconds in jsdom (${tA} ms)`);
  checkSVG(P.svg(), "A line 62", false);   // the source footer is drawn on exports only
  let ex = await exportBoth(P, cap);
  checkSVG(ex.png, "A line 62 PNG", true);
  const csvA = parseCSV(ex.csv || "");
  ok(csvA[0] && csvA[0].length - 1 >= 40, `A: CSV carries 40+ series columns (${csvA[0] && csvA[0].length - 1})`);
  ok(csvA[0] && csvA[0].slice(1).every(l => /, /.test(l)), "A: every label keeps its comma inside one column");
  ok(ex.csv && csvA.slice(0, csvA.findIndex(r => r.length === 1 && r[0] === "")).every(r => r.length === csvA[0].length), "A: no row splits into extra columns");

  // B. the same 62 as bars
  P.click([...P.doc.querySelectorAll("#cmChartTypeSeg button")].find(b => b.dataset.type === "bar")); await sleep(150);
  const bsvg = P.svg();
  checkSVG(bsvg, "B bar 62", false);
  const bars = (bsvg.match(/<rect /g) || []).length;
  ok(bars >= 40, `B: 40+ bars drawn (${bars} rects)`);
  ex = await exportBoth(P, cap);
  checkSVG(ex.png, "B bar 62 PNG", true);
  P.click([...P.doc.querySelectorAll("#cmChartTypeSeg button")].find(b => b.dataset.type === "line")); await sleep(80);

  // C. mixed frequencies
  P = await page(); cap = captureExports(P.win);
  await addMany(P, ["US"], "unemployment");      // monthly
  await addMany(P, ["UK"], "gdp_growth");        // quarterly
  await addMany(P, ["Japan"], "debt_gdp");       // annual
  eq(P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length, 3, "C: three series of different frequencies on one chart");
  checkSVG(P.svg(), "C mixed", false);
  ex = await exportBoth(P, cap);
  checkSVG(ex.png, "C mixed PNG", true);
  const cRows = parseCSV(ex.csv || ""), cData = cRows.slice(1, cRows.findIndex(r => r.length === 1 && r[0] === ""));
  ok(cData.some(r => /^\d{4}-\d{2}$/.test(r[0])) && cData.some(r => /^\d{4}-Q\d$/.test(r[0])) && cData.some(r => /^\d{4}$/.test(r[0])),
     "C: CSV keeps monthly, quarterly and annual periods as published");
  checkCSV(ex.csv, cRows[0].slice(1), cRows[0].slice(1), "C");
  // one value read back against the data file it came from
  const usFile = JSON.parse(require("fs").readFileSync(path.join(ROOT, "data-us.json"), "utf8"));
  const usPts = JSON.stringify(usFile).length ? (function find(o){ if(o && typeof o === "object"){ if(Array.isArray(o.points) && /unemploy/i.test(String(o.label || o.title || o.name || ""))) return o.points;
    for(const k of Object.keys(o)){ const r = find(o[k]); if(r) return r; } } return null; })(usFile) : null;
  const lastUS = usPts && usPts[usPts.length - 1];
  const csvUS = lastUS && cData.find(r => r[0] === String(lastUS[0]));
  ok(lastUS && csvUS && Math.abs(+csvUS[1] - lastUS[1]) < 1e-9, "C: the latest US unemployment value matches data-us.json: " + JSON.stringify([lastUS, csvUS]));
  // a label with a quote mark and a comma, and a series with no data: the label stays one quoted
  // cell, and the no-data series gets a notes row but no data column
  const lbl = P.doc.querySelector("#cmSeriesList .cm-seriesitem input.main-edit");
  lbl.value = 'US "headline", jobs'; P.fire(lbl, "input"); P.fire(lbl, "change"); await sleep(60);
  await addMany(P, ["Vietnam"], "policy_rate");
  ex = await exportBoth(P, cap);
  const qRows = parseCSV(ex.csv || "");
  ok(/"US ""headline"", jobs"/.test(ex.csv || ""), "C: a quote mark in a label is doubled inside a quoted cell");
  ok(qRows[0] && qRows[0][1] === 'US "headline", jobs', "C: that label reads back as one cell: " + JSON.stringify(qRows[0]));
  ok(qRows[0] && qRows[0].length === 4 && !qRows[0].some(l => /Vietnam/.test(l)), "C: the no-data series gets no data column: " + JSON.stringify(qRows[0]));
  ok(qRows.some(r => /Vietnam/.test(r[0] || "") && r[3] === "No data for this country on The Economic Atlas"), "C: the no-data series is named in the notes");

  // D. every country alone, core indicators (STRESS_QUICK=1 skips this sweep, for mutation runs)
  if(process.env.STRESS_QUICK){ console.log(`test_chartmaker_stress (quick): ${checks} checks, ${failures} failures`); process.exit(failures ? 1 : 0); }
  const CORE = ["gdp_growth", "cpi", "unemployment", "policy_rate", "debt_gdp"];
  P = await page(); cap = captureExports(P.win);
  let drawn = 0, missingNoted = 0, fails = [];
  const before = { c: 0, f: 0 };
  for(const c of ALL){
    for(const base of CORE){
      await removeAll(P);
      await addMany(P, [c], base);
      const n = P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length;
      if(!n) continue;            // indicator not offered for this country at all
      const svg = P.svg();
      ex = await exportBoth(P, cap);
      const rows = parseCSV(ex.csv || ""), blank = rows.findIndex(r => r.length === 1 && r[0] === "");
      const live = rows[0] ? rows[0].length - 1 : -1;
      const problems = [];
      if(BAD.test(svg)) problems.push("svg NaN");
      if(!ex.png || BAD.test(ex.png)) problems.push("png svg");
      if(!ex.csv) problems.push("no csv");
      else {
        if(rows.slice(0, blank).some(r => r.length !== rows[0].length)) problems.push("csv columns");
        const note = rows[blank + 2] || [];
        if(note.length !== 4 || !note[3]) problems.push("csv notes");
        if(live === 1 && /See theeconomicatlas/.test(note[3])) problems.push("csv generic source");
        if(live === 1 && !note[1]) problems.push("csv no unit");
        if(live === 1 && !/>Source: /.test(ex.png)) problems.push("png no source");
        if(live === 0) missingNoted += /No data/.test(note[3]) ? 1 : 0;
      }
      if(live === 1) drawn++;
      if(problems.length) fails.push(c + " " + base + ": " + problems.join(", "));
    }
  }
  ok(fails.length === 0, `D: every country renders and exports cleanly (${fails.length} problems): ` + fails.slice(0, 12).join("; "));
  ok(drawn >= 250, `D: country and indicator pairs drawn and exported (${drawn})`);
  console.log(`  D: ${drawn} pairs drawn; ${missingNoted} "no data" rows labelled as such`);
  ok(bootErrors.length === 0, "no page errors: " + bootErrors.slice(0, 3).join(" | "));
  console.log(`test_chartmaker_stress: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("CRASH", e && e.stack || e); process.exit(2); });
