#!/usr/bin/env node
/* ChartMaker's "Make it real" and "Dollarise" toggles, matched to the country pages and the Dashboard.
 *
 * Layer 1 (vm, every country's real data file): the pure display logic.
 *   - Make it real alone gives exactly the real GDP series, in its own unit
 *   - real GDP in dollars grows exactly as the published real series (one rate)
 *   - nominal dollars equal the Dashboard's conversion point for point (same rates, same floor)
 *   - already-dollar series are not "converted"
 *   - when Dollarise is forced / has nothing to do
 *   - a source note cites the series actually shown, and says when it was converted
 *   - currency names and native "$" symbols exist for every country and match the Dashboard
 * Layer 2 (jsdom, the real page driven through the DOM): buttons, labels, highlighting, axis title,
 *   note, announcements, forced and disabled states, and a saved chart carrying both toggles.
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_chartmaker_toggles.js
 */
const fs = require("fs"), vm = require("vm"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = (c, m) => { checks++; if (!c) fail(m); else if (process.env.VERBOSE) console.log("   ok   " + m); };
const eq = (a, b, m) => ok(a === b, `${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);

/* ---------------------------- layer 1: vm ---------------------------- */
function fn(src, name){
  const i = src.indexOf("function " + name + "("); if(i < 0) throw new Error("missing function " + name);
  let d = 0, j = src.indexOf("{", i);
  for(; j < src.length; j++){ if(src[j] === "{") d++; else if(src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1);
}
function varLit(src, name){
  const i = src.indexOf("var " + name + " ="); if(i < 0) throw new Error("missing var " + name);
  let d = 0, j = src.indexOf("{", i);
  for(; j < src.length; j++){ if(src[j] === "{") d++; else if(src[j] === "}" && --d === 0) break; }
  return src.slice(i, j + 1) + ";";
}
const cmSrc = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
const dashSrc = fs.readFileSync(path.join(ROOT, "dashboard.html"), "utf8");
const FILES = vm.runInNewContext("(" + cmSrc.match(/var FILES\s*=\s*(\{[\s\S]*?\});/)[1] + ")");
const SOURCE_MAP = JSON.parse(fs.readFileSync(path.join(ROOT, "data-metric-sources.json"), "utf8"));

const names = ["monthKey", "rateForPeriod", "nearestFxYear", "toUSDValue", "scaleOf", "isAlreadyUSDUnit", "forceUSDUnit",
  "toUSDMillions", "computeDisplay", "dollarBasis", "displayMetric", "citationText", "getSourceNote", "shortSourceNote", "buildCombinedSrcNote", "foreignCurrencyOf"];
const vars = ["CONCEPT_UNIT", "COUNTRY_CURRENCY", "DOLLAR_GLYPH_LOCAL_CURRENCY_COUNTRIES", "CURRENCY_NAME", "NATIVE_DOLLAR_SYMBOL"];
const cm = { console };
vm.createContext(cm);
vm.runInContext(
  "var FX_RATES = {}, REGISTRY = {}, series = [], SOURCE_MAP = {}, POLICY_RATE_KEYS = [];\n" +
  vars.map(v => varLit(cmSrc, v)).join("\n") + "\n" + (src => (src.match(/var CURRENCY_GLYPH_CODE[^\n]*/) || [""])[0])(cmSrc) + "\n" +
  varLit(cmSrc, "SOURCE_ALT_KEYS") + "\n" +
  names.map(n => fn(cmSrc, n)).join("\n") + "\n" +
  // the page's getSeries reads REGISTRY[country][concept] and rolls quarterly GDP up; the logic under test only
  // needs the points and unit, so this stand-in returns the served series as is
  "function getSeries(country, concept){ var r = REGISTRY[country] && REGISTRY[country][concept]; if(!r) return null; return {label: concept, unit: r.unit, freq: r.freq, points: r.points}; }\n" +
  "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };\n" +
  "this.setSeries = function(x){ series = x; };\n" +
  "this.setSources = function(x){ SOURCE_MAP = x; };\n" +
  names.concat(vars, ["getSeries"]).map(n => `this.${n}=${n};`).join(""), cm);

const D = { console }; vm.createContext(D);
vm.runInContext(
  "var FX_RATES = {}, REGISTRY = {}, dollarise = true, DOLLAR_GLYPH_LOCAL_CURRENCY_COUNTRIES = {Australia:1, Canada:1, Mexico:1, \"South Africa\":1, Brazil:1};\n" +
  (src => (src.match(/var CURRENCY_GLYPH_CODE[^\n]*/) || [""])[0])(dashSrc) + "\n" +
  ["monthKey", "rateForPeriod", "isRealGDPKey", "realFxYearFor", "usdRateFor", "toUSDValue", "toDisplayPoints", "isCurrencyUnit", "isAlreadyUSD", "foreignCurrencyOf"].map(n => fn(dashSrc, n)).join("\n") + "\n" +
  "this.setData = function(f, r){ FX_RATES = f; REGISTRY = r; };\nthis.toDisplayPoints = toDisplayPoints;", D);

cm.setSources(SOURCE_MAP);
const toObj = pts => pts.map(p => ({ x: p[0], y: p[1] }));
let tested = 0;
for(const [country, file] of Object.entries(FILES)){
  const data = JSON.parse(fs.readFileSync(path.join(ROOT, file), "utf8"));
  const s = data.series || {}, fx = data.fx_to_usd;
  const nom = s.gdp_level, real = s.gdp_real;
  if(!nom || !real) { fail(country + ": missing gdp_level or gdp_real"); continue; }
  cm.setData(fx ? { [country]: fx } : {}, { [country]: s });
  D.setData(fx ? { [country]: fx } : {}, { [country]: s });
  tested++;
  const nomPts = toObj(nom.points);

  // 1. Make it real alone: exactly the real series, in its own unit; nothing else changes
  const r = cm.computeDisplay(country, "gdp_level", nom.unit, nomPts, true, false);
  ok(r.realView === true && r.converted === false && r.inUSD === false, `${country}: real alone is a real view, unconverted`);
  ok(r.unit === real.unit && r.pts.length === real.points.length && r.pts.every((p, i) => p.x === real.points[i][0] && p.y === real.points[i][1]),
     `${country}: real alone is exactly the real GDP series`);
  const off = cm.computeDisplay(country, "gdp_level", nom.unit, nomPts, false, false);
  ok(off.realView === false && off.pts === nomPts && off.unit === nom.unit, `${country}: both off leaves the nominal series untouched`);
  // a non-GDP metric is never swapped
  if(s.unemployment){
    const u = cm.computeDisplay(country, "unemployment", s.unemployment.unit, toObj(s.unemployment.points), true, true);
    ok(u.realView === false && u.inUSD === false, `${country}: Make it real and Dollarise leave a % series alone`);
  }
  if(country === "US" || !fx) continue;

  // 2. real GDP in dollars grows exactly as the published real series
  const rd = cm.computeDisplay(country, "gdp_level", nom.unit, nomPts, true, true);
  ok(rd.realView && rd.inUSD && rd.unit === "$m" && rd.pts.length === real.points.length, `${country}: real + dollars is a real view in $m, nothing dropped`);
  let worst = 0;
  for(let i = 1; i < rd.pts.length; i++){
    const g = rd.pts[i].y / rd.pts[i - 1].y, h = real.points[i][1] / real.points[i - 1][1];
    worst = Math.max(worst, Math.abs(g / h - 1));
  }
  ok(worst < 1e-9, `${country}: real dollar growth equals published real growth (max rel diff ${worst})`);

  // 3. nominal dollars equal the Dashboard's, point for point
  const nd = cm.computeDisplay(country, "gdp_level", nom.unit, nomPts, false, true);
  const dash = D.toDisplayPoints(nom.points, nom.unit, country, "gdp_level");
  ok(nd.pts.length === dash.length, `${country}: nominal dollars keep the same points as the Dashboard (${nd.pts.length} vs ${dash.length})`);
  const scale = cm.scaleOf(nom.unit) / 1e6;
  let drift = 0;
  nd.pts.forEach((p, i) => { if(dash[i] && dash[i][1]) drift = Math.max(drift, Math.abs(p.y / (dash[i][1] * scale) - 1)); });
  ok(drift < 1e-9, `${country}: nominal dollars match the Dashboard (max rel diff ${drift})`);
  const already = cm.isAlreadyUSDUnit(nom.unit, country, "gdp_level");
  eq(nd.converted, !already, `${country}: converted flag follows whether the unit was already dollars`);
  ok(nd.inUSD && nd.unit === "$m", `${country}: dollarised nominal is drawn in $m`);
  if(fx.floor){
    const fk = cm.monthKey(String(fx.floor));
    ok(nd.pts.every(p => cm.monthKey(String(p.x)) >= fk), `${country}: nothing before fx.floor is shown in dollars`);
    eq(nd.droppedBeforeFloor, nomPts.some(p => cm.monthKey(String(p.x)) < fk), `${country}: droppedBeforeFloor reports whether the floor removed points`);
  }
}
ok(tested >= 60, `checked ${tested} countries`);

// forced / no-op rules
const B = (items, pref) => cm.dollarBasis(items, pref);
const g = (country, metric) => ({ country, metric: metric || "gdp_level" });
let b = B([g("US")], true);   ok(b.noOp && !b.forced && b.dollar === false, "US only: nothing to convert, Dollarise has no effect");
b = B([g("UK")], true);       ok(!b.noOp && !b.forced && b.dollar === true, "one country: the person's choice (on)");
b = B([g("UK")], false);      ok(!b.forced && b.dollar === false, "one country: the person's choice (off)");
b = B([g("UK"), g("US")], false); ok(b.forced && b.dollar === true, "UK and US: forced on whatever the choice");
b = B([g("Germany"), g("France")], false); ok(!b.forced && b.dollar === false, "two euro countries share a currency: not forced");
b = B([g("Germany"), g("Japan")], false);  ok(b.forced, "euro and yen: forced");
b = B([g("US"), g("Switzerland")], false); ok(b.forced, "US and Switzerland (CHF): forced, so mixed scales are brought to one basis");
b = B([g("UK", "unemployment"), g("US", "unemployment")], false); ok(!b.forced && !b.noOp && b.dollar === false, "% series never force a conversion");
b = B([], true);              ok(!b.forced && !b.noOp && b.dollar === true, "nothing on the chart: the choice stands");

// source notes cite what is shown
for(const country of Object.keys(FILES)){
  const realSrc = cm.shortSourceNote(country, "gdp_real"), nomSrc = cm.shortSourceNote(country, "gdp_level");
  ok(!!realSrc, `${country}: has a real GDP source to cite`);
  cm.setSeries([{ country, metric: "gdp_level", realView: true, converted: false }]);
  eq(cm.buildCombinedSrcNote(), `${country}: ${realSrc}`, `${country}: a real series cites the real source`);
  cm.setSeries([{ country, metric: "gdp_level", realView: false, converted: false }]);
  eq(cm.buildCombinedSrcNote(), `${country}: ${nomSrc}`, `${country}: a nominal series cites the nominal source`);
}
cm.setSeries([{ country: "UK", metric: "gdp_level", realView: false, converted: true }, { country: "Japan", metric: "gdp_level", realView: false, converted: true }]);
ok(/\(converted to USD\)$/.test(cm.buildCombinedSrcNote()), "a converted chart's source note ends (converted to USD), Compare's wording");
cm.setSeries([{ country: "US", metric: "gdp_level", realView: false, converted: false }]);
ok(!/converted/.test(cm.buildCombinedSrcNote()), "an unconverted chart's source note does not claim a conversion");

// names and symbols
for(const [country, code] of Object.entries(cm.COUNTRY_CURRENCY)) ok(!!cm.CURRENCY_NAME[code], `currency name exists for ${country} (${code})`);
const dashNative = vm.runInNewContext("(" + dashSrc.match(/var NATIVE_SYMBOL_OVERRIDES = (\{[\s\S]*?\});/)[1] + ")");
eq(JSON.stringify(Object.entries(cm.NATIVE_DOLLAR_SYMBOL).sort()), JSON.stringify(Object.entries(dashNative).sort()), "native $ symbols match the Dashboard's");

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

(async () => {
  const win = await boot(), doc = win.document, $ = s => doc.querySelector(s);
  const click = el => el.dispatchEvent(new win.Event("click", { bubbles: true }));
  const svgText = () => ($("#cmSvgBox") ? $("#cmSvgBox").textContent.replace(/\s+/g, " ").trim() : "");
  const labels = () => [...doc.querySelectorAll("#cmSeriesList .main-edit")].map(i => i.value);
  const rows = () => [...doc.querySelectorAll("#cmSeriesList .cm-seriesitem")];
  // Waits for what it needs instead of sleeping a fixed time, so a slow machine does not cause a false failure.
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

  const real = () => $("#makeRealToggle"), dol = () => $("#dollariseToggle");
  const toggle = async el => { click(el); await sleep(180); };

  // buttons exist in the site's order, off, with a note area and a live region
  const btns = [...doc.querySelectorAll(".metric-toggles button.mtoggle")].map(b => b.textContent.trim());
  eq(btns.join(" | "), "Make it real | Dollarise", "toggle order matches the country pages and Dashboard");
  eq(real().getAttribute("aria-pressed"), "false", "Make it real starts off");
  eq(dol().getAttribute("aria-pressed"), "false", "Dollarise starts off");
  ok(!!$("#mtoggleAnnounce") && $("#mtoggleAnnounce").getAttribute("aria-live") === "polite", "a polite live region announces changes");

  // UK, nominal
  await add("UK", "GDP level");
  eq(labels()[0], "UK, GDP level", "UK nominal label");
  ok(svgText().includes("\u00a3"), "UK nominal ticks carry the pound sign");
  eq($("#cmYAxisTitle").value, "Pounds sterling", "UK nominal axis names the currency");

  // Make it real
  await toggle(real());
  eq(labels()[0], "UK, Real GDP level", "Make it real renames the series to what it shows");
  ok(real().classList.contains("on") && real().classList.contains("fx-real") && real().getAttribute("aria-pressed") === "true", "Make it real button is on and yellow");
  ok(rows()[0].classList.contains("fx-real"), "the swapped series row glows yellow");
  ok(/GDP shown in real terms/.test($("#mtoggleNote").textContent), "the note says GDP is shown in real terms");
  eq($("#mtoggleAnnounce").textContent, "Make it real: on", "screen readers are told");
  ok(!/US dollars/.test($("#cmYAxisTitle").value), "real alone does not claim dollars");

  // plus Dollarise
  await toggle(dol());
  eq(labels()[0], "UK, Real GDP level (USD)", "dollarised real series says (USD)");
  ok(real().classList.contains("fx-both") && dol().classList.contains("fx-both") && dol().classList.contains("on"), "both buttons go green when both are on");
  ok(rows()[0].classList.contains("fx-both"), "the row glows green");
  ok(/GBP\/USD rate/.test($("#mtoggleNote").textContent) && /average rate throughout/.test($("#mtoggleNote").textContent) && /not purchasing power parity/.test($("#mtoggleNote").textContent),
     "the note explains the conversion, the one-rate real GDP rule and market rates");
  eq($("#cmYAxisTitle").value, "US dollars", "dollar axis is named");
  ok(svgText().includes("$") && !svgText().includes("\u00a3"), "ticks switch to dollars");
  eq($("#mtoggleAnnounce").textContent, "Dollarise: on", "Dollarise announced");

  // Make it real off again
  await toggle(real());
  eq(labels()[0], "UK, GDP level (USD)", "real off returns to nominal, still dollars");
  ok(!real().classList.contains("on") && !real().classList.contains("fx-real") && dol().classList.contains("fx-dollar") && rows()[0].classList.contains("fx-dollar"), "colours return to blue only");
  ok(!/real terms/.test($("#mtoggleNote").textContent), "the real-terms note goes away");

  // a custom title is respected: no suffix is forced onto it
  const nameInput = doc.querySelector("#cmSeriesList .main-edit");
  nameInput.value = "My UK line"; nameInput.dispatchEvent(new win.Event("input", { bubbles: true })); await sleep(100);
  eq(labels()[0], "My UK line", "a renamed series keeps the person's title");
  await toggle(dol()); // back to native
  eq(doc.querySelector("#cmSeriesList .main-edit").value, "My UK line", "custom title survives a toggle");

  // forced: UK + US
  nameInput.value = ""; nameInput.dispatchEvent(new win.Event("input", { bubbles: true })); await sleep(60);
  await add("US", "GDP level");
  ok(dol().disabled && dol().getAttribute("aria-disabled") === "true", "different currencies: Dollarise is disabled");
  ok(!dol().classList.contains("on") && dol().title === "Needed to compare different currencies", "forced Dollarise looks off and says why");
  ok(/^Converted to US dollars automatically/.test($("#mtoggleNote").textContent), "the note explains the automatic conversion");
  ok(labels().every(l => /\(USD\)$/.test(l)), "every series on a dollar chart says (USD): " + labels().join(" / "));
  ok(rows().filter(r => r.classList.contains("fx-dollar")).length === 1, "only the series actually converted (UK) glows; the US one was already dollars");
  const before = svgText(); click(dol()); await sleep(120); eq(svgText(), before, "clicking a forced button changes nothing");

  // US only: nothing to do
  const removeBtns = () => [...doc.querySelectorAll("#cmSeriesList .cm-seriesitem button")].filter(b => /remove|\u00d7|x/i.test(b.getAttribute("aria-label") || b.title || b.textContent));
  const ukRow = rows().filter(r => /UK/.test(r.querySelector(".main-edit").value))[0];
  const ukRemove = [...ukRow.querySelectorAll("button")].filter(b => /remove|\u00d7/i.test(b.getAttribute("aria-label") || b.title || b.textContent))[0] || ukRow.querySelector("button:last-of-type");
  click(ukRemove); await sleep(180);
  eq(rows().length, 1, "UK removed");
  ok(dol().disabled && dol().title === "Already in US dollars", "US only: Dollarise is disabled as already in US dollars");
  eq($("#mtoggleNote").textContent, "", "US only: no conversion note");
  ok(!/\(USD\)/.test(labels()[0]), "US only: no (USD) marker, nothing was converted");
  eq($("#cmYAxisTitle").value, "US dollars", "US only: axis still names the currency");
  click(rows()[0].querySelector("button:last-of-type")); await sleep(150);

  // Canada: native "$" is not the US dollar
  await add("Canada", "GDP level");
  ok(svgText().includes("C$"), "Canada native ticks read C$, as on its own page");
  eq($("#cmYAxisTitle").value, "Canadian dollars", "Canada native axis says Canadian dollars");
  await toggle(dol());
  ok(!svgText().includes("C$") && svgText().includes("$"), "Canada dollarised ticks read $");
  eq($("#cmYAxisTitle").value, "US dollars", "Canada dollarised axis says US dollars");
  await toggle(dol());
  click(rows()[0].querySelector("button:last-of-type")); await sleep(150);

  // Switzerland: nominal is already dollars, real is francs
  await add("Switzerland", "GDP level");
  eq($("#cmYAxisTitle").value, "US dollars", "Switzerland nominal axis is dollars (World Bank series)");
  await toggle(real());
  eq($("#cmYAxisTitle").value, "Swiss francs", "Switzerland real axis is francs");
  ok(svgText().includes("CHF"), "Switzerland real ticks read CHF");
  await toggle(dol());
  eq(labels()[0], "Switzerland, Real GDP level (USD)", "Switzerland real in dollars");
  eq($("#cmYAxisTitle").value, "US dollars", "Switzerland real dollarised axis");
  await toggle(dol()); await toggle(real());
  click(rows()[0].querySelector("button:last-of-type")); await sleep(150);

  // saved chart carries both toggles
  await add("UK", "GDP level");
  await toggle(real()); await toggle(dol());
  click($("#cmSaveBtn")); await sleep(60);
  $("#cmSaveNameInput").value = "toggle chart";
  click($("#cmSaveConfirmBtn")); await sleep(300);
  eq(savedPayloads.length, 1, "chart was saved");
  const snap = savedPayloads[0] && savedPayloads[0].style.snapshot;
  ok(snap && snap.real === true && snap.dollar === true, "the saved chart records Make it real and Dollarise: " + JSON.stringify(snap && { real: snap.real, dollar: snap.dollar }));
  // an older chart, saved before the toggles existed, and this one
  const olderStyle = JSON.parse(JSON.stringify(savedPayloads[0].style)); delete olderStyle.snapshot.real; delete olderStyle.snapshot.dollar;
  savedRows = [
    { id: 1, name: "toggle chart", country_code: "chartmaker", created_at: "2026-10-19T12:00:00Z", style: savedPayloads[0].style, from_period: savedPayloads[0].from_period, to_period: savedPayloads[0].to_period, metric_key: "gdp_level" },
    { id: 2, name: "older chart", country_code: "chartmaker", created_at: "2026-10-18T12:00:00Z", style: olderStyle, from_period: savedPayloads[0].from_period, to_period: savedPayloads[0].to_period, metric_key: "gdp_level" },
  ];
  // start from both off, then open the saved one
  await toggle(real()); await toggle(dol());
  eq(labels()[0], "UK, GDP level", "both off before opening");
  click($("#cmOpenBtn")); await sleep(400);
  const openBtns = [...doc.querySelectorAll(".cm-savedrow")].map(r => ({ name: r.querySelector(".cm-savedname").textContent, open: r.querySelector("button.open"), thumb: r.querySelector(".cm-savedthumb").textContent.replace(/\s+/g, " "), paths: [...r.querySelectorAll(".cm-savedthumb path")].map(x => x.getAttribute("d")).join("|") }));
  const tc = openBtns.filter(x => x.name === "toggle chart")[0], oc = openBtns.filter(x => x.name === "older chart")[0];
  // v1.9.32: a single line has no legend (as in Customise & export), so the thumbnail is read by its axis
  ok(tc && /US dollars/.test(tc.thumb), "the Open list thumbnail shows the real, dollar series it was saved as: " + (tc && tc.thumb.slice(0, 80)));
  // the older chart carries the same saved axis title, so it is told apart by what it plots: nominal pounds, not real dollars
  ok(oc && tc && oc.paths && oc.paths !== tc.paths, "an older chart's thumbnail is drawn from its own (nominal, own-currency) data");
  click(tc.open); await sleep(300);
  ok(real().getAttribute("aria-pressed") === "true" && dol().getAttribute("aria-pressed") === "true", "opening the saved chart restores both toggles");
  eq(labels()[0], "UK, Real GDP level (USD)", "and the series shows as saved");
  click($("#cmOpenBtn")); await sleep(400);
  const oc2 = [...doc.querySelectorAll(".cm-savedrow")].filter(r => r.querySelector(".cm-savedname").textContent === "older chart")[0];
  click(oc2.querySelector("button.open")); await sleep(300);
  ok(real().getAttribute("aria-pressed") === "false" && dol().getAttribute("aria-pressed") === "false", "an older chart opens with both toggles off");
  eq(labels()[0], "UK, GDP level", "and shows nominal, native");

  ok(bootErrors.length === 0, "no uncaught page errors: " + bootErrors.slice(0, 3).join(" | "));
  console.log(`\n${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("test crashed:", e && e.stack || e); process.exit(2); });
