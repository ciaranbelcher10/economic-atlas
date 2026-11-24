#!/usr/bin/env node
/* v2.0.16: Chartmaker Convert to PPP. NODE_PATH=/tmp/node_modules node tools/test_v216_chartmaker_ppp.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole } = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
(async () => {
  let html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8"), ROOT);
  html = html.replace('var chartType = "line";', 'var chartType = "line"; window.__cmEval = function(js){ return eval(js); };');
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: new VirtualConsole(),
    url: "https://theeconomicatlas.com/chartmaker.html",
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => ({ font: "11px sans-serif", measureText(t){ return { width: String(t).length * 6 }; }, fillText(){}, clearRect(){}, scale(){}, setTransform(){} });
      win.Chart = function(){}; win.Chart.register = function(){};
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]);
        if(!fs.existsSync(p)) return Promise.reject(new Error("no file"));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) }); };
      win.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.EATLAS_PREFS = { isLoggedIn: () => true, registerBanner(){}, onLogin(){} };
    } });
  const win = dom.window, d = win.document;
  await new Promise(r => win.addEventListener("load", r, { once: true })); await new Promise(r => setTimeout(r, 1500));
  const run = js => win.__cmEval(js);
  // fixture factors (the sandbox cannot reach the World Bank)
  run(`REGISTRY["UK"].ppp = {points: [["2023", 0.672], ["2024", 0.675]]};
       REGISTRY["US"].ppp = {points: [["2023", 1], ["2024", 1]]};
       if(REGISTRY["Taiwan"]) delete REGISTRY["Taiwan"].ppp;
       series.length = 0; addSeries("UK", "gdp_level", false, true); addSeries("US", "gdp_level", false, true); renderChart();`);
  const ppp = d.getElementById("pppToggle"), usd = d.getElementById("dollariseToggle");
  ok(ppp && ppp.closest(".mtoggle-pair") && usd.closest(".mtoggle-pair") === ppp.closest(".mtoggle-pair"), "USD$ and PPP sit together as a pair");
  ok(!ppp.disabled, "PPP available for GDP");
  ppp.click();
  ok(run("TOGGLE_STATE.ppp") === true && ppp.getAttribute("aria-pressed") === "true", "PPP on");
  const uk = run(`JSON.stringify(series.filter(function(s){return s.country==="UK"})[0].display)`);
  const D = JSON.parse(uk);
  ok(D.unit === "Int$m", "UK in Int$m (" + D.unit + ")");
  const raw = run(`(function(){var s=series.filter(function(s){return s.country==="UK"})[0];var p=s.origRawPoints.filter(function(p){return p.x==="2024-Q1"})[0];return p.y})()`);
  const conv = D.pts.find(p => p.x === "2024-Q1");
  ok(conv && Math.abs(conv.y - raw / 0.675) < 1e-6, "UK 2024-Q1 divided by the 2024 factor");
  ok(!D.pts.some(p => /^2025/.test(p.x)), "2025 left out (no factor)");
  const note = d.getElementById("mtoggleNote").textContent;
  ok(/PPP: each value converted at that year/.test(note) && /2025/.test(note), "note explains PPP and names 2025: " + note.slice(0, 200));
  ok(!/market exchange rates, not purchasing power parity/.test(note), "no market-rate line while PPP is on");
  usd.click();
  ok(run("TOGGLE_STATE.ppp") === false && ppp.getAttribute("aria-pressed") === "false", "Convert to USD$ turns PPP off");
  ppp.click();
  ok(run("userDollarPreference") === false, "PPP turns Convert to USD$ off");
  const yt = run(`syncAutoYAxisTitle(); var f = buildFmtY(); JSON.stringify([style.yAxisTitle, f(4300000)])`);
  console.log("  info: axis title and tick:", yt);
  ok(/Int\$/.test(yt), "axis shows international dollars");
  d.getElementById("percapToggle").click();
  const P = JSON.parse(run(`JSON.stringify(series.filter(function(s){return s.country==="UK"})[0].display)`));
  ok(P.unit === "Int$" && P.pts.length && P.pts[P.pts.length-1].y > 40000 && P.pts[P.pts.length-1].y < 80000, "PPP + per capita: Int$ per person, plausible (" + JSON.stringify(P.pts.slice(-1)) + ")");
  d.getElementById("percapToggle").click();
  d.getElementById("makeRealToggle").click();
  const R = JSON.parse(run(`JSON.stringify(series.filter(function(s){return s.country==="UK"})[0].display)`));
  ok(R.realView && (R.ppp ? (R.pppNo || /Int\$m/.test(R.unit)) : false), "real + PPP: anchored or named as unavailable (" + R.unit + ", anchor " + R.pppAnchor + ")");
  d.getElementById("makeRealToggle").click();
  run(`addSeries("Taiwan", "gdp_level", false, true); refreshToggleState();`);
  ok(/PPP not available for Taiwan/.test(d.getElementById("mtoggleNote").textContent), "an economy without PPP is named");
  ppp.click();
  run(`series.length = 0; addSeries("UK", "cpi", false, true); refreshToggleState();`);
  ok(ppp.disabled, "PPP greyed out for CPI (when off, as Per capita)");
  console.log(`test_v216_chartmaker_ppp: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
