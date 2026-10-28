// Behavioural test for consent.js: Google Analytics must never load before an explicit Accept.
// Run: NODE_PATH=/tmp/node_modules node tools/test_consent.js
const fs = require("fs"), path = require("path"), { JSDOM } = require("jsdom");
const JS = fs.readFileSync(path.join(__dirname, "..", "consent.js"), "utf8");
const BANNER = '<div id="cookieBanner"><button id="cookieReject"></button><button id="cookieAccept"></button></div>';
let fails = 0, runs = 0;
function ok(c, m) { runs++; if (!c) { fails++; console.log("FAIL", m); } }
function page(stored, src) {
  const dom = new JSDOM("<!doctype html><head></head><body>" + BANNER + "</body>", { runScripts: "outside-only", url: "https://theeconomicatlas.com/indicators/x" });
  if (stored) dom.window.localStorage.setItem("eatlas_cookie_consent", stored);
  dom.window.eval(src || JS);
  return dom.window;
}
const gaScripts = w => [...w.document.querySelectorAll("script")].filter(s => /googletagmanager/.test(s.src)).length;
const shown = w => w.document.getElementById("cookieBanner").classList.contains("show");
let w = page(null);
ok(gaScripts(w) === 0 && shown(w), "no choice: GA must not load, banner must show");
w.document.getElementById("cookieAccept").click();
ok(gaScripts(w) === 1 && !shown(w) && w.localStorage.getItem("eatlas_cookie_consent") === "granted", "Accept: GA loads once, banner hides, choice saved");
w.document.getElementById("cookieAccept").click();
ok(gaScripts(w) === 1, "second Accept must not load GA twice");
w = page(null); w.document.getElementById("cookieReject").click();
ok(gaScripts(w) === 0 && !shown(w) && w.localStorage.getItem("eatlas_cookie_consent") === "denied", "Reject: no GA, banner hides, choice saved");
w = page("denied");
ok(gaScripts(w) === 0 && !shown(w), "saved denied: no GA, no banner");
w = page("granted");
ok(gaScripts(w) === 1 && !shown(w), "saved granted: GA loads, no banner");
w = page("garbage");
ok(gaScripts(w) === 0 && shown(w), "unknown saved value is treated as no choice");
// storage that throws must not crash or load GA
const dom = new JSDOM("<!doctype html><body>" + BANNER + "</body>", { runScripts: "outside-only", url: "https://theeconomicatlas.com/" });
dom.window.eval("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})");
dom.window.eval(JS);
ok(gaScripts(dom.window) === 0, "blocked storage: no GA");
// a page with no banner must not crash
const nb = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only", url: "https://theeconomicatlas.com/" });
let threw = false; try { nb.window.eval(JS); } catch (e) { threw = true; }
ok(!threw && gaScripts(nb.window) === 0, "no banner: no crash, no GA");
console.log(`consent test: ${runs} checks, ${fails} failed`);
process.exit(fails ? 1 : 0);
