#!/usr/bin/env node
/* v2.0.3: the Bar colours choice above 10 countries on one measure (One colour or Country colours).
 * Built on the v2.0.2 harness. Original header: ChartMaker bar chart of 10-year bond yields across every country, and its CSV.
 * First label inside the canvas, period line clear of rotated labels, "Latest month, to ..." when bars
 * carry earlier periods, one colour above 10 countries, grouped FRED and ECB sources, the month-end note,
 * and a CSV whose notes match its columns with rounded values.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v203_bar_colours.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const { JSDOM, VirtualConsole } = require("jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };

async function boot(){
  let html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8"), ROOT);
  // a hook inside the page's own scope, so the test can drive its functions directly
  html = html.replace('var chartType = "line";', 'var chartType = "line"; window.__cmEval = function(js){ return eval(js); };');
  const vc = new VirtualConsole();
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/chartmaker.html",
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => ({ font: "11px sans-serif", measureText(t){ return { width: String(t).length * (parseFloat(this.font) || 11) * 0.55 }; }, fillText(){}, clearRect(){}, scale(){}, setTransform(){} });
      win.Chart = function(){}; win.Chart.register = function(){};
      win.fetch = u => {
        const file = String(u).split("/").pop().split("?")[0], p = path.join(ROOT, file);
        if(!fs.existsSync(p)) return Promise.reject(new Error("no such file " + file));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
      win.matchMedia = () => ({ matches: false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.EATLAS_PREFS = { isLoggedIn: () => true, registerBanner(){}, onLogin(){} };
    },
  });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  await new Promise(r => setTimeout(r, 1500));
  return win;
}

(async () => {
  const win = await boot();
  const run = js => win.__cmEval(js);
  const fills = () => new Set([...run(`czmState = buildCzmState(); G.W = CM_DESK_W;
    SNAPSHOT_ROWS = dropNoDataRows(buildSnapshotRows()); applyBarRankColors(SNAPSHOT_ROWS);
    czmBuildBars("light", true)`).matchAll(/rx='3' fill='([^']+)'/g)].map(m => m[1]));
  const row = () => win.document.getElementById("cmManyBarColourRow").style.display;
  run(`series.length = 0;
    Object.keys(REGISTRY).forEach(function(c){ addSeries(c, "bond_yield_10y", false, true); });
    chartType = "bar"; syncBarLegendTitle(); renderChart();`);
  ok(row() === "", "option shown above 10 countries");
  ok(run("style.manyBarColour") === "one", "default is one colour");
  let f = fills();
  ok(f.size === 1 && f.has("#1E4566"), "one colour: all bars navy (" + [...f].join(" ") + ")");
  win.document.querySelector('#cmManyBarColourSeg button[data-mode="country"]').click();
  f = fills();
  ok(run("style.manyBarColour") === "country", "button sets country colours");
  ok(f.size > 30, "country colours: " + f.size + " distinct fills");
  ok(f.has(run('COUNTRY_COLOR["Colombia"]')), "Colombia keeps its own colour");
  ok(/"manyBarColour":"country"/.test(run('JSON.stringify(buildSavePayload("t"))')), "saved chart keeps the choice");
  win.document.querySelector('#cmManyBarColourSeg button[data-mode="one"]').click();
  f = fills();
  ok(f.size === 1 && f.has("#1E4566"), "switching back gives navy again");
  run(`var keep = ["UK", "US", "Germany", "France", "Italy"]; series = series.filter(function(s){ return keep.indexOf(s.country) !== -1; }); renderChart();`);
  ok(row() === "none", "option hidden at 5 countries");
  ok(fills().size === 5, "5 countries keep ranked shades");
  run('chartType = "line"; renderChart();');
  ok(row() === "none", "option hidden on a line chart");
  console.log(`test_v203_bar_colours: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
