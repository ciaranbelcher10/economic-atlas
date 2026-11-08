#!/usr/bin/env node
/* v1.9.108 Chartmaker bar charts over long ranges: periods are combined (totals for flows, averages for
 * rates, indices and annual-rate series, end-of-period for stocks), never sampled; incomplete periods
 * are left out and named; the CSV keeps every original period.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19108.js */
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

const HT = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
const helperSrc = HT.slice(HT.indexOf("var BAR_MAX = 90;"), HT.indexOf("function barAggNote("));
const FMT_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function fmtPeriod(p){ let m = /^(\d{4})-Q(\d)$/.exec(p); if(m) return "Q" + m[2] + " " + m[1]; m = /^(\d{4})-(\d{2})$/.exec(p); if(m) return FMT_MONTHS[+m[2]-1] + " " + m[1]; return p; }
const H = labels => new Function("servedLabel", "fmtPeriod", helperSrc + "; return { aggregateBarPoints, barAggRule, BAR_MAX };")(
  (c, m) => labels[c + "|" + m] || "", fmtPeriod);
const h = H({ "US|gdp_level": "GDP, nominal, seasonally adjusted annual rate (GDP)", "Japan|gdp_real": "Real GDP, chained 2015 yen, SAAR (JPNRGDPEXP)", "UK|gdp_level": "GDP, current prices, CP SA (ONS YBHA)" });
const months = (y0, m0, y1, m1, f) => { const o = []; for(let y = y0, m = m0; y < y1 || (y === y1 && m <= m1); m === 12 ? (y++, m = 1) : m++) o.push({ x: y + "-" + String(m).padStart(2, "0"), y: f(y, m) }); return o; };

(async () => {
  // rules
  ok(h.barAggRule("UK", "trade_balance", "raw") === "sum", "trade balance is a flow: totals");
  ok(h.barAggRule("UK", "exports", "raw") === "sum" && h.barAggRule("UK", "imports", "raw") === "sum", "exports and imports: totals");
  ok(h.barAggRule("UK", "gdp_level", "raw") === "sum", "quarterly GDP not at an annual rate: totals");
  ok(h.barAggRule("US", "gdp_level", "raw") === "mean" && h.barAggRule("Japan", "gdp_real", "raw") === "mean", "GDP at an annual rate (SAAR): averaged, not summed");
  ok(h.barAggRule("UK", "net_debt", "raw") === "last", "net debt is a stock: end of period");
  ok(["unemployment","policy_rate","cpi","bond_yield_10y","fx_usd","business_confidence"].every(m => h.barAggRule("UK", m, "raw") === "mean"), "rates and indices: averages");
  ok(h.barAggRule("UK", "trade_balance", "yoy") === "mean", "a transformed flow (growth rate) is averaged");

  // short ranges untouched
  const short = months(2020, 1, 2026, 12, () => 1);
  ok(h.aggregateBarPoints(short, "UK", "trade_balance", "raw").level === null && h.aggregateBarPoints(short, "UK", "trade_balance", "raw").points.length === 84, "84 months: one bar per month, unchanged");
  const ninety = months(2019, 1, 2026, 6, () => 1);
  ok(ninety.length === 90 && h.aggregateBarPoints(ninety, "UK", "trade_balance", "raw").level === null, "exactly 90 months still unchanged");

  // trade balance 1997-01 to 2026-08: yearly totals, 2026 left out
  const tb = months(1997, 1, 2026, 8, (y, m) => y * 100 + m);
  const a = h.aggregateBarPoints(tb, "UK", "trade_balance", "raw");
  ok(a.level === "year" && a.rule === "sum", "356 months: yearly totals (quarters would be 119 bars)");
  ok(a.points.length === 29 && a.points[0].x === "1997" && a.points[28].x === "2025", "1997 to 2025, one bar a year: " + a.points.length);
  const want2000 = [...Array(12)].reduce((s, _, i) => s + 2000 * 100 + i + 1, 0);
  ok(a.points.find(p => p.x === "2000").y === want2000, "2000 is the sum of its 12 months");
  ok(!a.points.some(p => p.x === "2026") && a.dropped.length === 1 && /^2026 \(Jan to Aug only\)$/.test(a.dropped[0]), "incomplete 2026 left out and named: " + a.dropped.join("|"));
  ok(a.points.length <= h.BAR_MAX, "within the bar cap");

  // quarters when they fit; partial first quarter dropped
  const mq = months(2005, 2, 2026, 6, () => 2);
  const q = h.aggregateBarPoints(mq, "UK", "unemployment", "raw");
  ok(q.level === "quarter" && q.rule === "mean", "rates over 257 months: quarterly averages");
  ok(q.points[0].x === "2005-Q2" && q.dropped[0] === "Q1 2005 (Feb to Mar only)", "partial first quarter left out: " + q.dropped[0]);
  ok(q.points.every(p => p.y === 2), "averages keep the level");
  // a gap makes a period incomplete
  const gap = months(1990, 1, 2025, 12, () => 1).filter(p => p.x !== "2010-06");
  const g = h.aggregateBarPoints(gap, "UK", "exports", "raw");
  ok(!g.points.some(p => p.x === "2010") && g.dropped.some(d => /^2010 /.test(d)), "a year with a missing month is not presented as a full year");

  // quarterly series -> years; stock takes the last quarter
  const qs = []; for(let y = 1990; y <= 2025; y++) for(let k = 1; k <= 4; k++) qs.push({ x: y + "-Q" + k, y: y * 10 + k });
  const st = h.aggregateBarPoints(qs, "UK", "net_debt", "raw");
  ok(st.level === "year" && st.points.find(p => p.x === "2000").y === 20004, "stock: year-end (Q4) figure");
  const us = h.aggregateBarPoints(qs, "US", "gdp_level", "raw");
  ok(us.points.find(p => p.x === "2000").y === 20002.5, "US SAAR GDP: yearly average, not 4x");

  // daily -> months, edges checked
  const days = []; for(let d = new Date(Date.UTC(2025, 0, 2)); d <= new Date(Date.UTC(2025, 11, 15)); d.setUTCDate(d.getUTCDate() + 1)) days.push({ x: d.toISOString().slice(0, 10), y: 4 });
  const dm = h.aggregateBarPoints(days, "UK", "policy_rate", "raw");
  ok(dm.level === "month" && dm.points.length === 11 && dm.points[0].x === "2025-01" && /^Dec 2025/.test(dm.dropped[0]), "daily: monthly averages, part-month December left out");

  // the live page: Chartmaker's UK trade balance example on desktop
  const d = await boot({ desktop: true, query: "?ex=uk-trade-balance" });
  ok(d.errs.length === 0, "no page errors: " + d.errs.join("; "));
  const note = d.doc.getElementById("cmChartTypeNote").textContent;
  ok(/each bar is a year: yearly totals of the monthly data/.test(note), "note says yearly totals: " + note);
  ok(/Incomplete periods are left out: 2026 \(Jan to [A-Z][a-z]{2} only\)/.test(note), "note names the incomplete year");
  ok(!/sampled|representative subset/.test(note), "no sampling wording");
  ok(!/\u2014/.test(note), "no em dashes in the note");
  const rects = d.doc.querySelectorAll("#cmSvgBox svg rect[rx='3']").length;
  ok(rects >= 25 && rects <= 30, "about 29 yearly bars drawn: " + rects);
  ok(HT.indexOf("step = Math.ceil(pts.length / maxBars)") < 0, "the sampling code is gone");
  console.log("test_v19108: " + checks + " checks, " + failures + " failed");
  process.exit(failures ? 1 : 0);
})();
