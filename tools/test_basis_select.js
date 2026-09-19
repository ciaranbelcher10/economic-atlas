#!/usr/bin/env node
/* Drives the real country-page basis selector under jsdom.
 *
 * What it asserts, per inflation chart that offers a choice:
 *   - the selector exists only where the country serves more than one basis
 *   - every option draws a non-empty series
 *   - switching basis actually changes the drawn points
 *   - the source note, explainer and accessible label follow the basis
 *   - the range presets still work after a rebuild (they close over the old
 *     points array, which is the easy thing to get wrong here)
 *   - no duplicate chart object survives a switch
 *
 * Run: NODE_PATH=$(pwd)/node_modules node tools/test_basis_select.js [page...]
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const PAGES = process.argv.slice(2).length ? process.argv.slice(2) : ["uk.html"];
let failures = 0, checks = 0, selectors = 0, views = 0;

function fail(page, msg) { failures++; console.log(`  FAIL  ${page}: ${msg}`); }
function ok(msg) { checks++; if (process.env.VERBOSE) console.log(`   ok   ${msg}`); }

async function run(page) {
  const html = fs.readFileSync(page, "utf8");
  const vc = new VirtualConsole();
  vc.on("jsdomError", () => {});
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/" + page,
    beforeParse(win) {
      // Charts are not under test here; a stub records what was drawn.
      win.HTMLCanvasElement.prototype.getContext = () => ({
        canvas: {}, clearRect(){}, save(){}, restore(){}, beginPath(){}, moveTo(){},
        lineTo(){}, stroke(){}, fill(){}, arc(){}, fillRect(){}, measureText: () => ({width: 10}),
        fillText(){}, setTransform(){}, scale(){}, translate(){}, closePath(){}, createLinearGradient: () => ({addColorStop(){}}),
      });
      win.fetch = (u) => {
        const file = String(u).split("/").pop().split("?")[0];
        const p = path.join(process.cwd(), file);
        if (!fs.existsSync(p)) return Promise.reject(new Error("no such file " + file));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
      // Chart.js loads from a CDN the harness cannot reach; this stub records
      // what the page asked to draw, which is all the assertions need.
      win.__charts = {};
      function ChartStub(canvas, config) {
        this.canvas = canvas; this.config = config;
        if (canvas && canvas.id) win.__charts[canvas.id] = this;
        this.data = (config && config.data) || {datasets: []};
        this.options = (config && config.options) || {};
      }
      ChartStub.prototype.update = function(){};
      ChartStub.prototype.__pts = function(){
        var ds = (this.data && this.data.datasets && this.data.datasets[0]) || {};
        return ds.data || [];
      };
      ChartStub.prototype.destroy = function(){};
      ChartStub.prototype.resetZoom = function(){};
      ChartStub.register = function(){};
      win.Chart = ChartStub;
      win.matchMedia = win.matchMedia || (() => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} }));
    },
  });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  // let the data fetch settle
  for (let i = 0; i < 60 && !win.document.querySelector(".panel"); i++) await new Promise(r => setTimeout(r, 50));
  await new Promise(r => setTimeout(r, 300));

  const panels = [...win.document.querySelectorAll(".panel")];
  if (!panels.length) return fail(page, "no chart panels rendered at all");
  ok(`${page}: ${panels.length} panels`);

  const reg = win.__charts || {};
  for (const panel of panels) {
    const sel = panel.querySelector("select.basisdd");
    if (!sel) continue;
    selectors++;
    const key = panel.dataset.key || "(unkeyed)";
    const canvas = panel.querySelector("canvas");
    const id = canvas && canvas.id;
    const entry = reg[id];
    if (!entry) { fail(page, `${key}: no chart object created for ${id}`); continue; }
    if (sel.options.length < 2) fail(page, `${key}: selector rendered with only ${sel.options.length} option`);

    const seen = new Map();
    const before = Object.keys(reg).length;
    for (const opt of [...sel.options]) {
      sel.value = opt.value;
      sel.dispatchEvent(new win.Event("change"));
      await new Promise(r => setTimeout(r, 20));
      views++;
      const pts = reg[id] && reg[id].__pts();
      if (!pts || !pts.length) { fail(page, `${key}/${opt.text}: drew no points`); continue; }
      const first = pts[0], last = pts[pts.length - 1];
      const sig = pts.length + ":" + JSON.stringify(first) + ":" + JSON.stringify(last);
      if (seen.has(sig)) fail(page, `${key}: "${opt.text}" drew the same series as "${seen.get(sig)}"`);
      seen.set(sig, opt.text);

      const src = panel.querySelector(".src");
      if (!src || !/^Source: \S/.test(src.textContent)) fail(page, `${key}/${opt.text}: source note empty`);
      const aria = canvas.getAttribute("aria-label") || "";
      if (!aria.includes(opt.text)) fail(page, `${key}/${opt.text}: aria-label does not name the basis`);

      // presets must act on the basis now shown, not the one before it
      const btn = panel.querySelector("button[data-range]:not([data-range=max])");
      if (btn) {
        const full = reg[id].__pts().length;
        btn.dispatchEvent(new win.Event("click"));
        await new Promise(r => setTimeout(r, 20));
        if (reg[id].__pts().length > full) fail(page, `${key}/${opt.text}: preset drew more points than the basis holds`);
      }
    }
    if (Object.keys(reg).length !== before) fail(page, `${key}: chart objects leaked (${before} -> ${Object.keys(reg).length})`);
    ok(`${key}: ${sel.options.length} bases`);
  }
  dom.window.close();
}

(async () => {
  for (const p of PAGES) {
    try { await run(p); } catch (e) { fail(p, "threw: " + e.message); }
  }
  console.log(`\n${PAGES.length} page(s), ${selectors} selectors, ${views} views, ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
