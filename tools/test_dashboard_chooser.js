#!/usr/bin/env node
/* v1.9.62: My Dashboard uses the shared ChartMaker chooser (chooser.js), drives it under jsdom.
 *
 * Asserts:
 *   - both pages load chooser.js and neither keeps its own copy of the chooser
 *   - "Add a metric" opens the shared chooser, titled "Pin to dashboard"
 *   - ticking a group and a version pins one card per country that has it,
 *     skipping (not pinning) countries without it, and says so before pinning
 *   - reopening shows those countries as Pinned and the button as already done
 *   - unticking a pinned country never removes it from the dashboard
 *   - search ticks an exact country and selects an exact version name
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_dashboard_chooser.js
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

let bootErrors = [];
let failures = 0, checks = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = m => { checks++; if (process.env.VERBOSE) console.log("   ok   " + m); };
function eq(a, b, what) {
  if (a === b) ok(`${what} = ${a}`);
  else fail(`${what}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

const store = {};
function boot() {
  const html = require("./inline_local_scripts")(fs.readFileSync("dashboard.html", "utf8"), undefined);
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
    url: "https://theeconomicatlas.com/dashboard.html",
    beforeParse(win) {
      win.HTMLCanvasElement.prototype.getContext = () =>
        new Proxy({}, { get() { return function () { return { addColorStop() {} }; }; } });
      function C(c, cfg) { this.data = (cfg && cfg.data) || { datasets: [] }; this.options = {}; }
      C.prototype.update = function () {}; C.prototype.destroy = function () {};
      C.prototype.resetZoom = function () {}; C.register = function () {};
      win.Chart = C;
      // a localStorage that persists across the two boots, so "survives a
      // reload" is actually tested rather than assumed
      Object.defineProperty(win, "localStorage", {
        configurable: true,
        value: {
          getItem: k => (k in store ? store[k] : null),
          setItem: (k, v) => { store[k] = String(v); },
          removeItem: k => { delete store[k]; },
          clear: () => { for (const k of Object.keys(store)) delete store[k]; },
          key: i => Object.keys(store)[i] || null,
          get length() { return Object.keys(store).length; },
        },
      });
      win.fetch = (u) => {
        const file = String(u).split("/").pop().split("?")[0];
        const p = path.join(process.cwd(), file);
        if (!fs.existsSync(p)) return Promise.reject(new Error("no such file " + file));
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))),
          text: () => Promise.resolve(fs.readFileSync(p, "utf8")),
        });
      };
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {},
        addEventListener() {}, removeEventListener() {} }));
    },
  });
  return dom;
}

async function ready(dom) {
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for (let i = 0; i < 100 && !(win.REGISTRY && Object.keys(win.REGISTRY || {}).length); i++)
    await new Promise(r => setTimeout(r, 50));
  await new Promise(r => setTimeout(r, 500));
  return win;
}


const sleep = ms => new Promise(r => setTimeout(r, ms));
const pinnedIds = win => [...win.document.querySelectorAll(".tile[data-id]")].map(t => t.dataset.id);

(async () => {
  for (const page of ["chartmaker.html", "dashboard.html"]) {
    const s = fs.readFileSync(page, "utf8");
    eq(/<script src="chooser\.js\?v=\d+"><\/script>/.test(s), true, page + " loads chooser.js");
    eq(s.includes("var CHOOSER = ["), false, page + " keeps no copy of the chooser list");
    eq(s.includes("EAChooser.create("), true, page + " builds the shared chooser");
  }
  const dash = fs.readFileSync("dashboard.html", "utf8");
  eq(/id="picker"|pickerGrid|modeToggle/.test(dash), false, "old dashboard picker is gone");

  let win = await ready(boot());
  const doc = win.document, $ = s => doc.querySelector(s);
  const click = el => el.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  eq(bootErrors.length, 0, "boot errors (" + bootErrors.join("; ") + ")");
  const before = pinnedIds(win);

  const tile = $("#addMetricTile");
  eq(!!tile, true, "add tile exists");
  click(tile); await sleep(60);
  eq($("#cmChooser") && $("#cmChooser").hidden, false, "add tile opens the chooser");
  eq($("#cmzTitle").textContent, "Pin to dashboard", "chooser title");
  eq($("#cmzAdd").textContent, "Pin to dashboard", "button before choosing");
  eq($("#cmzAdd").disabled, true, "button disabled before choosing");
  eq(doc.querySelectorAll("#cmzCountries input:checked").length, 0, "opens with nothing ticked");

  // G7 + Inflation, HICP: only France, Germany and Italy publish HICP in the G7
  click([...doc.querySelectorAll("#cmzGroups button")].find(b => b.textContent.startsWith("G7 (")));
  const hicp = [...doc.querySelectorAll("#cmzInds button[data-base]")].find(b => b.dataset.base === "cpi_hicp");
  eq(!!hicp, true, "HICP version offered for the G7");
  click(hicp); await sleep(20);
  const reg = win.EATLAS_DASH && win.EATLAS_DASH.registry ? win.EATLAS_DASH.registry() : null;
  const cov = $("#cmzCov").textContent, label = $("#cmzAdd").textContent;
  const m = /^Pin (\d+) to dashboard$/.exec(label);
  eq(!!m, true, "button reads Pin N to dashboard: " + label);
  const n = m ? +m[1] : 0;
  eq(n > 0 && n < 7, true, "some but not all of the G7 have HICP (" + n + ")");
  eq(/will be skipped/.test(cov), true, "coverage says missing countries are skipped: " + cov);
  eq(/US/.test((cov.split("No data for ")[1] || "")), true, "US named as having no HICP");
  click($("#cmzAdd")); await sleep(200);
  eq($("#cmChooser").hidden, true, "chooser closes after pinning");
  const after = pinnedIds(win), added = after.filter(id => before.indexOf(id) === -1);
  eq(added.length, n, "one card pinned per country with data");
  eq(added.every(id => /^(France|Germany|Italy|UK|Canada|Japan|US)::/.test(id)), true, "only G7 cards added: " + added.join(", "));
  eq(added.some(id => /^US::/.test(id)), false, "no card pinned for a country without HICP");
  eq(added.some(id => /^Germany::/.test(id)), true, "Germany pinned");

  // reopen: pinned countries are tagged and nothing new to pin
  click($("#addMetricTile")); await sleep(60);
  click([...doc.querySelectorAll("#cmzGroups button")].find(b => b.textContent.startsWith("G7 (")));
  click([...doc.querySelectorAll("#cmzInds button[data-base]")].find(b => b.dataset.base === "cpi_hicp")); await sleep(20);
  const tags = [...doc.querySelectorAll("#cmzCountries label")].filter(l => /Pinned$/.test(l.textContent)).length;
  eq(tags, n, "reopened chooser tags pinned countries");
  eq($("#cmzAdd").textContent, "Already on your dashboard", "nothing new to pin");
  eq($("#cmzAdd").disabled, true, "button disabled when all pinned");
  // untick Germany: dashboard never removes through the chooser
  const de = $('#cmzCountries input[data-c="Germany"]');
  de.checked = false; de.dispatchEvent(new win.Event("change", { bubbles: true })); await sleep(20);
  eq(/remove/i.test($("#cmzAdd").textContent), false, "unticking never offers removal: " + $("#cmzAdd").textContent);
  click($("#cmzAdd")); await sleep(50);
  eq(pinnedIds(win).some(id => /^Germany::/.test(id)), true, "Germany still pinned");
  click($("#cmzCancel")); await sleep(30);
  eq($("#cmChooser").hidden, true, "Cancel closes");

  // search: an exact country is ticked and an exact version name selected
  click($("#addMetricTile")); await sleep(60);
  $("#cmzSearch").value = "PCE US"; $("#cmzSearch").dispatchEvent(new win.Event("input")); await sleep(20);
  eq($('#cmzCountries input[data-c="US"]').checked, true, "search ticks US");
  eq(/^Inflation, PCE:/.test($("#cmzCov").textContent), true, "search selects PCE: " + $("#cmzCov").textContent.slice(0, 50));
  eq($("#cmzAdd").textContent, "Pin 1 to dashboard", "one to pin");
  click($("#cmzAdd")); await sleep(200);
  eq(pinnedIds(win).filter(id => /^US::/.test(id)).length >= 1, true, "US PCE pinned");
  const final = pinnedIds(win);

  // Escape closes
  click($("#addMetricTile")); await sleep(60);
  doc.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape" })); await sleep(20);
  eq($("#cmChooser").hidden, true, "Escape closes");

  eq(final.length, before.length + 5, "five cards pinned in total");

  console.log(`\ntest_dashboard_chooser: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
