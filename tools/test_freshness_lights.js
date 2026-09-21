#!/usr/bin/env node
/* Drives the real freshness lights on a country page under jsdom.
 *
 * Loads japan.html with its data file rewritten in memory three ways, and
 * reads the light and tooltip each tile actually renders:
 *
 *   stamped an hour ago   every tile green, tooltip says "Matches the latest
 *                         release", regardless of how old the data point is
 *                         -- Japan's 2023 debt figure is the test of that
 *   stamped five days ago every tile amber, tooltip says it couldn't refresh
 *   unstamped             the old age rule, so pages keep working until the
 *                         pipeline has stamped everything
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_freshness_lights.js
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

let failures = 0, checks = 0;
const fail = m => { failures++; console.log("  FAIL  " + m); };
const ok = m => { checks++; if (process.env.VERBOSE) console.log("   ok   " + m); };

// japan.html by default: its annual debt series is the case the old rule got
// wrong. Pass --all to sweep every country page for any tile that ignores the
// stamp, which is how a browser-side derivation dropping it would show up.
const ALL = process.argv.includes("--all");
let PAGE = "japan.html", DATA = "data-jp.json";

function load(transform) {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", e => {
    const m = String(e && e.message || e).split("\n")[0];
    if (!/supabase|EATLAS_PREFS|Not implemented|\bd3\b/i.test(m)) errs.push(m);
  });
  const dom = new JSDOM(fs.readFileSync(PAGE, "utf8"), {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/" + PAGE,
    beforeParse(win) {
      win.HTMLCanvasElement.prototype.getContext = () =>
        new Proxy({}, { get() { return function () { return { addColorStop() {} }; }; } });
      function C() { this.data = { datasets: [] }; this.options = {}; }
      C.prototype.update = function () {}; C.prototype.destroy = function () {};
      C.prototype.resetZoom = function () {}; C.register = function () {};
      win.Chart = C;
      win.fetch = (u) => {
        const f = String(u).split("/").pop().split("?")[0];
        const p = path.join(process.cwd(), f);
        if (!fs.existsSync(p)) return Promise.reject(new Error("no such file " + f));
        let body = JSON.parse(fs.readFileSync(p, "utf8"));
        if (f === DATA) body = transform(body);
        return Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
      };
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener() {},
        removeListener() {}, addEventListener() {}, removeEventListener() {} }));
    },
  });
  return new Promise(res => dom.window.addEventListener("load", async () => {
    await new Promise(r => setTimeout(r, 900));
    res({ dom, errs });
  }, { once: true }));
}

function stampAll(hoursAgo) {
  return body => {
    const t = new Date(Date.now() - hoursAgo * 3600000).toISOString().slice(0, 16) + "Z";
    for (const k of Object.keys(body.series)) body.series[k].confirmed_at = t;
    return body;
  };
}
const unstamped = body => { for (const k of Object.keys(body.series)) delete body.series[k].confirmed_at; return body; };

function lights(dom) {
  return [...dom.window.document.querySelectorAll(".stat")].map(el => {
    const led = el.querySelector(".led");
    return { key: el.dataset.key, cls: led ? led.className : "", title: led ? (led.getAttribute("title") || "") : "" };
  }).filter(x => x.cls);
}

async function sweep() {
  const pages = fs.readdirSync(".").filter(f => f.endsWith(".html")).sort().map(f => {
    const m = fs.readFileSync(f, "utf8").match(/fetch\("(data(?:-[a-z]{2})?\.json)"/);
    return m && fs.readFileSync(f, "utf8").includes("chartPanel(") ? [f, m[1]] : null;
  }).filter(Boolean);
  for (const [p, d] of pages) {
    PAGE = p; DATA = d;
    const { dom, errs } = await load(stampAll(120));
    const stuck = lights(dom).filter(x => !/orange/.test(x.cls));
    if (stuck.length) fail(`${p}: tiles still green after 5 days unconfirmed: ${stuck.map(x => x.key + " (" + x.title.slice(0, 40) + ")").join("; ")}`);
    else ok(`${p}: every tile honours the stamp`);
    errs.forEach(e => fail(`${p}: uncaught page error: ${e}`));
    dom.window.close();
  }
  console.log(`\n${pages.length} pages swept, ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
}

(async () => {
  if (ALL) return sweep();
  // --- stamped an hour ago: everything green, including old annual data ---
  let { dom, errs } = await load(stampAll(1));
  let L = lights(dom);
  if (!L.length) fail("no tiles with lights rendered");
  const notGreen = L.filter(x => !/green/.test(x.cls));
  if (notGreen.length) fail("recently confirmed tiles not green: " + notGreen.map(x => x.key).join(", "));
  else ok(`all ${L.length} recently confirmed tiles are green`);
  const debt = L.find(x => x.key === "debt_gdp");
  if (debt) {
    if (/green/.test(debt.cls)) ok("debt_gdp green despite its latest point being years old -- the fix");
    else fail("debt_gdp amber despite being confirmed an hour ago");
  }
  if (L.every(x => /Matches the latest release/.test(x.title))) ok("tooltips say what was checked");
  else fail("a confirmed tile's tooltip does not say it matches the latest release: " +
            (L.find(x => !/Matches the latest release/.test(x.title)) || {}).title);
  errs.forEach(e => fail("uncaught page error: " + e));
  dom.window.close();

  // --- stamped five days ago: everything amber --------------------------------
  ({ dom, errs } = await load(stampAll(120)));
  L = lights(dom);
  const notAmber = L.filter(x => !/orange/.test(x.cls));
  if (notAmber.length) fail("tiles not refreshed for 5 days still green: " + notAmber.map(x => x.key).join(", "));
  else ok(`all ${L.length} tiles unconfirmed for 5 days are amber`);
  if (L.every(x => /Couldn't refresh from the source/.test(x.title))) ok("stale tooltips say the refresh failed");
  else fail("a stale tile's tooltip does not explain it");
  dom.window.close();

  // --- unstamped: the age rule still works -------------------------------------
  ({ dom, errs } = await load(unstamped));
  L = lights(dom);
  if (L.length && L.every(x => /green|orange|red/.test(x.cls))) ok("unstamped series fall back to the age rule");
  else fail("unstamped series rendered no light");
  if (L.some(x => /Matches the latest release|Couldn't refresh/.test(x.title)))
    fail("an unstamped series claims to have been checked");
  else ok("unstamped series make no claim about being checked");
  dom.window.close();

  console.log(`\n${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
