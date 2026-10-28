#!/usr/bin/env node
/* Behaviour of the two reference pages (v1.9.16): /methodology and /methodology-by-economy, loaded from the
 * repository with their real doc.js in jsdom. Needs jsdom 24 in NODE_PATH (see invariants_gate.js for the install).
 * Called by tools/test_doc_pages.py; also runnable alone:  NODE_PATH=/tmp/node_modules node tools/test_doc_pages.js
 */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const {JSDOM, VirtualConsole, ResourceLoader} = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; console.log("  FAIL  " + m); } };
const SUPA = "window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:null}).then(r)}};return {from:function(){return q},auth:{getSession:function(){return Promise.resolve({data:{session:null}})},onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}}}}}};";
class Loader extends ResourceLoader {
  fetch(url) {
    const f = path.join(ROOT, url.replace(/^https:\/\/example\.test\//, "").split("?")[0].split("#")[0]);
    if (/supabase/.test(url)) return Promise.resolve(Buffer.from(SUPA));
    if (/^https:\/\/example\.test\//.test(url) && fs.existsSync(f)) return Promise.resolve(fs.readFileSync(f));
    return Promise.resolve(Buffer.from(""));
  }
}
process.on("unhandledRejection", () => {});
const wait = ms => new Promise(r => setTimeout(r, ms));
function load(page, hash) {
  const vc = new VirtualConsole(), errs = [];
  vc.on("jsdomError", e => errs.push(String(e.message || e).split("\n")[0]));
  const dom = new JSDOM(fs.readFileSync(path.join(ROOT, page), "utf8"), {
    runScripts: "dangerously", resources: new Loader(), url: "https://example.test/" + page + (hash || ""),
    virtualConsole: vc, pretendToBeVisual: true,
    beforeParse(w) {
      w.matchMedia = () => ({matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
      w.scrollTo = () => {};
    }});
  return {dom, errs};
}
const visibleNames = d => [...d.querySelectorAll(".mb-econ")].filter(s => !s.hidden).map(s => s.getAttribute("data-name"));
const allNames = d => [...d.querySelectorAll(".mb-econ")].map(s => s.getAttribute("data-name"));
const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));

(async () => {
  // ------------------------------------------------------------ by economy
  {
    const {dom, errs} = load("methodology-by-economy.html"); await wait(900);
    const w = dom.window, d = w.document;
    const names = allNames(d), n = names.length;
    ok(n === 62, `62 economy sections expected, found ${n}`);
    ok(errs.length === 0, "by-economy: script errors: " + errs.slice(0, 2).join(" | "));
    ok(d.querySelectorAll(".doc-anchor").length >= n, `an anchor on every economy and section, found ${d.querySelectorAll(".doc-anchor").length}`);
    ok(!!d.querySelector(".doc-top"), "back-to-top button missing");
    const input = d.getElementById("docFilter"), count = d.getElementById("docCount"), empty = d.getElementById("docEmpty");
    const type = v => { input.value = v; input.dispatchEvent(new w.Event("input", {bubbles: true})); };

    type("ger");
    const want = names.filter(x => x.toLowerCase().includes("ger"));
    ok(want.length >= 2 && same(visibleNames(d), want), `typing "ger" must show exactly ${JSON.stringify(want)}, shows ${JSON.stringify(visibleNames(d))}`);
    ok(count.textContent === `${want.length} of ${n} economies`, `count text is "${count.textContent}"`);
    const linkVis = [...d.querySelectorAll(".mb-index a")].filter(a => !a.hidden).length;
    ok(linkVis === want.length, `the index must follow the filter: ${linkVis} links shown for ${want.length} economies`);
    ok(empty.hidden, "the empty message must stay hidden while something matches");

    type("zzzzq");
    ok(visibleNames(d).length === 0 && !empty.hidden, "no match: every section hidden and the empty message shown");
    type("");
    ok(visibleNames(d).length === n && count.textContent === "", "clearing the box restores all 62 and clears the count");

    const chips = [...d.querySelectorAll(".doc-chip")];
    const europe = chips.find(c => c.getAttribute("data-region") === "Europe");
    ok(chips.length >= 3 && chips[0].getAttribute("data-region") === "" && chips[0].classList.contains("current"), "an All chip, selected by default");
    ok(!!europe, "a Europe chip is expected");
    if (europe) {
      europe.click();
      const inEurope = [...d.querySelectorAll(".mb-econ")].filter(s => s.getAttribute("data-region") === "Europe").map(s => s.getAttribute("data-name"));
      ok(same(visibleNames(d), inEurope) && inEurope.length > 0, `Europe chip must show exactly the ${inEurope.length} European economies, shows ${visibleNames(d).length}`);
      ok(europe.classList.contains("current") && !chips[0].classList.contains("current"), "the selected chip must change");
      type("ger");
      ok(visibleNames(d).every(x => inEurope.includes(x)) && visibleNames(d).includes("Germany"), "the search and the region filter must combine");
      chips[0].click(); type("");
      ok(visibleNames(d).length === n, "All plus an empty box restores everything");
    }

    // a link to a hidden economy reveals it
    type("ger");
    ok(d.getElementById("uk").hidden, "UK should be hidden by that filter");
    w.location.hash = "#uk";
    w.dispatchEvent(new w.Event("hashchange"));
    ok(!d.getElementById("uk").hidden && input.value === "", "following a link to a hidden economy must clear the filter and show it");
  }
  // an arrival with the hash already set, for a section that exists
  {
    const {dom} = load("methodology-by-economy.html", "#germany"); await wait(500);
    ok(!dom.window.document.getElementById("germany").hidden, "arriving at #germany shows Germany");
  }
  // ------------------------------------------------------------ methodology
  {
    const {dom, errs} = load("methodology.html"); await wait(900);
    const d = dom.window.document, w = dom.window;
    ok(errs.length === 0, "methodology: script errors: " + errs.slice(0, 2).join(" | "));
    const secs = d.querySelectorAll("main .doc-sec[id]"), anchors = d.querySelectorAll(".doc-anchor");
    ok(secs.length === 8 && anchors.length === 8, `8 sections each with an anchor, found ${secs.length} and ${anchors.length}`);
    const det = [...d.querySelectorAll("details.doc-detail")];
    ok(det.length === 30 && det.every(x => !x.open), `30 closed accordions expected, found ${det.length}, open: ${det.filter(x => x.open).length}`);
    w.location.hash = "#limit-china";
    w.dispatchEvent(new w.Event("hashchange"));
    ok(d.getElementById("limit-china").open, "a link to a limitation must open its accordion");
    ok(!d.getElementById("limit-peru").open, "and only that one");
    ok(!!d.querySelector(".doc-top"), "back-to-top button missing");
  }
  {
    const {dom} = load("methodology.html", "#limit-peru"); await wait(500);
    ok(dom.window.document.getElementById("limit-peru").open, "arriving at #limit-peru opens it");
  }
  console.log(`test_doc_pages.js: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})();
