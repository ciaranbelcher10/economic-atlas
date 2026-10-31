#!/usr/bin/env node
/* ChartMaker saved charts reopen exactly as they were saved (v1.9.32).
 * Drives the real page in jsdom: builds a chart, changes the axis, theme, titles, reference line and an
 * annotation's position, saves it, boots a FRESH page, opens the saved chart and requires the drawn SVG to be
 * identical to what was on screen at save time. Also: charts saved before the step was stored, charts saved
 * on Compare (no snapshot) get a sensible axis rather than the coarsest, and a saved period that no longer
 * exists snaps to the nearest rather than leaving a blank selector.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_chartmaker_saved.js
 */
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
  async function add(country, metric){
    click($("#cmAddBtn"));
    const cb = await until(() => [...doc.querySelectorAll("#cmCountryRegions .picker-item")].filter(e => e.textContent.trim() === country)[0], "country " + country);
    click(cb);
    const mc = await until(() => [...doc.querySelectorAll("#cmMetricGrid .pickeritem")].filter(e => { const t = e.querySelector("div"); return t && t.textContent.trim() === metric; })[0], "metric " + metric);
    // v1.9.32: the example chart is replaced by the first metric added
    const n = $("#cmStarterNote") && !$("#cmStarterNote").hidden ? 0 : rows().length;
    click(mc);
    await until(() => rows().length === n + 1, "the new series row");
    await sleep(60);
  }
  const svg = () => $("#cmSvgBox").innerHTML;
  const fire = (el, type) => el.dispatchEvent(new win.Event(type, { bubbles: true }));
  async function openSaved(name){
    click($("#cmOpenBtn")); await sleep(400);
    const r = [...doc.querySelectorAll(".cm-savedrow")].filter(x => x.querySelector(".cm-savedname").textContent === name)[0];
    if(!r) throw new Error("saved chart not listed: " + name);
    click(r.querySelector("button.open")); await sleep(300);
  }
  return { win, doc, $, click, add, svg, fire, until, openSaved };
}

