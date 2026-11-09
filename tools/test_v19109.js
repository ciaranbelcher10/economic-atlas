#!/usr/bin/env node
/* v1.9.109 Chartmaker phones: a short caption under a bar chart whose periods were combined (the editor
 * note above the chart is hidden on phones), and nothing for charts that combine nothing; never on desktop.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19109.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const { JSDOM, VirtualConsole } = require("jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const MJS = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");

async function boot(o){
  o = o || {};
  const html = require("./inline_local_scripts")(fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8"), ROOT);
  const errs = [], vc = new VirtualConsole();
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if(!/supabase|EATLAS_PREFS|Not implemented|\bd3\b|is not defined: undefined/i.test(m)) errs.push(m); });
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/chartmaker" + (o.query || ""),
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => ({ canvas: {}, clearRect(){}, save(){}, restore(){}, beginPath(){}, moveTo(){}, lineTo(){}, stroke(){}, fill(){}, arc(){}, fillRect(){}, measureText: () => ({ width: 10 }), fillText(){}, setTransform(){}, scale(){}, translate(){}, closePath(){}, createLinearGradient: () => ({ addColorStop(){} }) });
      function C(c, g){ this.data = (g && g.data) || { datasets: [] }; this.options = {}; } C.prototype.update = C.prototype.destroy = function(){}; C.register = function(){}; win.Chart = C;
      win.fetch = u => { const f = String(u).split("/").pop().split("?")[0], p = path.join(ROOT, f);
        return fs.existsSync(p) ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) }) : Promise.reject(new Error("no " + f)); };
      win.matchMedia = () => ({ matches: !o.desktop, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      if(o.loggedIn) win.EATLAS_PREFS = { isLoggedIn: () => true, registerBanner(){}, onLogin(){}, ready: Promise.resolve() };
      win.__shared = [];
      if(o.share) Object.defineProperty(win.navigator, "share", { configurable: true, value: d => { win.__shared.push(d); return Promise.resolve(); } });
      win.__copied = [];
      Object.defineProperty(win.navigator, "clipboard", { configurable: true, value: { writeText: t => { win.__copied.push(t); return Promise.resolve(); } } });
    } });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for(let i = 0; i < 100 && !(win.EA_CM && win.EA_CM.ready); i++) await sleep(50);
  win.eval(MJS); await sleep(100);
  return { win, doc: win.document, errs };
}
const seriesNames = d => [...d.querySelectorAll("#cmSeriesList .cm-seriesitem")].map(li => li.textContent);

(async () => {
  const { win, doc, errs } = await boot();
  const $ = s => doc.querySelector(s), chips = () => [...doc.querySelectorAll(".cm-m-chip")];
  const cap = () => $("#cmAggCaption");
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  ok(cap() && cap().hidden, "Policy rates (a line chart): no caption");
  chips()[2].click(); await sleep(150);
  ok(!cap().hidden, "UK trade: caption shown");
  ok(/^Yearly totals of monthly data\. 2026 \(Jan to [A-Z][a-z]{2}\) not shown: incomplete\.$/.test(cap().textContent), "caption text: " + cap().textContent);
  ok(!/\u2014/.test(cap().textContent), "no em dashes");
  const outer = $("#cmChartOuter");
  ok(outer && outer.nextElementSibling === cap(), "caption sits under the chart card");
  ok(!$("#cmSvgBox").innerHTML.includes("not shown: incomplete"), "caption is not drawn into the chart image (PNG unaffected)");
  chips()[1].click(); await sleep(150);
  ok(cap().hidden && cap().textContent === "", "G7 (one bar per country): caption cleared");
  chips()[2].click(); await sleep(150);
  chips()[0].click(); await sleep(150);
  ok(cap().hidden, "back to Policy rates: caption cleared");
  const d = await boot({ desktop: true, query: "?ex=uk-trade-balance" });
  ok(d.doc.getElementById("cmAggCaption").hidden, "desktop: no caption (the editor note says it)");
  ok(/yearly totals of the monthly data/.test(d.doc.getElementById("cmChartTypeNote").textContent), "desktop note unchanged");
  console.log("test_v19109: " + checks + " checks, " + failures + " failed");
  process.exit(failures ? 1 : 0);
})();
