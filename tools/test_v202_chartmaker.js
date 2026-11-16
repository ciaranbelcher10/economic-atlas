#!/usr/bin/env node
/* v2.0.2: ChartMaker bar chart of 10-year bond yields across every country, and its CSV.
 * First label inside the canvas, period line clear of rotated labels, "Latest month, to ..." when bars
 * carry earlier periods, one colour above 10 countries, grouped FRED and ECB sources, the month-end note,
 * and a CSV whose notes match its columns with rounded values.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v202_chartmaker.js */
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
  // every country on the bond yield, as the reported chart
  run(`series.length = 0;
    Object.keys(REGISTRY).forEach(function(c){ addSeries(c, "bond_yield_10y", false, true); });
    chartType = "bar"; style.xLabelAngle = "diagonal"; style.sortMode = "alpha";
    syncBarLegendTitle(); renderChart();`);
  const n = run("series.length"), live = run("liveSeries().length");
  ok(n > 40 && live > 30, `bond series added: ${n} (${live} with data)`);

  const svg = run(`czmState = buildCzmState(); G.W = CM_DESK_W;
    SNAPSHOT_ROWS = dropNoDataRows(buildSnapshotRows()); applyBarRankColors(SNAPSHOT_ROWS);
    SNAPSHOT_ROWS = sortRowsByMode(SNAPSHOT_ROWS, function(r){ return r.value; }, style.sortMode);
    czmBuildBars("light", true)`);

  // 1. first rotated label starts inside the canvas
  const lab = [...svg.matchAll(/<text x='([\d.]+)' y='([\d.]+)' font-size='([\d.]+)'[^>]*rotate\(-45[^>]*>([^<]*)</g)];
  ok(lab.length > 30, "diagonal labels drawn: " + lab.length);
  const first = lab[0];
  const w = run(`estProseWidth(${JSON.stringify(first[4])}, AFS())`);
  ok(+first[1] - w * 0.71 >= 0, `first label "${first[4]}" starts at x=${(+first[1] - w * 0.71).toFixed(1)}`);

  // 2. the period line sits below every rotated label
  const legend = run("style.legendTitle");
  const lt = new RegExp("<text x='[\\d.]+' y='([\\d.]+)'[^>]*>" + legend.replace(/[()]/g, "\\$&") + "<").exec(svg);
  ok(!!lt, "period line drawn: " + legend);
  const lowest = Math.max(...lab.map(m => +m[2] + run(`estProseWidth(${JSON.stringify(m[4])}, AFS())`) * 0.71));
  ok(lt && +lt[1] - 12 > lowest, `period line y=${lt && lt[1]} clears labels ending at y=${lowest.toFixed(1)}`);

  // 3. title wording when bars carry earlier months
  const stale = run("buildSnapshotRows().some(function(r){ return r.stale; })");
  ok(stale ? /^Latest month, to /.test(legend) : !/^Latest/.test(legend), `period wording "${legend}" (earlier months present: ${stale})`);

  // 4. one colour
  const fills = new Set([...svg.matchAll(/<rect x='[\d.]+' y='[\d.]+' width='[\d.]+' height='[\d.]+' rx='3' fill='([^']+)'/g)].map(m => m[1]));
  ok(fills.size === 1, "bar colours: " + [...fills].join(" "));

  // 5. grouped sources and the month-end note
  const src = run("buildCombinedSrcNote()");
  ok(!/(^|; )FRED series/.test(src) && /FRED \(/.test(src), "FRED grouped: " + src.slice(0, 160));
  ok(!/M\.[A-Z]{2}\.L\.L40/.test(src), "ECB IRS codes grouped");
  ok(/Japan and euro area figures are month-end yields; the others are monthly averages\./.test(src), "month-end note");
  ok(!/—|--/.test(src), "no em dash or double hyphen in footer");

  // 6. CSV
  const csv = run("buildChartCSV()").split("\n");
  const cols = csv[0].split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/).length - 1;
  const blank = csv.indexOf("");
  const notes = csv.slice(blank + 2).filter(l => l && !/^"?(No data on|Note:|Values are|Downloaded)/.test(l));
  ok(cols === live, `CSV columns ${cols} = series with data ${live}`);
  ok(notes.length === live, `CSV source notes ${notes.length} = columns ${live}`);
  ok(n === live || csv.some(l => /No data on The Economic Atlas for: /.test(l)), "no-data countries named once");
  const long = csv.slice(1, blank).join(",").match(/\d\.\d{5,}/);
  ok(!long, "values rounded" + (long ? ": " + long[0] : ""));

  // 7. a 5-country chart keeps the ranked shades and its own month wording
  run(`var keep = ["UK", "US", "Germany", "France", "Italy"]; series = series.filter(function(s){ return keep.indexOf(s.country) !== -1; });
    syncBarLegendTitle(); renderChart();`);
  const svg5 = run(`czmState = buildCzmState(); SNAPSHOT_ROWS = dropNoDataRows(buildSnapshotRows()); applyBarRankColors(SNAPSHOT_ROWS); czmBuildBars("light", true)`);
  const fills5 = new Set([...svg5.matchAll(/rx='3' fill='([^']+)'/g)].map(m => m[1]));
  ok(fills5.size === 5, "five countries keep five ranked shades: " + fills5.size);

  console.log(`test_v202_chartmaker: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
