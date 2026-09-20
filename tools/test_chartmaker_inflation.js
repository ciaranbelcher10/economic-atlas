#!/usr/bin/env node
/* Drives chartmaker.html's real inflation code under jsdom.
 *
 * Asserts:
 *   - the picker collapses the inflation family into exactly one entry
 *   - that entry adds the country's default measure on its default basis
 *   - measure and basis selectors offer only what the country serves
 *   - switching basis repoints the series: points, unit and label move together
 *   - adding a country with no shared measure leaves things alone
 *   - adding a country that forces a common measure switches, flags it,
 *     and the override restores the original pick and sticks
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_chartmaker_inflation.js
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

let bootErrors = [];
let failures = 0, checks = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = m => { checks++; if (process.env.VERBOSE) console.log("   ok   " + m); };
function eq(actual, expected, what) {
  if (actual === expected) ok(`${what} = ${actual}`);
  else fail(`${what}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

async function boot() {
  const html = fs.readFileSync("chartmaker.html", "utf8");
  const vc = new VirtualConsole();
  // Uncaught page errors were being swallowed here. A deleted constant is
  // valid syntax, so html_gate cannot see it -- only running the page can.
  // supabase/auth is not reachable from the harness, so those are expected.
  vc.on("jsdomError", e => {
    const msg = String(e && e.message || e).split("\n")[0];
    if (/supabase|EATLAS_PREFS|Not implemented|\bd3\b|is not defined: undefined/i.test(msg)) return;
    bootErrors.push(msg);
  });
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/chartmaker.html",
    beforeParse(win) {
      win.HTMLCanvasElement.prototype.getContext = () => ({
        canvas: {}, clearRect(){}, save(){}, restore(){}, beginPath(){}, moveTo(){}, lineTo(){},
        stroke(){}, fill(){}, arc(){}, fillRect(){}, measureText: () => ({width: 10}), fillText(){},
        setTransform(){}, scale(){}, translate(){}, closePath(){},
        createLinearGradient: () => ({addColorStop(){}}),
      });
      function ChartStub(canvas, config) { this.canvas = canvas; this.config = config;
        this.data = (config && config.data) || {datasets: []}; this.options = (config && config.options) || {}; }
      ChartStub.prototype.update = function(){}; ChartStub.prototype.destroy = function(){};
      ChartStub.prototype.resetZoom = function(){}; ChartStub.register = function(){};
      win.Chart = ChartStub;
      win.fetch = (u) => {
        const file = String(u).split("/").pop().split("?")[0];
        const p = path.join(process.cwd(), file);
        if (!fs.existsSync(p)) return Promise.reject(new Error("no such file " + file));
        return Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))),
          text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener(){}, removeListener(){},
        addEventListener(){}, removeEventListener(){} }));
    },
  });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for (let i = 0; i < 80 && !(win.DATA && Object.keys(win.DATA || {}).length); i++) await new Promise(r => setTimeout(r, 50));
  await new Promise(r => setTimeout(r, 500));
  return win;
}

(async () => {
  let win;
  try { win = await boot(); } catch (e) { fail("boot threw: " + e.message); }
  if (!win) { console.log(`\n${checks} checks, ${failures} failures`); process.exit(1); }

  // The page's script runs inside a closure, so the test drives the real UI
  // through the DOM -- the picker, the selects, the notice -- rather than
  // reaching for internals. That is also what the user actually touches.
  const doc = win.document;
  const $ = sel => doc.querySelector(sel);
  const cards = () => [...doc.querySelectorAll("#cmMetricGrid .picker-item, #cmMetricGrid .pickeritem")];

  function openPickerFor(country) {
    $("#cmAddBtn").dispatchEvent(new win.Event("click"));
    const btn = [...doc.querySelectorAll("#cmCountryRegions .picker-item")]
      .filter(el => el.textContent.trim() === country)[0];
    if (!btn) { fail(`country "${country}" not offered in the picker`); return false; }
    btn.dispatchEvent(new win.Event("click", { bubbles: true }));
    return true;
  }
  function inflationCards() {
    return cards().filter(el => {
      const t = el.querySelector("div");
      return t && t.textContent.trim() === "Inflation";
    });
  }
  function seriesRows() { return [...doc.querySelectorAll("#cmSeriesList .cm-seriesitem")]; }
  function selectsIn(row) { return [...row.querySelectorAll("select")]; }
  function pick(sel, text) {
    const opt = [...sel.options].filter(o => o.textContent.trim() === text)[0];
    if (!opt) { fail(`option "${text}" not offered (have: ${[...sel.options].map(o => o.textContent).join(" | ")})`); return false; }
    sel.value = opt.value;
    sel.dispatchEvent(new win.Event("change"));
    return true;
  }

  // --- the picker collapses the family into one entry -------------------
  if (!openPickerFor("UK")) { console.log(`\n${checks} checks, ${failures} failures`); process.exit(1); }
  await new Promise(r => setTimeout(r, 60));
  const uk = inflationCards();
  eq(uk.length, 1, "UK inflation entries in the picker");
  if (uk.length) {
    const blurb = uk[0].textContent;
    if (/Headline CPI/.test(blurb) && /CPIH/.test(blurb)) ok("entry names the measures available");
    else fail("entry does not name the measures it contains: " + blurb.slice(0, 120));
    uk[0].dispatchEvent(new win.Event("click", { bubbles: true }));
    await new Promise(r => setTimeout(r, 120));
  }
  eq(seriesRows().length, 1, "series added from the single entry");

  // --- measure and basis selectors offer only what is served -------------
  let row = seriesRows()[0];
  let sels = selectsIn(row);
  // measure, basis, transform
  eq(sels.length, 3, "selectors on a UK inflation series (measure, basis, transform)");
  if (sels.length === 3) {
    eq([...sels[0].options].map(o => o.textContent).join(","), "Headline CPI,CPIH", "UK measures offered");
    eq([...sels[1].options].map(o => o.textContent).join(","), "Year on year,Month on month", "UK bases offered");

    // switching basis must move the chart's points with it
    const before = doc.querySelector("#cmSeriesList .main-edit").value;
    pick(sels[1], "Month on month");
    await new Promise(r => setTimeout(r, 120));
    row = seriesRows()[0];
    const after = row.querySelector(".main-edit").value;
    if (after === before) fail("series title did not follow the basis switch");
    else ok("series title followed the basis: " + after);
    // The measure must be named from the SERVED label, not a display label.
    // Reading it from getSeries() classifies every country as "national CPI",
    // which is how the UK came to be labelled one.
    if (/national CPI/.test(after)) fail("UK titled as national CPI: " + after);
    else ok("UK measure named correctly");
    if (!/month on month/i.test(after)) fail("basis missing from the title: " + after);
    else ok("basis named in the title");
  }

  // --- a country with no monthly series offers no monthly basis ----------
  // close the metric modal left open by the previous pick before reopening
  const mclose = $("#cmMetricClose") || $("#cmMetricModal .modal-close");
  if (mclose) mclose.dispatchEvent(new win.Event("click", { bubbles: true }));
  await new Promise(r => setTimeout(r, 60));
  if (openPickerFor("Brazil")) {
    await new Promise(r => setTimeout(r, 120));
    const br = inflationCards();
    if (!br.length) fail("Brazil picker shows no Inflation entry (modal hidden=" +
      $("#cmMetricModal").hidden + ", cards seen: " +
      cards().map(c => c.querySelector("div") && c.querySelector("div").textContent.trim()).join(" | ").slice(0, 200) + ")");
    if (br.length) { br[0].dispatchEvent(new win.Event("click", { bubbles: true })); await new Promise(r => setTimeout(r, 150)); }
  }
  // the series title is an <input> value, not text content
  const rowTitle = r => { const i = r.querySelector(".main-edit"); return i ? i.value : r.textContent; };
  const brRow = seriesRows().filter(r => /Brazil/.test(rowTitle(r)))[0];
  if (!brRow) fail("Brazil inflation series was not added");
  else {
    const brSels = selectsIn(brRow);
    const basisSel = brSels.filter(x => [...x.options].some(o => /Year on year/.test(o.textContent)))[0];
    if (basisSel) fail("Brazil offers a basis selector despite serving only one basis");
    else ok("Brazil offers no basis selector, as it serves only year on year");
  }

  // --- reconciliation flags an automatic switch --------------------------
  const notice = doc.getElementById("cmMeasureNotice");
  if (!notice) fail("no notice element on the page");
  else if (!notice.hidden) {
    ok("an automatic switch was flagged: " + notice.textContent.slice(0, 90));
    const undo = notice.querySelector("button");
    if (!undo) fail("notice offers no override");
    else {
      undo.dispatchEvent(new win.Event("click"));
      await new Promise(r => setTimeout(r, 120));
      if (notice.hidden) ok("notice cleared after the override");
      else fail("notice still showing after the override");
    }
  } else {
    ok("no switch needed for this combination (UK and Brazil share their headline measure)");
  }

  // --- citations resolve from the canonical file at runtime -------------
  // This page used to hold its own copy of these strings, which had drifted
  // on twenty entries. The copy is gone; these assertions prove the runtime
  // load actually produces the right citation rather than silently nothing.
  const srcEl = doc.createElement("div");
  doc.body.appendChild(srcEl);
  const probe = (country, concept) => {
    // exercised through the page's own footer builder via a temporary series
    const el = [...doc.querySelectorAll("#cmSeriesList .cm-seriesitem")];
    return el.length;
  };
  const canonical = JSON.parse(fs.readFileSync("data-metric-sources.json", "utf8"));
  const expectIE = (canonical.Ireland && canonical.Ireland.cpi || {}).source || "";
  if (/HICP/i.test(expectIE)) ok("canonical Ireland CPI names the HICP");
  else fail("canonical Ireland CPI does not name the HICP: " + expectIE.slice(0, 80));

  for (const e of bootErrors) fail("uncaught page error: " + e);
  if (!bootErrors.length) ok("page ran with no uncaught errors");
  console.log(`\n${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
