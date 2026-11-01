#!/usr/bin/env node
/* v1.9.49: Mexico and Poland off the calendar (no readable source yet), shown under
 * "Not on the calendar yet", and a saved list that still names them is cleaned on load.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_calendar_mx_pl.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const { JSDOM, VirtualConsole } = require("jsdom");
const html = fs.readFileSync(path.join(ROOT, "calendar.html"), "utf8");
const KEY = (html.match(/LOCAL_FALLBACK_COUNTRIES_KEY\s*=\s*"([^"]+)"/) || [])[1];
async function boot(seed){
  const vc = new VirtualConsole();
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, url: "https://theeconomicatlas.com/calendar",
    beforeParse(win){
      if(seed) Object.keys(seed).forEach(k => win.localStorage.setItem(k, seed[k]));
      win.matchMedia = () => ({ matches: true, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.fetch = u => { const p = path.join(ROOT, String(u).split("/").pop().split("?")[0]);
        return fs.existsSync(p) ? Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))) }) : Promise.resolve({ ok: false, status: 404 }); };
    } });
  const win = dom.window;
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  await new Promise(r => setTimeout(r, 900));
  return win;
}
(async () => {
  ok(!!KEY, "local storage key found");
  let win = await boot(), doc = win.document, $ = s => doc.querySelector(s);
  $("#calCountriesBtn").dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const names = [...doc.querySelectorAll("#ctpCountries .nm")].map(n => n.textContent);
  const notYet = $("#ctpNotYet").textContent;
  for(const c of ["Mexico", "Poland"]){
    ok(!names.includes(c), `${c} is not listed as trackable`);
    ok(new RegExp(c).test(notYet), `${c} is named under Not on the calendar yet`);
  }
  ok(names.includes("Denmark") && names.includes("Germany") && names.includes("Canada"), "other countries still trackable");
  const total = +$("#ctpCount").textContent.split(" of ")[1];
  ok(total === names.length, `count matches the list (${total})`);

  const picked = async seed => {
    const w = await boot(seed), d = w.document;
    d.querySelector("#calCountriesBtn").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    return { count: d.querySelector("#ctpCount").textContent,
             ticked: [...d.querySelectorAll("#ctpCountries input:checked")].map(i => i.dataset.country) };
  };
  let r = await picked({ [KEY]: JSON.stringify(["Mexico", "Poland", "Canada"]) });
  ok(r.count === `1 of ${total}` && JSON.stringify(r.ticked) === '["Canada"]', "a saved list loses Mexico and Poland, keeps Canada: " + JSON.stringify(r));
  r = await picked({ [KEY]: JSON.stringify(["Mexico", "Poland"]) });
  ok(r.count === `${total} of ${total}`, "a saved list of only removed countries falls back to all: " + r.count);
  console.log(`test_calendar_mx_pl: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
