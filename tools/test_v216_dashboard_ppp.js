#!/usr/bin/env node
/* v2.0.16: Dashboard Convert to PPP. Run from the repo root: NODE_PATH=/tmp/node_modules node tools/test_v216_dashboard_ppp.js */
const fs = require("fs"), path = require("path");
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole } = require(NM + "jsdom");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const store = {}, errs = [];
(async () => {
  let html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, "dashboard.html"), "utf8"), ROOT);
  html = html.replace("function pppSuffix(unit){", "window.__dE = function(js){ return eval(js); };\nfunction pppSuffix(unit){");
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if(!/supabase|EATLAS_PREFS|Not implemented|\bd3\b|is not defined: undefined/i.test(m)) errs.push(m); });
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, url: "https://theeconomicatlas.com/dashboard.html",
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get(){ return function(){ return { addColorStop(){} }; }; } });
      function C(c, cfg){ this.data = (cfg && cfg.data) || { datasets: [] }; this.options = {}; } C.prototype.update = function(){}; C.prototype.destroy = function(){}; C.prototype.resetZoom = function(){}; C.register = function(){}; win.Chart = C;
      Object.defineProperty(win, "localStorage", { configurable: true, value: { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; }, clear(){}, key: () => null, get length(){ return 0; } } });
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]); if(!fs.existsSync(p)) return Promise.reject(new Error("no file"));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) }); };
      win.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
    } });
  const win = dom.window, d = win.document;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for(let i = 0; i < 100 && !(win.REGISTRY && Object.keys(win.REGISTRY).length); i++) await new Promise(r => setTimeout(r, 50));
  await new Promise(r => setTimeout(r, 500));
  const E = js => win.__dE(js);
  E(`REGISTRY["UK"].ppp = {points: [["2023", 0.672], ["2024", 0.675], ["2025", 0.68]]};`);
  win.EATLAS_DASH.ensurePinned("UK::gdp_level"); win.EATLAS_DASH.ensurePinned("UK::cpi");
  await new Promise(r => setTimeout(r, 200));
  const tile = () => [...d.querySelectorAll(".tile")].find(t => t.dataset.id === "UK::gdp_level");
  const ppp = d.getElementById("pppBtn"), usd = d.getElementById("dollariseBtn");
  ok(ppp && ppp.parentNode.classList.contains("mtoggle-pair") && usd.parentNode === ppp.parentNode, "USD$ and PPP joined");
  ppp.click(); await new Promise(r => setTimeout(r, 100));
  ok(ppp.getAttribute("aria-pressed") === "true", "PPP on");
  ok(/\(PPP\)/.test(tile().textContent) && /Int\$/.test(tile().querySelector(".value").textContent), "GDP tile in international dollars: " + tile().querySelector(".value").textContent);
  ok(!/Int\$0\b/.test(tile().querySelector(".value").textContent) && /2025/.test(tile().textContent), "latest period without a factor: tile shows the latest year that has one (" + tile().textContent.replace(/\s+/g, " ").slice(0, 80) + ")");
  ok(tile().classList.contains("fx-dollar") && ppp.classList.contains("fx-dollar"), "PPP uses Convert to USD$'s blue (tile and button)");
  const cpi = [...d.querySelectorAll(".tile")].find(t => t.dataset.id === "UK::cpi");
  ok(!/Int\$/.test(cpi.textContent) && !cpi.classList.contains("fx-dollar"), "CPI tile unchanged");
  usd.click(); await new Promise(r => setTimeout(r, 100));
  ok(ppp.getAttribute("aria-pressed") === "false" && usd.getAttribute("aria-pressed") === "true", "USD$ turns PPP off");
  ppp.click(); await new Promise(r => setTimeout(r, 100));
  ok(usd.getAttribute("aria-pressed") === "false", "PPP turns USD$ off");
  d.getElementById("perCapitaBtn").click(); await new Promise(r => setTimeout(r, 100));
  const v = tile().querySelector(".value").textContent;
  ok(/^.*Int\$\d{2},\d{3}/.test(v.replace(/\s/g, "")) && ppp.classList.contains("fx-dollar-pc"), "PPP + per capita: Int$ per person, purple: " + v);
  ok(store.eatlas_dashboard_ppp === "1", "PPP remembered");
  win.EATLAS_DASH.ensurePinned("Eurozone::gdp_level"); await new Promise(r => setTimeout(r, 200));
  const ez = [...d.querySelectorAll(".tile")].find(t => t.dataset.id === "Eurozone::gdp_level");
  ok(ez && /€/.test(ez.querySelector(".value").textContent) && /PPP not available/.test(ez.textContent), "euro area (no factors): as published, labelled; never Int$0: " + (ez && ez.querySelector(".value").textContent));
  ok(!errs.length, "no page errors: " + errs.join(" | "));
  console.log(`test_v216_dashboard_ppp: ${checks} checks, ${failures} failures`); process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
