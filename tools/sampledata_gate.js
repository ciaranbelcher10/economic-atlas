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

function findRepo(start) {
  let d = start;
  while (true) {
    if (fs.existsSync(path.join(d, "compare.html")) &&
        fs.existsSync(path.join(d, "data-metric-sources.json"))) {
      return d;
    }
    const parent = path.dirname(d);
    if (parent === d) {
      throw new Error(
        "could not locate the economic-atlas clone from " + start +
        "; set ATLAS_REPO to the clone root");
    }
    d = parent;
  }
}

const REPO = process.env.ATLAS_REPO || findRepo(__dirname);
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

let pagesOk = 0, pagesFail = 0, seriesTotal = 0, pointsTotal = 0, nullTotal = 0;
const failures = [];
const fixtureSeries = new Map();

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
    let n = 0, pts = 0, nulls = 0;
    for (const [k, v] of Object.entries(out.series)) {
      const arr = Array.isArray(v) ? v : (v && v.points);
      if (!Array.isArray(arr) || arr.length === 0) throw new Error(`series ${k} is empty`);
      for (const p of arr) {
        const val = Array.isArray(p) ? p[1] : (p && p.v);
        // null is a legitimate gap in a series, so it does not fail the gate,
        // but it is NOT an asserted-finite point and must not be counted as
        // one: that inflated the headline number with values never checked.
        if (val === null) { nulls++; continue; }
        if (typeof val !== "number" || !isFinite(val)) {
          throw new Error(`series ${k} has a non-finite point: ${JSON.stringify(p)}`);
        }
        pts++;
      }
      n++;
    }
    fixtureSeries.set(page, new Set(Object.keys(out.series)));
    seriesTotal += n; pointsTotal += pts; nullTotal += nulls; pagesOk++;
  } catch (e) {
    failures.push([page, e.message]); pagesFail++;
  }
}

// sampleData() is the offline fixture, NOT the data the page serves. A gate
// that only runs the fixture can report a clean pass while a served series is
// absent from it entirely and therefore never asserted by anything. Compare
// the two key sets and say plainly how many served series this gate does not
// cover.
let bothCount = 0, fixtureOnly = [], servedOnly = [];
for (const [page, keys] of fixtureSeries) {
  const html = fs.readFileSync(path.join(REPO, page), "utf8");
  const m = html.match(/["'](data(?:-[a-z]{2,3})?\.json)["']/);
  if (!m) continue;
  const dataPath = path.join(REPO, m[1]);
  if (!fs.existsSync(dataPath)) continue;
  let served;
  try {
    served = JSON.parse(fs.readFileSync(dataPath, "utf8")).series || {};
  } catch { continue; }
  for (const k of Object.keys(served)) {
    if (keys.has(k)) bothCount++;
    else servedOnly.push(`${page} ${k}`);
  }
  for (const k of keys) if (!(k in served)) fixtureOnly.push(`${page} ${k}`);
}

console.log(`  pages with a sampleData block: ${PAGES.length}`);
console.log(`  executed clean:                ${pagesOk}`);
console.log(`  failed:                        ${pagesFail}`);
console.log(`  series asserted non-empty:     ${seriesTotal}`);
console.log(`  points asserted finite:        ${pointsTotal}`);
console.log(`  null points (gaps, not asserted): ${nullTotal}`);
console.log(`  fixture series also served:    ${bothCount}`);
console.log(`  fixture-only (no served match): ${fixtureOnly.length}`);
console.log(`  SERVED BUT NOT ASSERTED HERE:  ${servedOnly.length}`);
for (const s of servedOnly) console.log(`    uncovered: ${s}`);
for (const [p, m] of failures) console.log(`    FAIL ${p}: ${m}`);
if (PAGES.length === 0) {
  console.log("    FAIL no pages with a sampleData block were found; "
              + "REPO resolved to " + REPO);
  process.exit(1);
}
process.exit(pagesFail === 0 ? 0 : 1);
