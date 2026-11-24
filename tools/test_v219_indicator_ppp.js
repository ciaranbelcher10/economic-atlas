#!/usr/bin/env node
/* v2.0.19: Convert to PPP on the GDP-family indicator pages (generated pages, live data files).
 * Run from the repo root after generate_indicator_pages.py: NODE_PATH=/tmp/node_modules node tools/test_v219_indicator_ppp.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole, ResourceLoader } = require(NM + "jsdom");
let checks = 0, failures = 0; const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const wait = ms => new Promise(r => setTimeout(r, ms));
class Loader extends ResourceLoader {
  fetch(url){
    const b = url.split("/").pop().split("?")[0];
    if(b === "chart.umd.min.js") return Promise.resolve(fs.readFileSync(NM + "chart.js/dist/chart.umd.js"));
    if(/^https:\/\/example\.test\//.test(url)){ const f = path.join(ROOT, decodeURIComponent(new URL(url).pathname)); if(fs.existsSync(f)) return Promise.resolve(fs.readFileSync(f)); }
    return Promise.resolve(Buffer.from(""));
  }
}
async function open(p){
  const vc = new VirtualConsole(), errs = [];
  vc.on("jsdomError", e => { const m = String(e.message || e).split("\n")[0]; if(!/supabase|Not implemented|EATLAS_PREFS|d3|topojson/i.test(m)) errs.push(m); });
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, p), "utf8"), { runScripts: "dangerously", resources: new Loader(), url: "https://example.test/" + p, virtualConsole: vc, pretendToBeVisual: true,
    beforeParse(w){
      w.fetch = u => { const f = path.join(ROOT, path.posix.join(path.posix.dirname("/" + p), String(u).split("?")[0]));
        if(!fs.existsSync(f)) return Promise.resolve({ ok: false, status: 404, json: () => Promise.reject(new Error("404")) });
        const t = fs.readFileSync(f, "utf8"); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)), text: () => Promise.resolve(t) }); };
      w.matchMedia = q => ({ matches: false, media: q, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      w.scrollTo = () => {}; w.ResizeObserver = class { observe(){} unobserve(){} disconnect(){} };
      w.HTMLCanvasElement.prototype.getContext = function(){ const cv = this; return new Proxy({}, { get(t, k){ if(k === "canvas") return cv; if(k === "measureText") return s => ({ width: String(s).length * 6 }); if(/create(Linear|Radial)Gradient|createPattern/.test(k)) return () => ({ addColorStop(){} }); if(k === "getImageData") return () => ({ data: [] }); return () => {}; } }); };
    } });
  await new Promise(r => dom.window.addEventListener("load", r, { once: true })); await wait(400);
  return { d: dom.window.document, errs };
}
const fig = d => (d.getElementById("indFigure") || {}).textContent || "";
(async () => {
  { const { d, errs } = await open("indicators/uk-gdp.html");
    const ppp = d.getElementById("indTogglePpp"), usd = d.getElementById("indToggleDollar");
    ok(ppp && usd && ppp.parentNode.classList.contains("mtoggle-pair") && usd.parentNode === ppp.parentNode, "uk-gdp: USD$ and PPP joined");
    const before = fig(d); ppp.click(); await wait(50);
    const f = fig(d);
    ok(/^Int\$4\.\dtn/.test(f.trim()), "uk-gdp: figure in Int$ (" + before + " -> " + f + ")");
    ok(/PPP: each value converted/.test(d.getElementById("indPppNote").textContent) && !d.getElementById("indPppNote").hidden, "uk-gdp: PPP note shown");
    usd.click(); await wait(50);
    ok(ppp.getAttribute("aria-pressed") === "false" && /^\$/.test(fig(d).trim()), "uk-gdp: USD$ turns PPP off (" + fig(d) + ")");
    ppp.click(); await wait(50);
    ok(usd.getAttribute("aria-pressed") === "false", "uk-gdp: PPP turns USD$ off");
    d.getElementById("indTogglePc").click(); await wait(50);
    ok(/^Int\$6\d,\d{3}/.test(fig(d).trim()), "uk-gdp: PPP + per capita (" + fig(d) + ")");
    d.getElementById("indTogglePc").click(); d.getElementById("indToggleReal").click(); await wait(50);
    ok(/^Int\$4\.\dtn/.test(fig(d).trim()) && /constant 20\d\d international dollars/.test(d.getElementById("indPppNote").textContent), "uk-gdp: real + PPP (" + fig(d) + ")");
    ok(!errs.length, "uk-gdp: no page errors: " + errs.join(" | ")); }
  for(const [p, re] of [["indicators/uk-gdp-per-capita.html", /^Int\$6\d\.\dk/], ["indicators/uk-real-gdp.html", /^Int\$4\.\dtn/], ["indicators/us-gdp.html", /^Int\$3\d\.\dtn/]]){
    const { d, errs } = await open(p);
    const ppp = d.getElementById("indTogglePpp");
    ok(!!ppp, p + ": has Convert to PPP");
    if(!ppp) continue;
    const nat = fig(d); ppp.click(); await wait(50);
    ok(re.test(fig(d).trim()), p + ": " + nat + " -> " + fig(d));
    ok(!errs.length, p + ": no page errors: " + errs.join(" | "));
  }
  for(const p of ["indicators/eurozone-gdp.html", "indicators/taiwan-gdp.html", "indicators/uk-inflation-rate.html", "indicators/uk-exports.html"]){
    if(!fs.existsSync(path.join(ROOT, p))) continue;
    ok(!/indTogglePpp/.test(fs.readFileSync(path.join(ROOT, p), "utf8")), p + ": no PPP switch (no checked factor, or not GDP)");
  }
  console.log(`test_v219_indicator_ppp: ${checks} checks, ${failures} failures`); process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