(async () => {
  // 1. build, change everything that shapes the axis and look, save
  let P = await page();
  await P.add("UK", "Unemployment rate");
  await P.add("Germany", "Unemployment rate");
  P.$("#cmChartTitle").value = "Jobless rates"; P.fire(P.$("#cmChartTitle"), "input");
  P.click(P.$("#cmYTickPlus")); P.click(P.$("#cmYTickPlus")); P.click(P.$("#cmYTickPlus"));
  P.click(P.$("#cmXTickMinus"));
  P.click(P.$('#cmThemeSeg button[data-theme="dark"]'));
  P.click(P.$('#cmXAngleSeg button[data-angle="diagonal"]'));
  P.$("#cmRefToggle").checked = true; P.fire(P.$("#cmRefToggle"), "change");
  P.$("#cmRefValue").value = "5"; P.fire(P.$("#cmRefValue"), "input");
  const opts = [...P.$("#cmFromPeriod").options].map(o => o.value);
  P.$("#cmFromPeriod").value = opts[Math.floor(opts.length / 2)]; P.fire(P.$("#cmFromPeriod"), "change");
  P.click(P.$("#cmAddAnnotBtn")); await sleep(80);
  await sleep(150);
  const before = P.svg();
  ok(before.length > 1000 && /Jobless rates/.test(before), "a chart was drawn before saving");
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "jobless"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  eq(savedPayloads.length, 1, "chart saved");
  const st = savedPayloads[0].style;
  eq(st.snapshot.theme, "dark", "theme saved");
  ok(typeof st.snapshot.yTickStep === "number", "tick step value saved");
  ok(typeof st.annotations[0].labelX === "number" && typeof st.annotations[0].labelY === "number", "annotation position saved");

  // the annotation was dragged somewhere else before saving: move it in the payload as a drag would
  st.annotations[0].labelX += 37; st.annotations[0].labelY += 23;
  const wantX = st.annotations[0].labelX, wantY = st.annotations[0].labelY;
  const clone = o => JSON.parse(JSON.stringify(o));      // the page must not be able to edit the stored row
  const row = { id: 1, name: "jobless", country_code: "chartmaker", created_at: "2026-10-30T12:00:00Z", style: clone(st),
                from_period: savedPayloads[0].from_period, to_period: savedPayloads[0].to_period, metric_key: "unemployment" };

  // 2. a fresh page opens it identically
  savedRows = [clone(row)];
  P = await page();
  await P.openSaved("jobless");
  const after = P.svg();
  const strip = h => h.replace(/data-cz-label="0" x="[\d.]+" y="[\d.]+"/, "LABEL").replace(/<tspan x="[\d.]+"/g, "<tspan").replace(/<rect data-cz-label-handle[^>]*>/, "");
  sameSvg(strip(after), strip(before), "reopened chart draws exactly what was saved (apart from the moved label)");
  const lm = after.match(/data-cz-label="0" x="([\d.]+)" y="([\d.]+)"/);
  ok(lm && Math.abs(+lm[1] - wantX) < 0.11 && Math.abs(+lm[2] - wantY) < 0.11, "annotation reopens where it was dragged");
  eq(P.$('#cmThemeSeg button.active').dataset.theme, "dark", "theme control shows the saved theme");
  eq(P.$("#cmFromPeriod").value, row.from_period, "from period restored");

  // 3. new data since saving: the step, not the index, comes back
  const st2 = JSON.parse(JSON.stringify(st)); st2.snapshot.yTickStepIdx = 0;          // a stale index
  savedRows = [Object.assign(clone(row), { id: 2, name: "stale index", style: st2 })];
  P = await page(); await P.openSaved("stale index");
  sameSvg(P.svg(), after, "saved step wins over a stale index");

  // 4. saved before v1.9.32 (index only): still the saved axis
  const st3 = JSON.parse(JSON.stringify(st)); delete st3.snapshot.yTickStep;
  savedRows = [Object.assign(clone(row), { id: 3, name: "older", style: st3 })];
  P = await page(); await P.openSaved("older");
  sameSvg(P.svg(), after, "older save (index only) reopens with its axis");

  // 5. saved on Compare: no snapshot, so the default axis, not the coarsest one
  savedRows = [{ id: 4, name: "from compare", country_code: "compare", created_at: "2026-10-30T12:00:00Z", metric_key: "unemployment",
                 style: { countries: ["UK", "Germany"] } }];
  P = await page(); await P.openSaved("from compare");
  const ticks = (P.svg().match(/<text x="50" y="[\d.]+" font-size="11"[^>]*text-anchor="end">/g) || []).length;
  ok(ticks >= 4, "a chart saved on Compare opens with a readable axis (" + ticks + " y labels)");

  // 6. a saved period that no longer exists snaps to the nearest
  savedRows = [Object.assign(clone(row), { id: 5, name: "gone period", from_period: "1901-01", to_period: "2099-12" })];
  P = await page(); await P.openSaved("gone period");
  const o = [...P.$("#cmFromPeriod").options].map(x => x.value);
  eq(P.$("#cmFromPeriod").value, o[0], "an earlier-than-data start snaps to the first period");
  eq(P.$("#cmToPeriod").value, o[o.length - 1], "a later-than-data end snaps to the last period");

  // 7. parity with Customise & export (v1.9.32): one line has no legend, months read "Dec 1998",
  //    points are r=2.2, and a single series drawn as bars colours below-zero bars indigo
  P = await page();
  await P.add("UK", "Unemployment rate");
  let one = P.svg();
  ok(!/UK, Unemployment rate<\/text>/.test(one), "a single line has no legend");
  ok(/>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}<\/text>/.test(one) && !/>\d{4}-\d{2}<\/text>/.test(one), "monthly x labels read as Customise & export prints them");
  P.$("#cmPointsToggle").checked = true; P.fire(P.$("#cmPointsToggle"), "change"); await sleep(60);
  ok(/<circle [^>]*r="2.2"/.test(P.svg()) && !/<circle [^>]*r="2"[ />]/.test(P.svg()), "points match Customise & export");
  await P.add("Germany", "Unemployment rate");
  ok(/UK, Unemployment rate<\/text>/.test(P.svg()) && /Germany, Unemployment rate<\/text>/.test(P.svg()), "two lines keep their legend");
  P = await page();
  await P.add("UK", "GDP growth (annual, real)");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(120);
  const bars = P.svg().match(/<rect [^>]*rx="3"[^>]*>/g) || [];
  ok(bars.some(b => /fill="#413D7B"/.test(b)) && bars.some(b => !/fill="#413D7B"/.test(b)), "single-series bars colour below-zero bars indigo");

  // 8. example chart and glowing Add metric button (v1.9.32)
  P = await page();
  await P.until(() => P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length === 1, "the example chart");
  ok(P.$("#cmAddBtn").classList.contains("cm-glow"), "Add metric glows while only the example is shown");
  ok(!P.$("#cmStarterNote").hidden, "the example is labelled as an example");
  ok(/^UK, /.test(P.$("#cmSeriesList .main-edit").value) && P.svg().length > 1000, "the example is a drawn UK chart");
  const exFrom = P.$("#cmFromPeriod").value, exOpts = [...P.$("#cmFromPeriod").options].map(o => o.value);
  ok(exFrom > exOpts[0], "the example shows recent years, not the whole history");
  await P.add("Germany", "Unemployment rate");
  const names = [...P.doc.querySelectorAll("#cmSeriesList .main-edit")].map(i => i.value);
  eq(names.join("|"), "Germany, Unemployment rate", "the first metric added replaces the example");
  ok(!P.$("#cmAddBtn").classList.contains("cm-glow") && P.$("#cmStarterNote").hidden, "glow and note go once the person starts");
  eq(P.$("#cmFromPeriod").value, [...P.$("#cmFromPeriod").options][0].value, "their chart starts from the full history, not the example's window");
  savedRows = [clone(row)];
  P = await page();
  await P.until(() => P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length === 1, "the example chart");
  await P.openSaved("jobless");
  ok(!P.$("#cmAddBtn").classList.contains("cm-glow") && P.$("#cmStarterNote").hidden, "opening a saved chart replaces the example");
  eq(P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length, 2, "only the saved chart's series are shown");

  // 9. axis label size and chart font (v1.9.32): drawn, saved, reopened, and kept within limits
  savedPayloads.length = 0;
  P = await page();
  await P.add("UK", "Unemployment rate");
  for(let i = 0; i < 3; i++) P.click(P.$("#cmAxisFsPlus"));
  P.$("#cmFontSelect").value = "georgia"; P.fire(P.$("#cmFontSelect"), "change"); await sleep(60);
  let g = P.svg();
  ok(/font-family="Georgia/.test(g), "the chart is drawn in the chosen font");
  const yl = g.match(/<text x="50" y="[\d.]+" font-size="(\d+)"[^>]*text-anchor="end">/g) || [];
  ok(yl.length >= 3 && yl.every(t => /font-size="14"/.test(t)), "y-axis labels use the chosen size");
  ok(/font-size="14"[^>]*>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}</.test(g), "x-axis labels use the chosen size");
  eq(P.$("#cmAxisFsVal").textContent, "14px", "the size control shows the size");
  for(let i = 0; i < 10; i++) P.click(P.$("#cmAxisFsPlus"));
  eq(P.$("#cmAxisFsVal").textContent, "15px", "size stops at 15px");
  P.click(P.$("#cmAxisFsMinus"));
  const g14 = P.svg();
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "fonts"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  const fp = savedPayloads[0];
  eq(fp && fp.style.snapshot.font, "georgia", "font saved"); eq(fp && fp.style.snapshot.axisFontSize, 14, "size saved");
  savedRows = [{ id: 9, name: "fonts", country_code: "chartmaker", created_at: "2026-10-30T12:00:00Z", style: clone(fp.style), from_period: fp.from_period, to_period: fp.to_period, metric_key: "unemployment" }];
  P = await page(); await P.openSaved("fonts");
  sameSvg(P.svg(), g14, "a chart saved with a font and size reopens identically");
  eq(P.$("#cmFontSelect").value, "georgia", "font control restored");

  // 10. horizontal bars and data labels (v1.9.32)
  savedPayloads.length = 0;
  P = await page();
  await P.add("UK", "Unemployment rate"); await P.add("Germany", "Unemployment rate"); await P.add("France", "Unemployment rate");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(100);
  ok(P.$("#cmBarOptions").style.display !== "none", "bar options appear in Bar mode");
  P.$("#cmDataLabelsToggle").checked = true; P.fire(P.$("#cmDataLabelsToggle"), "change"); await sleep(60);
  let v = P.svg();
  const vdl = v.match(/<text class="cz-dl"[^>]*>[^<]+<\/text>/g) || [];
  eq(vdl.length, 3, "one data label per bar");
  ok(vdl.every(x => /%<\/text>$/.test(x)), "data labels print values as the axis does (%)");
  ok(vdl.every(x => /font-size="11"/.test(x)), "data labels start at 11px");
  P.click(P.$("#cmDlFsPlus")); P.click(P.$("#cmDlFsPlus"));
  ok((P.svg().match(/<text class="cz-dl"[^>]*>/g) || []).every(x => /font-size="13"/.test(x)), "data label size control works");
  P.click(P.$('#cmBarOrientSeg button[data-orient="horizontal"]')); await sleep(60);
  const h = P.svg();
  const hr = (h.match(/<rect [^>]*rx="3"[^>]*>/g) || []).map(r => ({ y: +r.match(/ y="([\d.]+)"/)[1], w: +r.match(/ width="([\d.]+)"/)[1], x: +r.match(/ x="([\d.]+)"/)[1] }));
  eq(hr.length, 3, "three horizontal bars");
  ok(hr.length === 3 && hr[0].y < hr[1].y && hr[1].y < hr[2].y && new Set(hr.map(r => r.x)).size === 1, "bars stack top to bottom from a shared baseline");
  ok(/>UK<\/text>/.test(h) && /text-anchor="end">Germany</.test(h), "country names label each bar on the left");
  ok((h.match(/<text class="cz-dl"[^>]*text-anchor="start"/g) || []).length === 3, "data labels sit past the end of each bar");
  const hlens = hr.slice().sort((a, b) => a.y - b.y).map(r => r.w);
  ok(hlens[0] !== hlens[1] || hlens[1] !== hlens[2], "bar lengths follow the values");
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "hbars"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  const hp = savedPayloads[0];
  savedRows = [{ id: 10, name: "hbars", country_code: "chartmaker", created_at: "2026-10-30T12:00:00Z", style: clone(hp.style), from_period: hp.from_period, to_period: hp.to_period, metric_key: "unemployment" }];
  P = await page(); await P.openSaved("hbars");
  sameSvg(P.svg(), h, "a horizontal bar chart with data labels reopens identically");
  ok(P.$('#cmBarOrientSeg button.active').dataset.orient === "horizontal" && P.$("#cmDataLabelsToggle").checked, "bar controls restored");
  // v1.9.33: the exported image keeps its whole footer, and labels share one number of decimals
  let blob = null;
  P.win.URL.createObjectURL = b => { blob = b; return "blob:x"; };
  P.click(P.$("#cmPngBtn")); await sleep(100);
  const ex = blob ? await new Promise(r => { const fr = new P.win.FileReader(); fr.onload = () => r(fr.result); fr.readAsText(blob); }) : "";
  const H = +((ex.match(/viewBox="0 0 \d+ (\d+)"/) || ex.match(/viewBox='0 0 \d+ (\d+)'/) || [])[1] || 0);
  const srcYs = [...ex.matchAll(/<text x=["']\d+["'] y=["']([\d.]+)["'][^>]*>(Source: [^<]*|[^<]*)<\/text>/g)].filter(m => /Source:|une_rt|FRED|ONS/.test(m[2])).map(m => +m[1]);
  ok(H > 0 && srcYs.length && Math.max(...srcYs) <= H - 4, "the export's source footer fits inside the image (" + Math.max(...srcYs) + " of " + H + ")");
  const decs = [...ex.matchAll(/class=["']cz-dl["'][^>]*>([^<]+)</g)].map(m => (m[1].match(/\.(\d+)/) || ["", ""])[1].length);
  ok(decs.length === 3 && new Set(decs).size === 1, "data labels share one number of decimals");
  // a negative bar's label sits below it (vertical) / to its left (horizontal)
  P = await page();
  await P.add("UK", "GDP growth (annual, real)");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(80);
  P.$("#cmDataLabelsToggle").checked = true; P.fire(P.$("#cmDataLabelsToggle"), "change"); await sleep(60);
  ok(/<text class="cz-dl"[^>]*>(\u2212|-)[\d.]+%</.test(P.svg()), "negative values are labelled with their sign");

  // 11. v1.9.34: high-to-low by default, A-Z chips with group buttons, compare at a chosen period with the
  //     month in full, Mako by rank for 2-10 countries, and saved charts from other pages clearing old titles
  P = await page();
  await P.add("UK", "Unemployment rate");
  click: {
    const chips = [...P.doc.querySelectorAll("#cmNudgeChips .nudgechip")].map(c => c.textContent.replace(/ [+\u2713]$/, ""));
    ok(chips.length > 10 && chips.every((c, i) => i === 0 || chips[i - 1].localeCompare(c) <= 0), "other countries are listed A to Z");
    const groups = [...P.doc.querySelectorAll("#cmNudgeGroups .nudgegroup")].map(b => b.textContent);
    ok(["G7", "G20", "EU", "Euro area", "OECD", "BRICS"].every(g => groups.some(t => t.startsWith("Add " + g + " ("))), "group buttons for G7, G20, EU, euro area, OECD and BRICS: " + groups.join(" | "));
    P.click([...P.doc.querySelectorAll("#cmNudgeGroups .nudgegroup")].filter(b => b.textContent.startsWith("Add G7"))[0]);
    await sleep(200);
  }
  const g7 = [...P.doc.querySelectorAll("#cmSeriesList .main-edit")].map(i => i.value.split(",")[0]).sort();
  eq(g7.join(","), "Canada,France,Germany,Italy,Japan,UK,US", "Add G7 puts exactly the G7 on the chart");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(120);
  eq(P.$("#cmSortModeSelect").value, "value_desc", "bars are ordered high to low by default");
  const vals = [...P.svg().matchAll(/<rect [^>]*height="([\d.]+)"[^>]*rx="3"/g)].map(m => +m[1]);
  ok(vals.length === 7 && vals.every((v, i) => i === 0 || vals[i - 1] >= v - 0.01), "tallest bar first");
  ok(/>(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}</.test(P.svg()), "the period under the bars names the month in full");
  const fills = [...P.svg().matchAll(/<rect [^>]*rx="3" fill="(#[0-9A-Fa-f]{6})"/g)].map(m => m[1].toUpperCase());
  eq(fills[0], "#2E1E3B", "with 2 to 10 countries the highest bar takes the darkest Mako colour");
  eq(new Set(fills).size, 7, "each bar has its own shade");
  ok(P.$("#cmSnapshotAtRow").style.display !== "none", "Compare at is offered for bars");
  const atOpts = [...P.$("#cmSnapshotAt").options].map(o => o.value).filter(Boolean);
  const pick = atOpts[12];
  P.$("#cmSnapshotAt").value = pick; P.fire(P.$("#cmSnapshotAt"), "change"); await sleep(80);
  const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const want = /-\d{2}$/.test(pick) ? months[+pick.slice(5) - 1] + " " + pick.slice(0, 4) : pick;
  ok(P.svg().includes(">" + want + "<"), "the bars say which period they compare: " + want);
  ok(P.svg() !== "" && !P.svg().includes(">" + P.$("#cmSnapshotAt").options[0].textContent.replace(/^Latest in range \(|\)$/g, "") + "<"), "the old period label is gone");
  // eleven or more countries: each country's own colour
  await P.add("Spain", "Unemployment rate"); await P.add("Sweden", "Unemployment rate");
  await P.add("Poland", "Unemployment rate"); await P.add("Austria", "Unemployment rate");
  const fills11 = [...P.svg().matchAll(/<rect [^>]*rx="3" fill="(#[0-9A-Fa-f]{6})"/g)].map(m => m[1].toUpperCase());
  ok(fills11.length === 11 && fills11.indexOf("#1E4566") !== -1, "over 10 countries, each keeps its own colour (UK navy present)");
  // a chart saved on Compare opens without the previous chart's titles
  P.$("#cmChartTitle").value = "Old title"; P.fire(P.$("#cmChartTitle"), "input");
  savedRows = [{ id: 11, name: "cmp", country_code: "compare", created_at: "2026-10-30T12:00:00Z", metric_key: "unemployment", style: { countries: ["UK", "Germany"] } }];
  await P.openSaved("cmp");
  eq(P.$("#cmChartTitle").value, "", "opening a Compare chart clears the old chart title");
  ok(!/Old title/.test(P.svg()), "and the old title is not drawn");

  if(bootErrors.length) fail("page errors: " + bootErrors.slice(0, 3).join(" | "));
  console.log(`test_chartmaker_saved: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  " + e.message); process.exit(1); });
