#!/usr/bin/env node
/* v1.9.130: the phone map card moves smoothly. Real pages, real mobile.js.
 *
 *   A. Enlarging animates the card's real height: it starts from the small height, runs to the
 *      measured full height on a 0.3s max-height transition, and hands back to the stylesheet when
 *      the transition ends (no inline max-height left behind).
 *   B. A tap elsewhere shrinks it the same way, full height down to the small height.
 *   C. Scrolling it off screen shrinks it instantly (no animation), still holding the page still.
 *   D. Reduced motion: no animation at all.
 *   E. mobile.css: no max-height transition left on the cards; legend and zoom hint fade in;
 *      reduced motion switches the fade off. Pages and the generator request mobile.css v49, mobile.js v46.
 * Homepage and a sample of country pages.
 * Run from the repo root:  NODE_PATH=/tmp/node_modules node tools/test_v19130.js
 */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(process.env.ATLAS_ROOT || path.join(__dirname, ".."));
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
if (!fs.existsSync(NM + "jsdom/package.json")) { console.log("test_v19130: jsdom missing in " + NM); process.exit(2); }
const {JSDOM, VirtualConsole, ResourceLoader} = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; if (failures <= 40) console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
let REDUCED = false;
const LIB = {"d3.min.js": "d3/dist/d3.min.js", "chart.umd.min.js": "chart.js/dist/chart.umd.js", "topojson.min.js": "topojson/dist/topojson.min.js",
             "hammer.min.js": "hammerjs/hammer.min.js", "chartjs-plugin-zoom.min.js": "chartjs-plugin-zoom/dist/chartjs-plugin-zoom.min.js"};
const SUPA = "window.supabase={createClient:function(){var q={select:function(){return q},eq:function(){return q},order:function(){return q},maybeSingle:function(){return Promise.resolve({data:null})},then:function(r){return Promise.resolve({data:null}).then(r)}};return {from:function(){return q},functions:{invoke:function(){return Promise.resolve({data:null})}},auth:{getSession:function(){return Promise.resolve({data:{session:null}})},onAuthStateChange:function(){return {data:{subscription:{unsubscribe:function(){}}}}}}}}};";
class Loader extends ResourceLoader {
  fetch(url) {
    const b = url.split("/").pop().split("?")[0];
    if (LIB[b] && fs.existsSync(NM + LIB[b])) return Promise.resolve(fs.readFileSync(NM + LIB[b]));
    if (/supabase/.test(url)) return Promise.resolve(Buffer.from(SUPA));
    if (/^https:\/\/example\.test\//.test(url)) {
      const f = path.join(ROOT, decodeURIComponent(new URL(url).pathname));
      if (fs.existsSync(f)) return Promise.resolve(fs.readFileSync(f));
    }
    return Promise.resolve(Buffer.from(""));
  }
}
process.on("unhandledRejection", () => {});
function render(p, phone) {
  const vc = new VirtualConsole(), errs = [];
  vc.on("jsdomError", e => errs.push(String(e.message || e).split("\n")[0]));
  const dom = new JSDOM(read(p), {runScripts: "dangerously", resources: new Loader(), url: "https://example.test/" + p,
    virtualConsole: vc, pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u) => { u = String(u);
        if (/countries-110m\.json/.test(u)) return Promise.resolve({ok: true, json: () => Promise.resolve(JSON.parse(fs.readFileSync(NM + "world-atlas/countries-110m.json")))});
        const rel = /^https?:/.test(u) ? (u.startsWith("https://example.test/") ? new URL(u).pathname : null)
                                       : path.posix.join(path.posix.dirname("/" + p), u.split("?")[0]);
        const f = rel && path.join(ROOT, rel);
        if (!f || !fs.existsSync(f)) return Promise.resolve({ok: false, status: 404, json: () => Promise.reject(new Error("404")), text: () => Promise.reject(new Error("404"))});
        const t = fs.readFileSync(f, "utf8");
        return Promise.resolve({ok: true, status: 200, json: () => Promise.resolve(JSON.parse(t)), text: () => Promise.resolve(t)}); };
      w.matchMedia = q => ({matches: /reduced-motion/.test(q) ? REDUCED : !!phone && /max-width/.test(q), media: q, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
      w.scrollTo = () => {};
      // A canvas context Chart.js can lay out ticks with: text 6px per character, everything else a no-op
      w.HTMLCanvasElement.prototype.getContext = function () {
        const cv = this;
        return new Proxy({}, {get(t, k) {
          if (k === "canvas") return cv;
          if (k === "measureText") return s => ({width: String(s).length * 6});
          if (k === "createLinearGradient" || k === "createRadialGradient" || k === "createPattern") return () => ({addColorStop() {}});
          if (k === "getImageData") return () => ({data: []});
          if (k in t) return t[k];
          return () => {};
        }, set(t, k, v) { t[k] = v; return true; }});
      };
      const W = phone ? 390 : 1200;
      Object.defineProperty(w.HTMLElement.prototype, "clientWidth", {get() { return W; }});
      Object.defineProperty(w.HTMLElement.prototype, "clientHeight", {get() { return 320; }});
      w.Element.prototype.getBoundingClientRect = function () { return {x: 0, y: 0, top: 0, left: 0, right: W, bottom: 320, width: W, height: 320}; };
      w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.__io = []; w.IntersectionObserver = class { constructor(cb) { this.cb = cb; w.__io.push(this); } observe(el) { this.el = el; } unobserve() {} disconnect() {} };
      w.__scrolls = []; w.scrollBy = (x, y) => w.__scrolls.push([x, y]);
      try { w.localStorage.setItem("eatlas_consent", "denied"); } catch (e) {}
    }});
  return {dom, w: dom.window, d: dom.window.document, errs};
}
const wait = ms => new Promise(r => setTimeout(r, ms));
const GENERATED_ROOT = new Set(["methodology-by-economy.html", "data-status.html"]);
const PAGES = ["index.html", "uk.html", "us.html", "germany.html", "japan.html", "slovenia.html", "taiwan.html", "newzealand.html"];

