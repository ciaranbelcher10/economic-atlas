#!/usr/bin/env node
/* v1.9.129: three fixes to v1.9.128. Real pages, real CSS and JS.
 *
 *   A. (i) popovers: on every country page the "Per capita:" label is drawn in the per capita glow
 *      colour, the same value the page uses for the glow on tiles (.stat.fx-pc border colour).
 *   B. Map hint: hidden on desktop (style.css), shown on phones; still in every country page's markup.
 *   C. Phone map card, homepage and all 62 country pages: starts small; the first tap only enlarges it
 *      (the tap is swallowed, so no country opens by accident); a second tap goes through; a tap
 *      elsewhere shrinks it; scrolling it fully off screen shrinks it; shrinking while it is above the
 *      reader scrolls back by the height lost, so the page does not jump; no Collapse button.
 *      On desktop none of this applies.
 *   D. Every page and the indicator page generator request style.css v63, mobile.css v48, mobile.js v45.
 *
 * Run from the repo root:  NODE_PATH=/tmp/node_modules node tools/test_v19129.js
 */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(process.env.ATLAS_ROOT || path.join(__dirname, ".."));
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
if (!fs.existsSync(NM + "jsdom/package.json")) { console.log("test_v19129: jsdom missing in " + NM); process.exit(2); }
const {JSDOM, VirtualConsole, ResourceLoader} = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; if (failures <= 40) console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
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
      w.matchMedia = q => ({matches: !!phone && /max-width/.test(q), media: q, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}});
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
const countryPages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && read(f).includes("const INFO_CONTENT = {")).sort();
const GENERATED_ROOT = new Set(["methodology-by-economy.html", "data-status.html"]);   // written by the generator on the hourly run
const allPages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && !GENERATED_ROOT.has(f) && /(style\.css|mobile\.js)\?v=/.test(read(f))).sort();
const norm = c => String(c).replace(/\s+/g, "").toLowerCase();

