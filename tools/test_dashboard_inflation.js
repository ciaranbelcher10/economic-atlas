#!/usr/bin/env node
/* Drives dashboard.html's real inflation tile controls under jsdom.
 *
 * Asserts:
 *   - a tile for a country with one measure and one basis shows no control
 *   - a tile for a multi-basis country shows measure and/or basis pills,
 *     offering only what that country serves
 *   - choosing a basis changes the value the tile shows
 *   - the choice survives a renderDash() redraw
 *   - the choice is persisted, so it survives a reload
 *   - the tile's citation follows the chosen basis rather than the tile key
 *   - the tile's identity (its pinned id) does not change, so pinning and
 *     ordering are unaffected
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_dashboard_inflation.js
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
  const html = fs.readFileSync("dashboard.html", "utf8");
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

const tileOf = (win, id) => [...win.document.querySelectorAll(".tile")]
  .filter(t => (t.dataset && t.dataset.id) === id)[0];

(async () => {
  let dom = boot();
  let win = await ready(dom);

  // The page's script is closed over; EATLAS_DASH.ensurePinned is its own
  // public seam for pinning (it pins, saves and re-renders atomically), so
  // the test uses that rather than reaching into the closure.
  if (!win.EATLAS_DASH || typeof win.EATLAS_DASH.ensurePinned !== "function") {
    fail("dashboard did not expose EATLAS_DASH.ensurePinned; cannot drive tiles");
    console.log(`\n${checks} checks, ${failures} failures`);
    process.exit(1);
  }
  const add = (id) => win.EATLAS_DASH.ensurePinned(id);
  add("UK::cpi"); add("Japan::cpi");
  await new Promise(r => setTimeout(r, 300));

  const ukTile = tileOf(win, "UK::cpi");
  const jpTile = tileOf(win, "Japan::cpi");
  if (!ukTile) fail("UK::cpi tile did not render");
  if (!jpTile) fail("Japan::cpi tile did not render");
  if (!ukTile || !jpTile) { console.log(`\n${checks} checks, ${failures} failures`); process.exit(1); }

  // --- controls offered only where there is a choice ---------------------
  const jpGroup = jpTile.querySelector(".basisselect");
  if (jpGroup) fail("Japan tile offers a control despite serving one basis only");
  else ok("Japan tile offers no control, as it serves year on year only");

  const ukGroup = ukTile.querySelector(".basisselect");
  if (!ukGroup) { fail("UK tile offers no measure/basis control"); }
  else {
    const measures = [...ukGroup.querySelectorAll("button[data-measure]")].map(b => b.textContent);
    const bases = [...ukGroup.querySelectorAll("button[data-basis]")].map(b => b.textContent);
    eq(measures.join(","), "Headline CPI,CPIH", "UK measures offered on the tile");
    eq(bases.join(","), "Year on year,Month on month", "UK bases offered on the tile");

    const valueBefore = ukTile.querySelector(".value").textContent;
    const idBefore = ukTile.dataset.id;

    // --- choosing a basis changes the value -----------------------------
    const mom = [...ukGroup.querySelectorAll("button[data-basis]")]
      .filter(b => /Month on month/.test(b.textContent))[0];
    mom.dispatchEvent(new win.Event("click", { bubbles: true }));
    await new Promise(r => setTimeout(r, 250));

    const after = tileOf(win, "UK::cpi");
    if (!after) fail("tile identity changed after choosing a basis (pinning would break)");
    else {
      eq(after.dataset.id, idBefore, "tile id unchanged by the choice");
      const valueAfter = after.querySelector(".value").textContent;
      if (valueAfter === valueBefore) fail("tile value did not change with the basis");
      else ok(`tile value followed the basis: ${valueBefore.trim()} -> ${valueAfter.trim()}`);

      const src = after.querySelector(".chartsrc");
      if (src && /D7OE|previous month|month/i.test(src.textContent)) ok("citation followed the basis");
      else fail("citation still names the year-on-year series: " + (src ? src.textContent.slice(0, 90) : "none"));

      const activeBasis = after.querySelector(".basisselect button[data-basis].active");
      if (activeBasis && /Month on month/.test(activeBasis.textContent)) ok("the chosen basis is shown as active");
      else fail("active state does not reflect the choice");
    }

    // --- survives a redraw ----------------------------------------------
    add("UK::cpi");   // idempotent; forces a fresh render
    await new Promise(r => setTimeout(r, 250));
    const redrawn = tileOf(win, "UK::cpi");
    const activeAfterRedraw = redrawn && redrawn.querySelector(".basisselect button[data-basis].active");
    if (activeAfterRedraw && /Month on month/.test(activeAfterRedraw.textContent))
      ok("choice survived renderDash()");
    else fail("choice was lost on renderDash()");
  }

  // --- survives a reload -------------------------------------------------
  const persisted = store["eatlas_tile_measure_v1"];
  if (!persisted || !/cpi_mom/.test(persisted)) fail("choice was not persisted: " + persisted);
  else ok("choice persisted to storage");

  dom.window.close();
  dom = boot();
  win = await ready(dom);
  add("UK::cpi");
  await new Promise(r => setTimeout(r, 300));
  const reloaded = tileOf(win, "UK::cpi");
  const activeAfterReload = reloaded && reloaded.querySelector(".basisselect button[data-basis].active");
  if (activeAfterReload && /Month on month/.test(activeAfterReload.textContent))
    ok("choice survived a reload");
  else fail("choice was lost on reload");

  for (const e of bootErrors) fail("uncaught page error: " + e);
  if (!bootErrors.length) ok("page ran with no uncaught errors");
  console.log(`\n${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
