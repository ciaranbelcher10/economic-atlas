#!/usr/bin/env node
/* ChartMaker (v1.9.43): new data on an empty chart clears the old chart title; adding data or reopening a saved chart keeps it.
 * Style control matching a reopened, other-page or reset chart. Run: NODE_PATH=/tmp/node_modules node tools/test_chartmaker_title_reset.js */
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
const setTitle = (P, v) => { const e = P.$("#cmChartTitle"); e.value = v; P.fire(e, "input"); };
const removeAll = async P => { for(const b of [...P.doc.querySelectorAll("#cmSeriesList .cm-rm")]) { P.click(b); await sleep(60); } };
const drawnTitle = P => /font-size=["']16["'] font-weight=["']700["']/.test(P.svg());
(async () => {
  let P = await page();
  // 1. adding to a chart keeps its title
  await P.add("UK", "Unemployment rate");
  setTitle(P, "Old title"); await sleep(80);
  ok(drawnTitle(P), "title drawn after typing");
  await P.add("Germany", "Unemployment rate"); await sleep(80);
  eq(P.$("#cmChartTitle").value, "Old title", "adding a second series keeps the title box");
  ok(drawnTitle(P), "adding a second series keeps the drawn title");
  // 2. emptying the chart then loading new data clears it
  await removeAll(P);
  eq(P.doc.querySelectorAll("#cmSeriesList .cm-seriesitem").length, 0, "chart emptied");
  await P.add("US", "GDP level"); await sleep(80);
  eq(P.$("#cmChartTitle").value, "", "new data on an empty chart: title box cleared");
  ok(!drawnTitle(P), "new data on an empty chart: no title drawn");
  // 3. a reopened saved chart keeps its saved title, and adding to it keeps it too
  setTitle(P, "Saved title"); await sleep(60);
  savedPayloads.length = 0;
  P.click(P.$("#cmSaveBtn")); P.$("#cmSaveNameInput").value = "keep"; P.click(P.$("#cmSaveConfirmBtn")); await sleep(300);
  eq(savedPayloads.length, 1, "chart saved");
  const sp = savedPayloads[0];
  savedRows = [{ id: 31, name: "keep", country_code: "chartmaker", created_at: "2026-11-01T12:00:00Z", style: JSON.parse(JSON.stringify(sp.style)), from_period: sp.from_period, to_period: sp.to_period, metric_key: "gdp_level" }];
  P = await page();
  await P.add("Germany", "Unemployment rate");
  setTitle(P, "Other chart"); await sleep(60);
  await P.openSaved("keep"); await sleep(200);
  eq(P.$("#cmChartTitle").value, "Saved title", "reopened chart keeps its title");
  await P.add("UK", "GDP level"); await sleep(80);
  eq(P.$("#cmChartTitle").value, "Saved title", "adding to a reopened chart keeps its title");
  // 4. the example chart's title does not carry over to the person's first data
  const P2 = await page();
  if(P2.$("#cmStarterNote") && !P2.$("#cmStarterNote").hidden){
    setTitle(P2, "Example title"); await sleep(60);
    await P2.add("France", "Unemployment rate"); await sleep(80);
    eq(P2.$("#cmChartTitle").value, "", "first own data after the example: title cleared");
  } else ok(true, "no example chart on load");
  ok(bootErrors.length === 0, "no page errors: " + bootErrors.slice(0, 3).join(" | "));
  console.log(`test_chartmaker_title_reset: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("CRASH " + (e && e.stack || e)); process.exit(2); });
