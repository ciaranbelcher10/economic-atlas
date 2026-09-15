#!/usr/bin/env node
/*
 * Settled regression gate: actually execute each country page's sampleData()
 * under a stubbed DOM and assert every series is non-empty and every point
 * numeric and finite. node --check is blind to runtime errors like a deleted
 * variable initialisation, which is the failure this catches.
 *
 * The page blocks are "use strict", so function declarations do not leak to
 * globalThis; sampleData has to be captured from inside the eval scope.
 * sampleData() returns {updated, sample, series:{...}}, not a bare series map.
 */
const fs = require("fs");
const path = require("path");

const REPO = process.env.ATLAS_REPO || path.resolve(__dirname, "..");
const PAGES = fs.readdirSync(REPO)
  .filter(f => f.endsWith(".html"))
  .filter(f => fs.readFileSync(path.join(REPO, f), "utf8").includes("function sampleData"));

function stubs() {
  const el = () => ({
    style: {}, classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    appendChild() {}, removeChild() {}, remove() {}, setAttribute() {}, removeAttribute() {}, getAttribute() { return null; },
    disabled: false, value: "", checked: false, focus() {}, blur() {}, click() {},
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
    getContext() { return {}; }, textContent: "", innerHTML: "", dataset: {}, children: [],
  });
  global.window = global;
  global.document = {
    getElementById: () => el(), querySelector: () => null, querySelectorAll: () => [],
    createElement: () => el(), addEventListener() {}, body: el(), head: el(),
    documentElement: { style: { setProperty() {} }, classList: { add() {}, remove() {}, contains() { return false; } }, getAttribute() { return null; } },
  };
  global.getComputedStyle = () => ({ getPropertyValue: () => "#000", fontFamily: "sans-serif" });
  global.location = { href: "https://theeconomicatlas.com/", pathname: "/", search: "", hash: "" };
  global.navigator = { userAgent: "node", language: "en-GB" };
  global.localStorage = { _d: {}, getItem(k) { return this._d[k] ?? null; }, setItem(k, v) { this._d[k] = String(v); }, removeItem(k) { delete this._d[k]; } };
  global.sessionStorage = global.localStorage;
  function Chart() {}
  Chart.register = function () {};
  Chart.defaults = { font: {}, plugins: { legend: {} }, scale: { grid: {} } };
  global.Chart = Chart;
  global.matchMedia = () => ({ matches: false, addEventListener() {}, addListener() {} });
  global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });
  global.requestAnimationFrame = (f) => setTimeout(f, 0);
}

let pagesOk = 0, pagesFail = 0, seriesTotal = 0, pointsTotal = 0;
const failures = [];

for (const page of PAGES.sort()) {
  const html = fs.readFileSync(path.join(REPO, page), "utf8");
  const block = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    .map(m => m[1]).find(b => b.includes("function sampleData"));
  if (!block) { failures.push([page, "no sampleData block found"]); pagesFail++; continue; }
  stubs();
  try {
    // capture sampleData from inside the eval scope: "use strict" keeps it local
    const fn = eval(block + "\n;sampleData");
    const out = fn();
    if (!out || typeof out !== "object" || !out.series) throw new Error("no .series on return value");
    let n = 0, pts = 0;
    for (const [k, v] of Object.entries(out.series)) {
      const arr = Array.isArray(v) ? v : (v && v.points);
      if (!Array.isArray(arr) || arr.length === 0) throw new Error(`series ${k} is empty`);
      for (const p of arr) {
        const val = Array.isArray(p) ? p[1] : (p && p.v);
        if (val !== null && (typeof val !== "number" || !isFinite(val))) {
          throw new Error(`series ${k} has a non-finite point: ${JSON.stringify(p)}`);
        }
        pts++;
      }
      n++;
    }
    seriesTotal += n; pointsTotal += pts; pagesOk++;
  } catch (e) {
    failures.push([page, e.message]); pagesFail++;
  }
}

console.log(`  pages with a sampleData block: ${PAGES.length}`);
console.log(`  executed clean:                ${pagesOk}`);
console.log(`  failed:                        ${pagesFail}`);
console.log(`  series asserted non-empty:     ${seriesTotal}`);
console.log(`  points asserted finite:        ${pointsTotal}`);
for (const [p, m] of failures) console.log(`    FAIL ${p}: ${m}`);
process.exit(pagesFail === 0 ? 0 : 1);