(async () => {
  ok(countryPages.length === 62, "expected 62 country pages, found " + countryPages.length);

  // ---------------- D. versions ----------------
  const WANT = {"style.css": "63", "mobile.css": "48", "mobile.js": "45"};
  const G = read("generate_indicator_pages.py");
  for (const [a, v] of Object.entries(WANT)) ok(G.includes("../" + a + "?v=" + v + '"'), "D: generator does not request " + a + " v" + v);
  let pinned = 0;
  for (const p of allPages) {
    const s = read(p);
    for (const [a, v] of Object.entries(WANT)) {
      const vs = [...s.matchAll(new RegExp(a.replace(".", "\\.") + "\\?v=(\\d+)", "g"))].map(m => m[1]);
      if (vs.length) { pinned++; ok(vs.every(x => x === v), "D: " + p + " requests " + a + " v" + vs.join(",") + ", want v" + v); }
    }
  }
  ok(allPages.length >= 74 && pinned >= 74 * 2, "D: only " + allPages.length + " pages, " + pinned + " asset links checked");

  // ---------------- B. map hint: phones only ----------------
  const css = read("style.css");
  const outside = css.replace(/@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, "");
  ok(/\.ea-maphint\{display:none;\}/.test(outside), "B: style.css does not hide the map hint on desktop");
  ok(!/\.ea-maphint\{[^}]*display:(block|flex)/.test(outside), "B: map hint shown outside the phone rules");
  const phoneBlock = (css.match(/@media \(max-width:700px\)\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/) || [""])[0];
  ok(/\.ea-maphint\{display:block;/.test(phoneBlock), "B: map hint not shown on phones (max-width:700px)");
  ok(!/\.ea-maphint \+ \.mini-mapwrap\{top:/.test(outside), "B: desktop map still pushed down for a hint that is hidden");
  ok(/getComputedStyle\(mh\)\.display !== "none"/.test(read("mobile.js")), "B: mobile.js still moves the map for a hidden hint");

  // ---------------- C. pill rule ----------------
  const mcss = read("mobile.css");
  ok(/\.mini-mapwrap\.mm-expanded \.minihint, \.mapwrap\.mm-collapsible\.mm-expanded \.minihint\{ display:none; \}/.test(mcss), "C: pill not hidden while the map is enlarged");
  ok(!/textContent\s*=\s*"Collapse"/.test(read("mobile.js")), "C: mobile.js still writes Collapse");

  let pops = 0, maps = 0;
  for (const p of ["index.html"].concat(countryPages)) {
    const isHome = p === "index.html";
    // ---------------- B/A on desktop ----------------
    if (!isHome) {
      const D = render(p, false);
      await wait(900);
      const hint = D.d.querySelector(".ea-maphint");
      ok(hint && D.w.getComputedStyle(hint).display === "none", p + ": map hint visible on desktop");
      const glow = (read(p).match(/\.stat\.fx-pc, \.panel\.fx-pc\{border-color:(#[0-9A-Fa-f]{6})/) || [])[1];
      ok(!!glow, p + ": per capita glow colour not found");
      const btn = D.d.querySelector(".infoBtn");
      let st = null;
      try { if (btn) { btn.dispatchEvent(new D.w.MouseEvent("click", {bubbles: true})); st = D.d.querySelector(".infoPopoverToggleNote.capita strong"); } } catch (e) {}
      ok(!!st, p + ": no Per capita label in the (i) popover " + D.errs.slice(0, 1).join(""));
      if (st && glow) { pops++; const c = D.w.getComputedStyle(st).color;
        const hex = "#" + (c.match(/\d+/g) || []).slice(0, 3).map(n => (+n).toString(16).padStart(2, "0")).join("");
        ok(norm(c) === norm(glow) || hex.toLowerCase() === glow.toLowerCase(), p + ": Per capita label colour " + c + ", glow is " + glow); }
      // the desktop map is untouched
      const dw = D.d.getElementById("miniMapWrap");
      if (dw) { dw.dispatchEvent(new D.w.MouseEvent("click", {bubbles: true, cancelable: true}));
        ok(!dw.classList.contains("mm-expanded"), p + ": desktop map picked up the phone card behaviour"); }
      D.w.close();
    }
    // ---------------- C. phone map card ----------------
    const R = render(p, true);
    await wait(isHome ? 1200 : 900);
    const w = R.w, d = R.d;
    const wrap = isHome ? d.querySelector(".mapwrap") : d.getElementById("miniMapWrap");
    if (!wrap) { ok(false, p + ": no map on the phone page"); w.close(); continue; }
    maps++;
    const big = () => wrap.classList.contains("mm-expanded");
    const tap = el => { const e = new w.MouseEvent("click", {bubbles: true, cancelable: true}); el.dispatchEvent(e); return e; };
    ok(!big(), p + ": phone map starts enlarged");
    const e1 = tap(wrap);
    ok(big(), p + ": a tap does not enlarge the phone map");
    ok(e1.defaultPrevented, p + ": the enlarging tap is not swallowed (it could open a country)");
    const e2 = tap(wrap);
    ok(big() && !e2.defaultPrevented, p + ": a second tap does not go through to the map");
    tap(d.body);
    ok(!big(), p + ": a tap elsewhere does not shrink the map (it stays enlarged)");
    const io = (w.__io || []).find(o => o.el === wrap);
    ok(!!io, p + ": the map is not watched for scrolling off screen");
    tap(wrap);
    if (io) {
      io.cb([{target: wrap, isIntersecting: true}]);
      ok(big(), p + ": shrinks while still on screen");
      // the card is above the reader: 340px tall enlarged, 130px small
      wrap.getBoundingClientRect = function () { const h = big() ? 340 : 130; return {top: -h - 50, bottom: -50, height: h, left: 0, right: 390, width: 390, x: 0, y: -h - 50}; };
      w.__scrolls.length = 0;
      io.cb([{target: wrap, isIntersecting: false}]);
      ok(!big(), p + ": scrolling the map off screen does not shrink it");
      ok(w.__scrolls.length === 1 && w.__scrolls[0][1] === -210, p + ": page not held still when the map shrinks above the reader " + JSON.stringify(w.__scrolls));
      ok(wrap.style.transition === "" || !/none/.test(wrap.style.transition), p + ": transition left switched off");
    }
    w.close();
  }
  ok(maps === 63, "C: only " + maps + " phone maps checked");
  ok(pops === 62, "A: only " + pops + " popovers checked");
  const H = render("index.html", false); await wait(800);
  const hw = H.d.querySelector(".mapwrap");
  if (hw) { hw.dispatchEvent(new H.w.MouseEvent("click", {bubbles: true, cancelable: true}));
    ok(!hw.classList.contains("mm-collapsible") && !hw.classList.contains("mm-expanded"), "C: desktop homepage map picked up the phone card"); }
  H.w.close();

  console.log(`test_v19129: ${checks} checks, ${failures} failures (${pops} popovers, ${maps} phone maps, ${allPages.length} pages)`);
  process.exit(failures ? 1 : 0);
})();
