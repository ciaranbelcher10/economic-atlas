#!/usr/bin/env node
/* v1.9.80 Chartmaker on phones: example gallery + live chart instead of the "bigger screen" dead end,
 * "Send this to my desktop" link (?ex=key opens the same example on any screen), saved charts read-only
 * for signed-in people via the page's own Open list. Desktop unchanged.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_chartmaker_mobile.js */
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
  ok(win.EA_CM && win.EA_CM.ready && win.EA_CM.examples.length === 4, "page exposes 4 examples");
  ok(doc.body.classList.contains("cm-m"), "phone mode on");
  const gate = $("#cmMobileGate");
  ok(gate && !/bigger screen\b(?! )/.test("") && !/needs a bigger screen/i.test(gate.textContent), "no dead-end message");
  const chips = $$(".cm-m-chip");
  ok(chips.length === 4 && chips.map(c => c.textContent).join("|") === win.EA_CM.examples.map(e => e.title).join("|"), "one chip per example");
  ok(chips.every(c => c.getAttribute("aria-pressed") === "false"), "starter chart: no example pressed");
  ok($("#cmSvgBox").style.display !== "none", "the live chart is drawn");
  for(const [i, want] of [[1, 7], [2, 3], [3, 3], [0, 1]]){
    chips[i].click(); await sleep(150);
    const k = chips[i].dataset.key;
    ok(win.EA_CM.current === k && chips[i].getAttribute("aria-pressed") === "true" && $$(".cm-m-chip[aria-pressed=true]").length === 1, `example ${k} selected`);
    ok(seriesNames(doc).length === want, `example ${k} draws ${want} series (got ${seriesNames(doc).length})`);
    ok($("#cmSvgBox").style.display !== "none" && $("#cmSvgBox").innerHTML.length > 200, `example ${k} chart rendered`);
  }
  // send to desktop: no share -> clipboard
  chips[1].click(); await sleep(100);
  $(".cm-m-send").click(); await sleep(50);
  ok(win.__copied[0] === "https://theeconomicatlas.com/chartmaker?ex=g7-inflation", "copies a link to this example: " + win.__copied[0]);
  ok(/Link copied/.test($(".cm-m-msg").textContent), "confirms the copy");
  ok($(".cm-m-saved").hidden, "signed out: no saved charts button");
  ok($$("#cmMobileGate").length === 1, "one gallery");
  win.dispatchEvent(new win.Event("resize")); await sleep(50);
  ok($$("#cmMobileGate").length === 1 && $$(".cm-m-chip").length === 4, "re-runs keep one gallery");

  // with share sheet + signed in
  const b = await boot({ share: true, loggedIn: true });
  b.doc.querySelectorAll(".cm-m-chip")[2].click(); await sleep(100);
  b.doc.querySelector(".cm-m-send").click(); await sleep(50);
  ok(b.win.__shared.length === 1 && b.win.__shared[0].url === "https://theeconomicatlas.com/chartmaker?ex=unemployment" && !b.win.__copied.length, "phones with a share sheet share the link");
  ok(!b.doc.querySelector(".cm-m-saved").hidden, "signed in: saved charts button shown");
  let opened = 0; b.doc.getElementById("cmOpenBtn").addEventListener("click", () => opened++);
  b.doc.querySelector(".cm-m-saved").click();
  ok(opened === 1, "saved charts opens the page's own Open list");

  // ?ex= link on desktop opens that example in the editor
  const d = await boot({ desktop: true, query: "?ex=policy-rates" });
  ok(!d.doc.body.classList.contains("cm-m") && (!d.doc.getElementById("cmMobileGate") || d.doc.getElementById("cmMobileGate").style.display === "none"), "desktop: no phone gallery");
  ok(d.win.EA_CM.current === "policy-rates" && seriesNames(d.doc).length === 3, "desktop ?ex=policy-rates opens that example");
  ok(!d.doc.getElementById("cmStarterNote").hidden, "desktop: shown as an example that clears when you add a metric");
  const e = await boot({ desktop: true, query: "?ex=nonsense" });
  ok(e.win.EA_CM.current === null && seriesNames(e.doc).length === 1, "unknown ?ex= falls back to the normal starter");

  const start = CSS.indexOf("@media (max-width:760px){", 140);
  ok(CSS.indexOf("body.cm-m .cmx-data") > start && start > 0, "phone-scoped CSS");
  ok(!/#cmLayout\{ display:none !important; \}/.test(CSS), "layout no longer hidden on phones");
  ok(/\.cm-m-chip\{[^}]*min-height:40px/.test(CSS) && /\.cm-m-send, \.cm-m-saved\{[^}]*min-height:44px/.test(CSS), "tap targets");

  console.log(`test_chartmaker_mobile: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.stack); console.log(`test_chartmaker_mobile: ${checks - failures} ok, ${failures + 1} failed`); process.exit(1); });
