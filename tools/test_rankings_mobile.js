#!/usr/bin/env node
/* v1.9.79 Rankings on phones: region chips filter rows, "Find a country" jumps to and highlights a row.
 * Also checks bump_assets keeps the generator's mobile.css/mobile.js versions in step with the root pages.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_rankings_mobile.js */
const fs = require("fs"), path = require("path"), cp = require("child_process");
const ROOT = path.resolve(__dirname, "..");
const { JSDOM, VirtualConsole } = require("jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const MJS = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");

function boot(file, phone){
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, file), "utf8"), { runScripts: "outside-only", pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(), url: "https://theeconomicatlas.com/" + file.replace(/\.html$/, "") });
  const w = dom.window;
  w.matchMedia = () => ({ matches: phone, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
  w.HTMLElement.prototype.scrollIntoView = function(){ w.__scrolled = this; };
  w.eval(MJS);
  w.document.dispatchEvent(new w.Event("DOMContentLoaded"));
  return w;
}

const pages = fs.readdirSync(path.join(ROOT, "rankings")).filter(f => f.endsWith(".html") && /id="rkTable"/.test(fs.readFileSync(path.join(ROOT, "rankings", f), "utf8")));
ok(pages.length >= 10, "rankings pages found: " + pages.length);
pages.forEach(f => {
  const w = boot("rankings/" + f, true), d = w.document;
  const rows = [...d.querySelectorAll("#rkTable tbody tr")];
  const bars = d.querySelectorAll("#rkMTools");
  ok(bars.length === 1, f + ": one tools bar");
  if(!bars.length) return;
  const chips = [...d.querySelectorAll(".rk-m-chip")];
  const regions = {}; rows.forEach(tr => { const r = tr.querySelector(".rk-region"); if(r) regions[r.textContent.trim()] = (regions[r.textContent.trim()] || 0) + 1; });
  ok(chips.length === Object.keys(regions).length + 1 && chips[0].textContent === "All " + rows.length, f + ": All + one chip per region");
  ok(chips.slice(1).every(c => regions[c.dataset.region] && c.textContent === c.dataset.region + " " + regions[c.dataset.region]), f + ": chip counts match rows");
  const visible = () => rows.filter(tr => !tr.classList.contains("rk-m-hide"));
  const r1 = chips[1].dataset.region;
  chips[1].click();
  ok(visible().length === regions[r1] && visible().every(tr => tr.querySelector(".rk-region").textContent.trim() === r1), f + ": region chip filters to " + r1);
  ok(chips[1].getAttribute("aria-pressed") === "true" && chips[0].getAttribute("aria-pressed") === "false", f + ": pressed state");
  ok(/Ranks are out of all/.test(d.querySelector(".rk-m-status").textContent), f + ": status explains ranks");
  ok(visible().every(tr => tr.querySelector(".rank").textContent.trim() === tr.dataset.rank), f + ": original ranks kept");
  // find a country outside the filtered region resets to All and highlights it
  const other = rows.find(tr => tr.querySelector(".rk-region").textContent.trim() !== r1);
  const name = other.querySelector(".rk-cty").textContent.trim();
  const inp = d.getElementById("rkMFind");
  inp.value = name.slice(0, 3).toLowerCase(); inp.dispatchEvent(new w.Event("input"));
  const hit = d.querySelector("tr.rk-m-hit");
  ok(hit && hit.querySelector(".rk-cty").textContent.trim().toLowerCase().indexOf(name.slice(0, 3).toLowerCase()) === 0, f + ": find highlights a row starting with the text");
  ok(hit && !hit.classList.contains("rk-m-hide") && chips[0].getAttribute("aria-pressed") === "true", f + ": find clears a filter that hid the row");
  ok(w.__scrolled === hit, f + ": find scrolls to the row");
  ok(d.querySelectorAll("tr.rk-m-hit").length === 1, f + ": one highlight");
  inp.value = ""; inp.dispatchEvent(new w.Event("input"));
  ok(!d.querySelector("tr.rk-m-hit"), f + ": clearing find removes the highlight");
  chips[0].click();
  ok(visible().length === rows.length, f + ": All shows every row");
  w.dispatchEvent(new w.Event("resize"));
  ok(d.querySelectorAll("#rkMTools").length === 1, f + ": not duplicated");
});
{ const w = boot("rankings/" + pages[0], false);
  ok(!w.document.getElementById("rkMTools"), "desktop: no tools bar"); }

const start = CSS.indexOf("@media (max-width:760px){", 140);
ok(CSS.indexOf("#rkMTools{") > start && start > 0, "rankings CSS phone-scoped");
ok(/\.rk-m-chip\{ flex:none; min-height:40px;/.test(CSS) && /#rkMFind\{[^}]*min-height:44px/.test(CSS) && /#rkMFind\{[^}]*font-size:16px/.test(CSS), "tap targets and no iOS zoom");
ok(/#rkTable tr\.rk-m-hide\{ display:none !important; \}/.test(CSS), "hidden rows really hide");

// generator versions follow bump_assets
const gen = fs.readFileSync(path.join(ROOT, "generate_indicator_pages.py"), "utf8");
const cmp = fs.readFileSync(path.join(ROOT, "compare.html"), "utf8");
const v = (s, a) => +((s.match(new RegExp(a.replace(".", "\\.") + "\\?v=(\\d+)")) || [0, 0])[1]);
ok(v(gen, "mobile.css") === v(cmp, "mobile.css") && v(gen, "mobile.js") === v(cmp, "mobile.js"),
  `generator template on the same mobile.css/js as the root pages (gen v${v(gen, "mobile.css")}/v${v(gen, "mobile.js")}, root v${v(cmp, "mobile.css")}/v${v(cmp, "mobile.js")})`);

console.log(`test_rankings_mobile: ${checks - failures} ok, ${failures} failed`);
process.exit(failures ? 1 : 0);
