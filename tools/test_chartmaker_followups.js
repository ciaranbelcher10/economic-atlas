#!/usr/bin/env node
/* ChartMaker follow-ups (v1.9.40): single-line above/below colouring, per-event label options, and every
 * Style control matching a reopened, other-page or reset chart. Run: NODE_PATH=/tmp/node_modules node tools/test_chartmaker_followups.js */
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
  const html = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
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

const clone = o => JSON.parse(JSON.stringify(o));
const setChk = (P, id, v) => { const e = P.$(id); e.checked = v; P.fire(e, "change"); };
(async () => {
  /* 1. single line coloured above/below the reference line */
  let P = await page();
  await P.add("UK", "Unemployment rate");
  setChk(P, "#cmRefToggle", true);
  P.$("#cmRefValue").value = "5"; P.fire(P.$("#cmRefValue"), "input"); await sleep(80);
  ok(P.$("#cmThresholdShadeRow").style.display !== "none", "single line: above/below option offered once a reference line is on");
  ok(/line/.test(P.$("#cmThresholdShadeLabel").textContent) && !/bars/.test(P.$("#cmThresholdShadeLabel").textContent), "single line: option worded for a line");
  ok(!/clip-path=["']url\(#cmxSplit/.test(P.svg()), "single line: not split until asked");
  setChk(P, "#cmThresholdShadeToggle", true); await sleep(80);
  let s1 = P.svg();
  ok(/clip-path=["']url\(#cmxSplitSa\)["']/.test(s1) && /clip-path=["']url\(#cmxSplitSb\)["']/.test(s1), "single line: drawn in two clipped halves");
  ok(/stroke=["']#348FA7["'][^>]*clip-path/.test(s1) && /stroke=["']#413D7B["'][^>]*clip-path/.test(s1), "single line: above and below colours used");
  // the split sits on the reference line's own row
  const refRow = (s1.match(/<line[^>]*stroke-dasharray=["']4,3["'][^>]*>/g) || []).map(l => +l.match(/y1=["']([\d.]+)["']/)[1])[0];
  const clipB = s1.match(/<clipPath id=["']cmxSplitSb["']><rect x=["']0["'] y=["']([\d.]+)["']/);
  ok(clipB && refRow != null && Math.abs(+clipB[1] - refRow) < 0.6, "single line: split at the reference line (" + (clipB && clipB[1]) + " vs " + refRow + ")");
  // with Fill on, the shading runs between the line and the reference line, not down to the axis
  setChk(P, "#cmFillToggle", true); await sleep(80);
  const areas = (P.svg().match(/<path d=["'][^"']*Z["'][^>]*clip-path[^>]*>/g) || []);
  ok(areas.length === 2 && clipB && areas.every(a => new RegExp(",(" + (+clipB[1]).toFixed(1) + ") L[\\d.]+," + (+clipB[1]).toFixed(1) + " Z").test(a)), "single line: fill closes on the reference line");
  setChk(P, "#cmFillToggle", false);
  // points follow the value, not the clip
  setChk(P, "#cmPointsToggle", true); await sleep(80);
  const circ = (P.svg().match(/<circle [^>]*r=["']2.2["'][^>]*>/g) || []);
  ok(circ.length > 5 && circ.some(c => /#348FA7/.test(c)) && circ.some(c => /#413D7B/.test(c)), "single line: points coloured by side");
  // a second line hides the option and turns it off
  await P.add("Germany", "Unemployment rate"); await sleep(80);
  ok(P.$("#cmThresholdShadeRow").style.display === "none", "two lines: option hidden");
  eq(P.$("#cmThresholdShadeToggle").checked, false, "two lines: option switched off");
  ok(!/cmxSplit/.test(P.svg()), "two lines: no split drawn");
  // bars keep their own wording
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(80);
  setChk(P, "#cmRefToggle", true); await sleep(50);
  ok(/bars/.test(P.$("#cmThresholdShadeLabel").textContent), "bars: option keeps its bar wording");

  /* 2. per-event options */
  P = await page();
  await P.add("UK", "Unemployment rate");
  P.click(P.$("#cmAddAnnotBtn")); await sleep(80);
  const lbls = [...P.doc.querySelectorAll("#cmAnnotList .cmx-evlbl")].map(l => l.textContent);
  ["Date", "Shape", "Label position and size", "Label"].forEach(t => ok(lbls.includes(t), "event card labelled: " + t));
  const fsBtns = () => P.doc.querySelectorAll("#cmAnnotList .cmx-evfs button");
  const fsTxt = () => P.doc.querySelector("#cmAnnotList .cmx-evfs span").textContent;
  eq(fsTxt(), "11", "event label starts at 11");
  P.click(fsBtns()[1]); P.click(fsBtns()[1]); await sleep(50);
  eq(fsTxt(), "13", "event label size goes up");
  ok(/<text data-cz-label=["']0["'][^>]*font-size=["']13["']/.test(P.svg()), "event label drawn at the chosen size");
  for(let i = 0; i < 20; i++) P.click(fsBtns()[0]);
  eq(fsTxt(), "9", "event label size floors at 9"); eq(fsBtns()[0].disabled, true, "smaller disabled at 9");
  for(let i = 0; i < 20; i++) P.click(fsBtns()[1]);
  eq(fsTxt(), "20", "event label size caps at 20"); eq(fsBtns()[1].disabled, true, "larger disabled at 20");
  // a second event keeps its own size
  P.click(P.$("#cmAddAnnotBtn")); await sleep(80);
  const spans = [...P.doc.querySelectorAll("#cmAnnotList .cmx-evfs span")].map(s => s.textContent);
  eq(spans.join(","), "20,11", "each event has its own size");
  P.click(P.doc.querySelectorAll("#cmAnnotList .cmx-evfs")[1].querySelectorAll("button")[1]); await sleep(50);
  eq([...P.doc.querySelectorAll("#cmAnnotList .cmx-evfs span")].map(s => s.textContent).join(","), "20,12", "changing one event leaves the other alone");

  /* 3. every Style control reflects a reopened chart */
  P = await page();
  await P.add("UK", "Unemployment rate");
  P.$("#cmChartTitle").value = "Saved look"; P.fire(P.$("#cmChartTitle"), "input");
  P.$("#cmYAxisTitle").value = "Per cent"; P.fire(P.$("#cmYAxisTitle"), "input");
  P.click(P.$('#cmYTitlePosSeg button[data-pos="above"]'));
  setChk(P, "#cmFillToggle", true); setChk(P, "#cmPointsToggle", true);
  setChk(P, "#cmRefToggle", true); P.$("#cmRefValue").value = "4.5"; P.fire(P.$("#cmRefValue"), "input");
  setChk(P, "#cmThresholdShadeToggle", true);
  P.click(P.$("#cmXTickMinus")); P.click(P.$("#cmXTickMinus"));
  P.click(P.$('#cmXAngleSeg button[data-angle="diagonal"]'));
  P.click(P.$('#cmThemeSeg button[data-theme="dark"]'));
  P.click(P.$("#cmAxisFsPlus"));
  P.$("#cmFontSelect").value = "georgia"; P.fire(P.$("#cmFontSelect"), "change");
  P.click(P.$("#cmAddAnnotBtn")); await sleep(60);
  P.click(P.doc.querySelector("#cmAnnotList .cmx-evfs").querySelectorAll("button")[1]);
  await sleep(120);
  const shown = P.svg();
  savedPayloads.length = 0;
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "look"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  eq(savedPayloads.length, 1, "look chart saved");
  const sp = savedPayloads[0];
  eq(sp.style.snapshot.thresholdShadeBars, true, "line split saved");
  eq(sp.style.annotations[0].fontSize, 12, "event size saved");
  const row = { id: 21, name: "look", country_code: "chartmaker", created_at: "2026-11-01T12:00:00Z", style: clone(sp.style), from_period: sp.from_period, to_period: sp.to_period, metric_key: "unemployment" };

  // a fresh page with a DIFFERENT chart already on it, so stale controls would show
  P = await page();
  await P.add("Germany", "Unemployment rate");
  savedRows = [clone(row)];
  await P.openSaved("look"); await sleep(200);
  sameSvg(P.svg(), shown, "reopened line split chart draws exactly as saved");
  eq(P.$("#cmChartTitle").value, "Saved look", "control: chart title");
  eq(P.$("#cmYAxisTitle").value, "Per cent", "control: y-axis title");
  ok(P.$('#cmYTitlePosSeg button[data-pos="above"]').classList.contains("active"), "control: y title position");
  eq(P.$("#cmFillToggle").checked, true, "control: fill");
  eq(P.$("#cmPointsToggle").checked, true, "control: points");
  eq(P.$("#cmRefToggle").checked, true, "control: reference line");
  eq(P.$("#cmRefValue").value, "4.5", "control: reference value");
  eq(P.$("#cmThresholdShadeToggle").checked, true, "control: above/below colouring");
  ok(P.$("#cmThresholdShadeRow").style.display !== "none", "control: above/below row visible");
  eq(P.$("#cmXTickVal").textContent, "6", "control: x ticks");
  ok(P.$('#cmXAngleSeg button[data-angle="diagonal"]').classList.contains("active"), "control: x label angle");
  ok(P.$('#cmThemeSeg button[data-theme="dark"]').classList.contains("active"), "control: theme");
  eq(P.$("#cmAxisFsVal").textContent, "12px", "control: axis text size");
  eq(P.$("#cmFontSelect").value, "georgia", "control: font");
  eq(P.doc.querySelector("#cmAnnotList .cmx-evfs span").textContent, "12", "control: event size");

  // a bar chart's sort and bar options come back too
  P = await page();
  await P.add("UK", "Unemployment rate"); await P.add("Germany", "Unemployment rate");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(60);
  P.$("#cmSortModeSelect").value = "alphabetical"; P.fire(P.$("#cmSortModeSelect"), "change");
  P.click(P.$('#cmBarOrientSeg button[data-orient="horizontal"]'));
  setChk(P, "#cmDataLabelsToggle", true); await sleep(80);
  savedPayloads.length = 0;
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "bars"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  const bp = savedPayloads[0];
  P = await page();
  await P.add("France", "Unemployment rate");
  savedRows = [{ id: 22, name: "bars", country_code: "chartmaker", created_at: "2026-11-01T12:00:00Z", style: clone(bp.style), from_period: bp.from_period, to_period: bp.to_period, metric_key: "unemployment" }];
  await P.openSaved("bars"); await sleep(200);
  eq(P.$("#cmSortModeSelect").value, "alphabetical", "control: sort order");
  ok(P.$('#cmBarOrientSeg button[data-orient="horizontal"]').classList.contains("active"), "control: bar direction");
  eq(P.$("#cmDataLabelsToggle").checked, true, "control: data labels");

  // a chart saved elsewhere (no ChartMaker settings) opens with every control at its default
  P = await page();
  await P.add("UK", "Unemployment rate");
  setChk(P, "#cmFillToggle", true); setChk(P, "#cmPointsToggle", true);
  P.click(P.$('#cmYTitlePosSeg button[data-pos="above"]'));
  P.click(P.$("#cmXTickMinus")); P.click(P.$('#cmXAngleSeg button[data-angle="diagonal"]'));
  P.click(P.$('#cmThemeSeg button[data-theme="dark"]'));
  setChk(P, "#cmRefToggle", true); await sleep(60);
  savedRows = [{ id: 23, name: "cmp", country_code: "compare", created_at: "2026-11-01T12:00:00Z", metric_key: "unemployment", style: { countries: ["UK", "Germany"] } }];
  await P.openSaved("cmp"); await sleep(200);
  eq(P.$("#cmFillToggle").checked, false, "default: fill off");
  eq(P.$("#cmPointsToggle").checked, false, "default: points off");
  ok(P.$('#cmYTitlePosSeg button[data-pos="along"]').classList.contains("active"), "default: y title alongside");
  eq(P.$("#cmXTickVal").textContent, "8", "default: x ticks");
  ok(P.$('#cmXAngleSeg button[data-angle="straight"]').classList.contains("active"), "default: x label angle");
  ok(P.$('#cmThemeSeg button[data-theme="light"]').classList.contains("active"), "default: theme");
  eq(P.$("#cmRefToggle").checked, false, "default: reference line off");
  ok(!/fill-opacity=["']0.12["']/.test(P.svg()), "default: no fill drawn (fill used to carry over)");

  // the saved reference line is copied, not shared: editing the reopened chart leaves the saved row alone
  P = await page();
  savedRows = [clone(row)];
  await P.openSaved("look"); await sleep(150);
  const before = JSON.stringify(savedRows[0].style.snapshot.refLine);
  P.$("#cmRefValue").value = "9"; P.fire(P.$("#cmRefValue"), "input"); await sleep(50);
  eq(JSON.stringify(savedRows[0].style.snapshot.refLine), before, "editing a reopened chart does not change the saved copy");

  // Reset clears every setting
  P.click(P.$("#cmResetBtn")); await sleep(300);
  eq(P.$("#cmFillToggle").checked, false, "reset: fill off");
  eq(P.$("#cmThresholdShadeToggle").checked, false, "reset: above/below off");
  eq(P.$("#cmChartTitle").value, "", "reset: title cleared");
  eq(P.$("#cmFontSelect").value, "helvetica", "reset: font");

  ok(bootErrors.length === 0, "no page errors: " + bootErrors.slice(0, 3).join(" | "));
  console.log(`test_chartmaker_followups: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("CRASH " + (e && e.stack || e)); process.exit(2); });
