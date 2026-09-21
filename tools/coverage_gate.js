#!/usr/bin/env node
/* Country-page coverage gate.
 *
 * The rule: if a country serves a series, the page must make it reachable,
 * and inflation bases must have both a tile and a chart.
 *
 * Why this is a runtime check. Every static audit of this question has been
 * wrong at least once -- a regex over source patterns missed most gaps, and
 * a check keyed on `data-key` reported series as unrendered that were one
 * click away. The site deliberately swaps series behind controls (a basis
 * selector, the "Make it real" toggle), so reachability is decided when the
 * page runs, not by what its source looks like. This loads each real page
 * under jsdom and reads what actually rendered.
 *
 * What counts as reachable:
 *   tile     a .stat element whose data-key or info button names the series
 *   chart    a .panel whose data-key names it
 *   basis    offered by a basis selector on a panel (cpi_mom, cpi_qoq, ...)
 *   toggle   the target of "Make it real": the real-terms variant of a GDP
 *            series drawn on a panel keyed by its nominal counterpart
 *
 * Exit status: non-zero only when a served INFLATION BASIS lacks a tile or a
 * reachable chart -- the rule set in 2C.5, which this gate now enforces.
 * Everything else is reported, not failed, so known outstanding gaps do not
 * block unrelated deploys while still being visible on every run.
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/coverage_gate.js
 *      add --verbose to list every page, not only those with findings
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const VERBOSE = process.argv.includes("--verbose");

// Plumbing the pipeline serves for the pages' own use, never displayed.
const PLUMBING = new Set([
  "fx_to_usd", "fx_to_usd_history", "cpi_index", "cpi_index_nsa",
]);

// "Make it real" swaps a GDP panel to its real-terms series while the panel
// keeps its nominal key. These are reachable whenever that panel exists.
const TOGGLE_TARGETS = {
  gdp_real: ["gdp_level", "gdp_nominal"],
  gdp_real_annual: ["gdp_level", "gdp_level_annual", "gdp_nominal"],
  gdp_level_annual: ["gdp_level"],
};

// Inflation bases: the rule this gate enforces.
const BASIS_KEYS = new Set(["cpi_mom", "cpi_qoq", "cpih_mom"]);
const BASIS_LABEL = { cpi_mom: /Month on month/, cpih_mom: /Month on month/, cpi_qoq: /Quarter on quarter/ };

function load(page) {
  const vc = new VirtualConsole();
  vc.on("jsdomError", () => {});
  const dom = new JSDOM(fs.readFileSync(page, "utf8"), {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/" + page,
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
        return Promise.resolve({ ok: true, status: 200,
          json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))),
          text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener() {},
        removeListener() {}, addEventListener() {}, removeEventListener() {} }));
    },
  });
  return new Promise(res => dom.window.addEventListener("load", async () => {
    await new Promise(r => setTimeout(r, 900));
    res(dom);
  }, { once: true }));
}

function countryPages() {
  return fs.readdirSync(".").filter(f => f.endsWith(".html")).sort().map(f => {
    const s = fs.readFileSync(f, "utf8");
    if (!s.includes("chartPanel(")) return null;
    // A country page fetches its own series file (data.json, data-xx.json).
    // Shared pages such as dashboard.html also call chartPanel() and fetch
    // other JSON, so match the series-file shape exactly rather than any
    // data*.json -- otherwise the citation file is read as a country.
    const m = s.match(/fetch\("(data(?:-[a-z]{2})?\.json)"/);
    return m ? [f, m[1]] : null;
  }).filter(Boolean);
}

(async () => {
  const pages = countryPages();
  let failures = 0, reported = 0, pagesWithFindings = 0;
  const summary = { unreachable: 0, tileOnly: 0, chartOnly: 0 };

  for (const [page, dataFile] of pages) {
    let served;
    try { served = Object.keys(JSON.parse(fs.readFileSync(dataFile, "utf8")).series); }
    catch (e) { console.log(`FAIL  ${page}: cannot read ${dataFile}`); failures++; continue; }
    served = served.filter(k => !PLUMBING.has(k));

    const dom = await load(page);
    const d = dom.window.document;
    const tiles = new Set(), charts = new Set(), viaBasis = new Set();
    d.querySelectorAll(".stat").forEach(el => {
      if (el.dataset.key && el.dataset.key !== "null") tiles.add(el.dataset.key);
      el.querySelectorAll("[data-infokey]").forEach(b => tiles.add(b.dataset.infokey));
    });
    d.querySelectorAll(".panel").forEach(el => {
      if (el.dataset.key) charts.add(el.dataset.key);
      const g = el.querySelector(".basisselect");
      if (!g) return;
      const opts = [...g.querySelectorAll("button[data-basis]")].map(b => b.textContent.trim());
      for (const [k, re] of Object.entries(BASIS_LABEL)) {
        // a basis button reaches the series that panel's measure offers
        const measureMom = el.dataset.key === "cpih" ? "cpih_mom" : (k === "cpih_mom" ? null : k);
        if (measureMom === k && opts.some(o => re.test(o))) viaBasis.add(k);
      }
    });
    dom.window.close();

    const viaToggle = new Set(Object.entries(TOGGLE_TARGETS)
      .filter(([, hosts]) => hosts.some(h => charts.has(h)))
      .map(([k]) => k));
    const chartReach = new Set([...charts, ...viaBasis, ...viaToggle]);
    const reach = new Set([...tiles, ...chartReach]);

    const lines = [];
    for (const k of served) {
      const hasTile = tiles.has(k), hasChart = chartReach.has(k);
      if (BASIS_KEYS.has(k)) {
        if (!hasTile || !hasChart) {
          failures++;
          lines.push(`  FAIL  ${k.padEnd(22)} inflation basis without ${!hasTile && !hasChart ? "a tile or a chart" : !hasTile ? "a tile" : "a chart"}`);
        }
        continue;
      }
      if (!reach.has(k)) { summary.unreachable++; reported++; lines.push(`  gap   ${k.padEnd(22)} served, reachable nowhere`); }
      else if (hasTile && !hasChart && !viaToggle.has(k)) { summary.tileOnly++; reported++; lines.push(`  gap   ${k.padEnd(22)} tile, no chart`); }
      else if (hasChart && !hasTile && !viaToggle.has(k) && !viaBasis.has(k)) { summary.chartOnly++; reported++; lines.push(`  gap   ${k.padEnd(22)} chart, no tile`); }
    }
    if (lines.length) pagesWithFindings++;
    if (lines.length || VERBOSE) {
      console.log(`${page}  (${served.length} served${viaBasis.size ? ", basis: " + [...viaBasis].join("/") : ""})`);
      lines.forEach(l => console.log(l));
    }
  }

  console.log(`\n${pages.length} country pages loaded`);
  console.log(`  inflation-basis failures   ${failures}`);
  console.log(`  reported gaps              ${reported}  (unreachable ${summary.unreachable}, tile-only ${summary.tileOnly}, chart-only ${summary.chartOnly})`);
  console.log(`  pages with any finding     ${pagesWithFindings}`);
  process.exit(failures ? 1 : 0);
})();
