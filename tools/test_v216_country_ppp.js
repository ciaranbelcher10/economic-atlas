#!/usr/bin/env node
/* v2.0.16: Convert to PPP on the country pages (real page, real data, fixture PPP factors).
 * NODE_PATH=/tmp/node_modules node tools/test_v216_country_ppp.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole } = require(NM + "jsdom");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
async function boot(file){
  let html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, file), "utf8"), ROOT);
  html = html.replace("function pppPoints(){", "window.__pE = function(js){ return eval(js); };\nfunction pppPoints(){");
  const errs = [], vc = new VirtualConsole();
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if(!/supabase|EATLAS|Not implemented|\bd3\b|topojson|Chart|is not defined: undefined/i.test(m)) errs.push(m); });
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, url: "https://theeconomicatlas.com/" + file,
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get(){ return function(){ return { addColorStop(){} }; }; } });
      function C(c, cfg){ this.data = (cfg && cfg.data) || { datasets: [] }; this.options = (cfg && cfg.options) || {}; } C.prototype.update = function(){}; C.prototype.destroy = function(){}; C.prototype.resetZoom = function(){}; C.register = function(){}; win.Chart = C;
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]); if(!fs.existsSync(p)) return Promise.reject(new Error("no file"));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) }); };
      win.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.scrollTo = () => {}; win.IntersectionObserver = class { observe(){} unobserve(){} disconnect(){} }; win.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
    } });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for(let i = 0; i < 100 && !win.__pE("typeof PAGE_DATA !== 'undefined' && PAGE_DATA && PAGE_DATA.series"); i++) await wait(50);
  await wait(300);
  return { win, d: win.document, E: js => win.__pE(js), errs };
}
const tileVal = (d, key) => { const t = d.querySelector('.stat[data-key="' + key + '"]'); return t ? t.textContent.replace(/\s+/g, " ") : ""; };
(async () => {
  { // UK: fixture factors
    const { d, E, errs } = await boot("uk.html");
    E(`PAGE_DATA.series.ppp = {points: [["2022", 0.67], ["2023", 0.672], ["2024", 0.675]]}; rerender();`);
    const ppp = d.getElementById("togglePpp"), usd = d.getElementById("toggleDollar");
    ok(ppp && ppp.parentNode.classList.contains("mtoggle-pair") && usd.parentNode === ppp.parentNode, "uk: USD$ and PPP joined");
    ok(!ppp.disabled, "uk: PPP available");
    ppp.click(); await wait(50);
    ok(E("TOGGLE_STATE.ppp") === true, "uk: PPP on");
    ok(/Int\$/.test(tileVal(d, "gdp_level")), "uk: GDP tile in Int$: " + tileVal(d, "gdp_level").slice(0, 120));
    ok(!/Int\$/.test(tileVal(d, "cpi")), "uk: CPI untouched");
    const note = d.getElementById("mtoggleNote").textContent;
    ok(/PPP: each value converted/.test(note) && /not yet published/.test(note), "uk: note: " + note);
    ok(d.querySelector('.stat[data-key="gdp_level"]').classList.contains("fx-dollar") && ppp.classList.contains("fx-dollar"), "uk: Convert to USD$'s blue on the tile and the PPP button");
    ok(!d.querySelector('.stat[data-key="exports"]') || !d.querySelector('.stat[data-key="exports"]').classList.contains("fx-dollar"), "uk: exports not highlighted");
    usd.click(); await wait(50);
    ok(!E("TOGGLE_STATE.ppp") && E("TOGGLE_STATE.dollar") && ppp.getAttribute("aria-pressed") === "false", "uk: USD$ turns PPP off");
    ppp.click(); await wait(50);
    ok(!E("TOGGLE_STATE.dollar") && usd.getAttribute("aria-pressed") === "false", "uk: PPP turns USD$ off");
    d.getElementById("toggleCapita").click(); await wait(50);
    const pc = tileVal(d, "gdp_level");
    ok(/Int\$\s?\d{2},\d{3}/.test(pc) && ppp.classList.contains("fx-dollar-pc"), "uk: PPP + per capita, purple: " + pc.slice(0, 120));
    d.getElementById("toggleCapita").click(); d.getElementById("toggleReal").click(); await wait(50);
    const rn = d.getElementById("mtoggleNote").textContent;
    ok(/real GDP in constant \d{4} international dollars|not available for real GDP/.test(rn), "uk: real + PPP note: " + rn);
    ok(ppp.classList.contains("fx-both"), "uk: real + PPP green, as real + USD$");
    ok(!errs.length, "uk: no page errors: " + errs.join(" | "));
  }
  { // Taiwan: no PPP series (no World Bank figures)
    const { d, E, errs } = await boot("taiwan.html");
    const ppp = d.getElementById("togglePpp");
    ok(ppp && ppp.disabled && /not available/.test(ppp.title), "taiwan: PPP greyed out without factors");
    ok(!errs.length, "taiwan: no page errors: " + errs.join(" | "));
  }
  { // US: USD$ is off (already dollars) but PPP works; factor 1 gives the same numbers
    const { d, E, errs } = await boot("us.html");
    E(`PAGE_DATA.series.ppp = {points: [["2023", 1], ["2024", 1]]}; rerender();`);
    const before = tileVal(d, "gdp_per_capita");
    d.getElementById("togglePpp").click(); await wait(50);
    ok(!d.getElementById("togglePpp").disabled && /Int\$/.test(tileVal(d, "gdp_per_capita")), "us: PPP available, per person in Int$: " + tileVal(d, "gdp_per_capita").slice(0, 80) + " (was " + before.slice(0, 60) + ")");
    ok(!errs.length, "us: no page errors: " + errs.join(" | "));
  }
  console.log(`test_v216_country_ppp: ${checks} checks, ${failures} failures`); process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