// the card's height as a browser would lay it out: 340px enlarged, 130px small, capped by any inline max-height
function sizeCard(w, wrap, log) {
  const px = v => /px$/.test(v) ? parseFloat(v) : Infinity;
  wrap.getBoundingClientRect = function () {
    const nat = wrap.classList.contains("mm-expanded") ? 340 : 130;
    const h = Math.min(nat, px(wrap.style.maxHeight));
    return {top: 100, bottom: 100 + h, height: h, left: 0, right: 390, width: 390, x: 0, y: 100};
  };
  const st = wrap.style, desc = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(st), "maxHeight") || {};
  let cur = "";
  Object.defineProperty(st, "maxHeight", {configurable: true, get() { return cur; }, set(v) { cur = String(v); log.push(cur); }});
}
const endTransition = (w, wrap) => { const e = new w.Event("transitionend", {bubbles: true}); e.propertyName = "max-height"; wrap.dispatchEvent(e); };

(async () => {
  // ---------------- E. stylesheet and versions ----------------
  const mcss = read("mobile.css");
  const cardRule = (mcss.match(/\n  \.mini-mapwrap\{[^}]*\}/) || [""])[0];
  ok(/transition:none/.test(cardRule) && !/max-height \.25s/.test(cardRule), "E: country map card still on the old max-height transition");
  ok(/\.mapwrap\.mm-collapsible\{[^}]*transition:none;/.test(mcss), "E: homepage map card still on the old max-height transition");
  ok(/@keyframes eaMapFade\{ from\{ opacity:0; \} to\{ opacity:1; \} \}/.test(mcss) && /\.mapwrap\.mm-collapsible\.mm-expanded \.legend\{ animation:eaMapFade \.25s ease \.2s both; \}/.test(mcss), "E: legend and zoom hint do not fade in");
  ok(/@media \(prefers-reduced-motion: reduce\)\{\s*\.mini-mapwrap\.mm-expanded \.zoomhint[^}]*\{ animation:none; \}/.test(mcss), "E: reduced motion does not switch the fade off");
  const G = read("generate_indicator_pages.py");
  ok(G.includes('../mobile.css?v=49"') && G.includes('../mobile.js?v=46"'), "E: generator does not request mobile.css v49 and mobile.js v46");
  let pinned = 0;
  for (const p of fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && !GENERATED_ROOT.has(f))) {
    const s = read(p);
    for (const [a, v] of [["mobile.css", "49"], ["mobile.js", "46"]]) {
      const vs = [...s.matchAll(new RegExp(a.replace(".", "\\.") + "\\?v=(\\d+)", "g"))].map(m => m[1]);
      if (vs.length) { pinned++; ok(vs.every(x => x === v), "E: " + p + " requests " + a + " v" + vs.join(",")); }
    }
  }
  ok(pinned >= 140, "E: only " + pinned + " asset links checked");

  let cards = 0;
  for (const p of PAGES) {
    for (const reduced of [false, true]) {
      REDUCED = reduced;
      const R = render(p, true);
      await wait(p === "index.html" ? 1200 : 900);
      const w = R.w, d = R.d;
      const wrap = p === "index.html" ? d.querySelector(".mapwrap") : d.getElementById("miniMapWrap");
      if (!wrap) { ok(false, p + ": no phone map"); w.close(); continue; }
      cards++;
      const log = []; sizeCard(w, wrap, log);
      const tag = p + (reduced ? " (reduced motion)" : "");
      const tap = el => el.dispatchEvent(new w.MouseEvent("click", {bubbles: true, cancelable: true}));
      // A. enlarge
      tap(wrap);
      if (!reduced) {
        ok(log.includes("130px") && log.indexOf("130px") < log.lastIndexOf("340px"), tag + ": enlarging does not run from 130px to 340px " + JSON.stringify(log));
        ok(wrap.style.maxHeight === "340px" && /max-height \.3s/.test(wrap.style.transition), tag + ": no 0.3s max-height transition while enlarging (" + wrap.style.maxHeight + ", " + wrap.style.transition + ")");
        endTransition(w, wrap);
        ok(wrap.style.maxHeight === "" && wrap.style.transition === "", tag + ": inline height left behind after enlarging");
      } else {
        ok(wrap.style.maxHeight === "" && !log.includes("340px"), tag + ": animates despite reduced motion " + JSON.stringify(log));
      }
      ok(wrap.classList.contains("mm-expanded"), tag + ": not enlarged");
      // B. tap elsewhere
      log.length = 0;
      tap(d.body);
      ok(!wrap.classList.contains("mm-expanded"), tag + ": a tap elsewhere does not shrink it");
      if (!reduced) {
        ok(log.indexOf("340px") > -1 && log.indexOf("340px") < log.lastIndexOf("130px") && wrap.style.maxHeight === "130px", tag + ": shrinking does not run from 340px to 130px " + JSON.stringify(log));
        await wait(500);   // no transitionend this time: the fallback timer must still tidy up
        ok(wrap.style.maxHeight === "" && wrap.style.transition === "", tag + ": inline height left behind after shrinking");
      } else ok(wrap.style.maxHeight === "", tag + ": animates the shrink despite reduced motion");
      // C. off screen: instant
      tap(wrap); endTransition(w, wrap);
      const io = (w.__io || []).find(o => o.el === wrap);
      log.length = 0;
      if (io) io.cb([{target: wrap, isIntersecting: false}]);
      ok(io && !wrap.classList.contains("mm-expanded"), tag + ": scrolling off screen does not shrink it");
      ok(!log.some(v => /\d/.test(v)) && !/max-height \.3s/.test(wrap.style.transition), tag + ": off-screen shrink is animated " + JSON.stringify(log));
      w.close();
    }
  }
  ok(cards === PAGES.length * 2, "only " + cards + " cards checked");
  console.log(`test_v19130: ${checks} checks, ${failures} failures (${cards} phone map cards)`);
  process.exit(failures ? 1 : 0);
})();
