#!/usr/bin/env node
/* v1.9.107 Chartmaker phone gallery: Ciaran's three saved showcase charts (Policy rates, G7 unemployment,
 * UK trade balance), each loaded exactly as saved, with ?ex= links for the two new ones.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v19107.js */
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
  const $ = s => doc.querySelector(s), $$ = s => [...doc.querySelectorAll(s)];
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  ok(win.EA_CM.examples.map(e => e.key).join("|") === "policy-rates|g7-unemployment|uk-trade-balance", "three examples in order: " + win.EA_CM.examples.map(e => e.key).join("|"));
  ok($$(".cm-m-chip").map(c => c.textContent).join("|") === "Policy rates|G7 unemployment|UK trade", "chip labels");
  ok(win.EA_CM.current === "policy-rates", "phone opens on Policy rates");
  const HT = fs.readFileSync(path.join(ROOT, "chartmaker.html"), "utf8");
  const ex = HT.slice(HT.indexOf("var EXAMPLES = ["), HT.indexOf("function exampleByKey"));
  ok(!/user_id|"id"\s*:|created_at/.test(ex), "no user ids or row ids copied into the page");

  // G7 unemployment: horizontal bars, July 2026 snapshot, data labels
  $$(".cm-m-chip")[1].click(); await sleep(150);
  ok(win.EA_CM.current === "g7-unemployment" && $$(".cm-m-chip")[1].getAttribute("aria-pressed") === "true", "G7 chip selected");
  ok(seriesNames(doc).length === 7, "G7: seven countries: " + seriesNames(doc).length);
  ok($("#cmChartTitle").value === "G7 Unemployment Rates", "G7 title as saved");
  ok($("#cmChartTypeSeg button.active").dataset.type === "bar", "G7 is a bar chart");
  let h = $("#cmSvgBox").innerHTML;
  ok(/G7 Unemployment Rates/.test(h) && /July 2026/.test(h), "G7 drawn with title and July 2026");
  ["Germany","France","Italy","Canada","Japan","UK","US"].forEach(c => ok(new RegExp(">" + c + "<").test(h), "G7 bar for " + c));

  // UK trade balance: vertical bars, zero line, Year only labels
  $$(".cm-m-chip")[2].click(); await sleep(150);
  ok(win.EA_CM.current === "uk-trade-balance", "trade balance chip selected");
  ok(seriesNames(doc).length === 1 && $("#cmChartTitle").value === "UK Trade Balance", "trade balance: one series, title as saved");
  ok($("#cmChartTypeSeg button.active").dataset.type === "bar", "trade balance is a bar chart");
  h = $("#cmSvgBox").innerHTML;
  const xt = [...doc.querySelectorAll("#cmSvgBox svg text")].map(t => t.textContent);
  ok(xt.some(t => /^\d{4}$/.test(t)) && !xt.some(t => /^[A-Z][a-z]{2} \d{4}$/.test(t)), "Year only date labels");
  ok(!/\u2212\u00a30|-\u00a30bn|\u2212£0/.test(h), "no negative zero");

  // back to Policy rates restores its chart
  $$(".cm-m-chip")[0].click(); await sleep(150);
  ok(seriesNames(doc).length === 3 && $("#cmChartTitle").value === "ECB, Fed, BoE Policy Rates", "back to Policy rates");
  ok($$(".cm-m-chip").filter(c => c.getAttribute("aria-pressed") === "true").length === 1, "exactly one chip pressed");

  // ?ex= on desktop for the new keys
  for(const k of ["g7-unemployment", "uk-trade-balance"]){
    const d = await boot({ desktop: true, query: "?ex=" + k });
    ok(d.win.EA_CM.current === k && d.errs.length === 0, "desktop ?ex=" + k + " opens it");
  }
  console.log("test_v19107: " + checks + " checks, " + failures + " failed");
  process.exit(failures ? 1 : 0);
})();
