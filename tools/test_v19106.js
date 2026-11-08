#!/usr/bin/env node
/* v1.9.106 Chartmaker editor: Clear all metrics; a reopened bar chart's period-named legend title and
 * chart title follow a new period; "X-axis labels" wording on a horizontal bar; "Hide countries with no
 * data"; "Year only" date labels on line and time-bar charts; no negative zero on the value axis.
 * Drives the real page in jsdom (harness copied from test_chartmaker_saved.js).
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19106.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = (c, m) => { checks++; if (!c) fail(m); };
const eq = (a, b, m) => ok(a === b, `${m}: expected ${JSON.stringify(b).slice(0, 120)}, got ${JSON.stringify(a).slice(0, 120)}`);
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

(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const clone = o => JSON.parse(JSON.stringify(o));
  // 1. Clear all
  let P = await page();
  await P.add("Germany", "Unemployment rate"); await P.add("France", "Unemployment rate");
  const ca = P.$("#cmClearAll");
  ok(ca && !ca.hidden, "Clear all shows with two or more metrics");
  P.click(ca); await sleep(150);
  eq(P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length, 0, "Clear all empties the chart");
  ok(/No metrics added yet/.test(P.$("#cmStatus").textContent) && P.$("#cmClearAll").hidden, "status reset, Clear all hidden");

  // 2. a bar chart saved with an automatic period legend and a title naming it
  await P.add("Germany", "Unemployment rate"); await P.add("France", "Unemployment rate");
  P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(80);
  const toSel = P.$("#cmToPeriod");
  const opts = [...toSel.options].map(o => o.value);
  const last = opts[opts.length - 1], prev = opts[opts.length - 2];
  toSel.value = prev; P.fire(toSel, "change"); await sleep(80);
  const prevText = P.$("#cmLegendTitle").value;
  ok(prevText && prevText !== "", "legend shows the period: " + prevText);
  P.$("#cmChartTitle").value = "Unemployment, " + prevText; P.fire(P.$("#cmChartTitle"), "input");
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "eu jobless"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  const st = clone(savedPayloads[savedPayloads.length - 1].style);
  eq(st.snapshot.legendTitleTouched, false, "save records the legend title as automatic");
  delete st.snapshot.legendTitleTouched;   // as a chart saved before v1.9.106
  const row = { id: 9, name: "eu jobless", country_code: "chartmaker", created_at: "2026-11-01T12:00:00Z", style: st,
                from_period: savedPayloads[savedPayloads.length - 1].from_period, to_period: prev, metric_key: "unemployment" };
  savedRows = [clone(row)];
  P = await page(); await P.openSaved("eu jobless"); await sleep(200);
  eq(P.$("#cmLegendTitle").value, prevText, "reopened legend title");
  const toSel2 = P.doc.getElementById(toSel.id);
  toSel2.value = last; P.fire(toSel2, "change"); await sleep(120);
  const lastText = P.$("#cmLegendTitle").value;
  ok(lastText !== prevText && lastText !== "", "legend follows the new period: " + lastText);
  eq(P.$("#cmChartTitle").value, "Unemployment, " + lastText, "chart title follows the new period");
  ok(P.svg().indexOf(lastText) !== -1 && P.svg().indexOf(prevText) === -1, "drawn chart shows only the new period");
  // a typed legend title stays put
  P.$("#cmLegendTitle").value = "My own"; P.fire(P.$("#cmLegendTitle"), "input");
  toSel2.value = prev; P.fire(toSel2, "change"); await sleep(80);
  eq(P.$("#cmLegendTitle").value, "My own", "a typed legend title is kept");

  // 3. horizontal bar: the value-axis tick control says X-axis labels
  P.click(P.$('#cmBarOrientSeg button[data-orient="horizontal"]')); await sleep(60);
  eq(P.$("#cmYTickLbl").textContent, "X-axis labels", "horizontal bar: X-axis labels");
  P.click(P.$('#cmBarOrientSeg button[data-orient="vertical"]')); await sleep(60);
  eq(P.$("#cmYTickLbl").textContent, "Y-axis labels", "vertical bar: Y-axis labels");
  ok(P.$("#cmXDateGroup").style.display === "none", "date labels control hidden on a country bar chart");

  // 4. hide no data: a group brings in members without the figure
  P.click(P.$("#cmClearAll")); await sleep(100);
  const g = await P.addGroup("G20", "fdi"); await sleep(200);
  const before = (P.svg().match(/No data/g) || []).length;
  const row2 = P.$("#cmHideNoDataRow");
  if(before > 0){
    ok(row2.style.display !== "none", "Hide countries with no data offered when a bar says No data");
    const cb = P.$("#cmHideNoData"); cb.checked = true; P.fire(cb, "change"); await sleep(120);
    eq((P.svg().match(/>No data</g) || []).length, 0, "No data bars hidden");
    cb.checked = false; P.fire(cb, "change"); await sleep(120);
    ok((P.svg().match(/>No data</g) || []).length > 0, "and shown again");
  } else ok(false, "test setup: expected G20 FDI to include a country without data");

  // 5. year-only date labels on a single-series line
  P.click(P.$("#cmClearAll")); await sleep(80);
  await P.add("Germany", "Unemployment rate");
  P.click(P.$('#cmChartTypeSeg button[data-type="line"]')); await sleep(80);
  const fromSel = P.$("#cmFromPeriod");
  fromSel.value = [...fromSel.options].map(o => o.value).find(v => /^2010-0[1-9]$|^2010-Q/.test(v)) || fromSel.options[0].value; P.fire(fromSel, "change"); await sleep(80);
  ok(P.$("#cmXDateGroup").style.display !== "none", "date labels control shown on a time chart");
  P.click(P.$('#cmXDateSeg button[data-fmt="year"]')); await sleep(120);
  const labels = [...P.$("#cmSvgBox").querySelectorAll("text")].map(t => t.textContent).filter(t => /^(19|20)\d\d$/.test(t));
  ok(labels.length >= 3 && !/[A-Z][a-z]{2} \d{4}/.test(P.svg().replace(/<text[^>]*>(Source|Made)[^<]*<\/text>/g, "")), "year-only labels: " + labels.join(" "));
  const yrs = labels.map(Number), steps = yrs.slice(1).map((y, i) => y - yrs[i]);
  ok(steps.every(d => d === steps[0]) && yrs.every(y => y % steps[0] === 0), "evenly spaced round years: " + labels.join(" "));
  P.click(P.$('#cmXDateSeg button[data-fmt="auto"]')); await sleep(100);
  ok(/[A-Z][a-z]{2} \d{4}/.test(P.svg()), "month and year labels back");
  // time bars too
  P.click(P.$('#cmXDateSeg button[data-fmt="year"]')); P.click(P.$('#cmChartTypeSeg button[data-type="bar"]')); await sleep(150);
  const bl = [...P.$("#cmSvgBox").querySelectorAll("text")].map(t => t.textContent).filter(t => /^(19|20)\d\d$/.test(t));
  ok(bl.length >= 3, "time bars get year labels: " + bl.join(" "));
  // year format is saved
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "years"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  eq(savedPayloads[savedPayloads.length - 1].style.snapshot.xDateFmt, "year", "date label format saved");

  // 6. no negative zero
  const CM = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
  const f = CM.match(/function czmTrimAxisZeros\([\s\S]*?\n\}\n/)[0] + CM.match(/function czmAxisTickLabel\([\s\S]*?\n\}\n/)[0];
  const lab = new Function(f + "; return czmAxisTickLabel;")();
  const fmt = v => (v < 0 ? "\u2212" : "") + "\u00a3" + Math.abs(v) + "bn";
  eq(lab(0, [-15, -10, 0, 10, 15], fmt), "\u00a30bn", "zero tick has no minus sign");
  eq(lab(0, [-15, 0, 5], fmt), "\u00a30bn", "zero tick beside a larger negative tick");
  eq(lab(-10, [-15, -10, 0], fmt), "\u221210".replace("10", "\u00a310bn"), "negative ticks keep their sign");

  console.log(`test_v19106: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  " + (e && e.stack || e)); console.log(`test_v19106: ${checks} checks, ${failures + 1} failures`); process.exit(1); });
