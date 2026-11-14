#!/usr/bin/env node
/* v1.9.128: y-axis labels, (i) popovers, map hint. Real pages, real data files, real Chart.js.
 *
 *   A. Axis: every indicator page (indicators/*.html) at Max, 10Y, 5Y and 1Y, and every chart on every
 *      country page, has y-axis labels that all differ (China's population read "1.4bn" five times).
 *   B. (i): on every country page, every (i) popover, with Per capita off and on, shows no old toggle
 *      name ("Make it real", "Dollarise") and has a "Per capita:" paragraph; an eligible currency series
 *      explains the division, and says "On now" when the switch is on; Taiwan says not available.
 *      Dashboard and Compare popovers carry the same paragraph.
 *   C. Map hint: the homepage's sentence, word for word, directly above the map on every country page;
 *      on a phone the homepage map starts collapsed with an "Expand" pill and a tap expands it.
 *   D. EA_axisTick is the same function in percapita.js and indicator-kit.js.
 *
 * Needs jsdom 24 and chart.js in NODE_PATH (one-command install, see DEPLOY).
 * Run from the repo root:  NODE_PATH=/tmp/node_modules node tools/test_v19128.js
 * EA_SAMPLE=n checks every n-th indicator page only (mutation runs); default is all of them.
 */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(process.env.ATLAS_ROOT || path.join(__dirname, ".."));
const NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
if (!fs.existsSync(NM + "jsdom/package.json") || !fs.existsSync(NM + "chart.js/dist/chart.umd.js")) {
  console.log("test_v19128: jsdom or chart.js missing in " + NM); process.exit(2); }
const {JSDOM, VirtualConsole, ResourceLoader} = require(NM + "jsdom");
const SAMPLE = Math.max(1, +(process.env.EA_SAMPLE || 1));
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if (!c) { failures++; if (failures <= 40) console.log("  FAIL  " + m); } };
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const HINT = "All 62 economies. Tap or click a coloured country to open its data.";
{ /* generated indicator pages must request the changed kit and percapita builds, or caches serve the old axis and popover code */
  const G = read("generate_indicator_pages.py");
  ok(/^KIT_VERSION = "13"$/m.test(G), "G: generator KIT_VERSION is not 13 (indicator-kit.js changed in v1.9.128)");
  ok(/^PERCAPITA_VERSION = "5"$/m.test(G), "G: generator PERCAPITA_VERSION is not 5 (percapita.js changed in v1.9.128)"); }

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
      w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      try { w.localStorage.setItem("eatlas_consent", "denied"); } catch (e) {}
    }});
  return {dom, w: dom.window, d: dom.window.document, errs};
}
const wait = ms => new Promise(r => setTimeout(r, ms));
function yLabels(chart) {
  const y = chart && chart.scales && (chart.scales.y || Object.values(chart.scales).find(s => s.axis === "y"));
  return y && y.options.display !== false && y.ticks ? y.ticks.map(t => t.label).filter(l => l !== "" && l != null).map(String) : null;
}
const dups = ls => ls.filter((l, i) => ls.indexOf(l) !== i);

const pc = require(path.join(ROOT, "percapita.js"));
const countryPages = fs.readdirSync(ROOT).filter(f => /\.html$/.test(f) && read(f).includes("const INFO_CONTENT = {")).sort();

(async () => {
  // ---------------- D. one EA_axisTick ----------------
  const fnOf = src => { const m = /function EA_axisTick\(fmt, v, i, ticks\)\{[\s\S]*?\n\s*return out\[i\];\n\s*\}/.exec(src); return m ? m[0].replace(/^\s+/gm, "") : null; };
  const a1 = fnOf(read("percapita.js")), a2 = fnOf(read("indicator-kit.js"));
  ok(a1 && a2 && a1 === a2, "D: EA_axisTick differs between percapita.js and indicator-kit.js");
  ok(/callback: function\(v, i, t\)\{[^}]*\}[\s\S]{0,40}return EA_axisTick\(f, v, i, t\);/.test(read("indicator-kit.js")), "D: indicator page y-axis callback does not use EA_axisTick");
  // unit cases, through the real function
  const t5 = [1.406e9, 1.408e9, 1.410e9, 1.412e9, 1.414e9].map(v => ({value: v}));
  const bn = v => (v / 1e9).toFixed(1) + "bn";
  ok(dups(t5.map((t, i) => pc.axisTick(bn, t.value, i, t5))).length === 0, "D: 1.406bn to 1.414bn still duplicates");
  const pct = [{value: -0.04}, {value: -0.02}, {value: 0}, {value: 0.02}].map(x => x);
  const pf = v => (v < 0 ? "−" : "") + Math.abs(v).toFixed(1) + "%";
  const pl = pct.map((t, i) => pc.axisTick(pf, t.value, i, pct));
  ok(dups(pl).length === 0 && pl[0].startsWith("−") && pl[2] === "0.0%", "D: percent axis wrong: " + pl.join(","));
  const fine = [{value: 1e9}, {value: 2e9}];
  ok(pc.axisTick(bn, 1e9, 0, fine) === "1.0bn", "D: labels that already differ must be left alone");

  // ---------------- A1. indicator pages ----------------
  const inds = fs.readdirSync(path.join(ROOT, "indicators")).filter(f => /\.html$/.test(f)).sort().filter((_, i) => i % SAMPLE === 0);
  let rendered = 0, axes = 0;
  for (const f of inds) {
    const p = "indicators/" + f;
    const R = render(p);
    await wait(60);
    const canvas = R.d.getElementById("indChart");
    if (!canvas) { R.w.close(); continue; }
    rendered++;
    const btns = [...R.d.querySelectorAll("[data-range]")];
    for (const b of btns) {
      b.click();
      const ls = yLabels(R.w.Chart && R.w.Chart.getChart(canvas));
      ok(!!ls, p + " [" + b.dataset.range + "]: no chart drawn " + R.errs.slice(0, 1).join(""));
      if (!ls) continue;
      axes++;
      ok(dups(ls).length === 0, p + " [" + b.dataset.range + "]: repeated y labels " + ls.join(" | "));
    }
    R.w.close();
  }
  ok(rendered >= Math.floor(1000 / SAMPLE), "A1: only " + rendered + " indicator pages drew a chart");

  // ---------------- A2 + B + C1. country pages ----------------
  const hintIdx = /<p class="home-mapcap">([^<]*)<\/p>/.exec(read("index.html"));
  ok(hintIdx && hintIdx[1] === HINT, "C: homepage map caption is not the agreed sentence");
  let popovers = 0, cAxes = 0;
  for (const p of countryPages) {
    const src = read(p);
    ok(src.split(HINT).length === 2, p + ": map hint missing or repeated");
    ok(src.includes('<p class="home-mapcap ea-maphint">' + (hintIdx ? hintIdx[1] : "") + '</p>\n<div class="mini-mapwrap" id="miniMapWrap"'),
       p + ": hint is not the homepage sentence directly above the map");
    const R = render(p);
    await wait(900);
    const {w, d} = R;
    ok(d.getElementById("loadFail") && d.getElementById("loadFail").hidden, p + ": page failed to load " + R.errs.slice(0, 2).join(" | "));
    // A2: every chart drawn on the page
    for (const ch of Object.values(w.Chart ? w.Chart.instances : {})) {
      const ls = yLabels(ch); if (!ls || ls.length < 2) continue;
      cAxes++;
      ok(dups(ls).length === 0, p + " chart " + (ch.canvas && ch.canvas.id) + ": repeated y labels " + ls.join(" | "));
    }
    // B: every (i)
    const keys = [...new Set([...d.querySelectorAll(".infoBtn[data-infokey]")].map(b => b.dataset.infokey))];
    ok(keys.length > 0, p + ": no (i) buttons rendered");
    const noPop = w.eval("typeof pcPopulation === 'function' ? !pcPopulation().length : null");
    for (const on of [false, true]) {
      w.eval("TOGGLE_STATE.capita = " + (on && !noPop));
      for (const k of keys) {
        const btn = d.querySelector('.infoBtn[data-infokey="' + k + '"]');
        w.openInfoPopover(btn, k, k);
        const box = d.querySelector(".infoPopover"); popovers++;
        const text = box ? box.textContent : "";
        ok(!/Make it real|Dollari[sz]e/.test(text), p + " (i) " + k + ": old toggle name shown");
        const pcp = box && box.querySelector(".infoPopoverToggleNote.capita");
        ok(!!pcp && /^Per capita:/.test(pcp.textContent), p + " (i) " + k + ": no Per capita paragraph");
        if (!pcp) continue;
        const unit = (((w.eval("PAGE_DATA").series || {})[k]) || {}).unit;
        const amount = pc.eligible(k) && /(m|bn|tn)$/.test(String(unit || "").replace(/\s*\(.*\)\s*$/, "").trim());
        if (noPop && amount) ok(/Not available for this economy/.test(pcp.textContent), p + " (i) " + k + ": should say Per capita is not available");
        else if (amount) {
          ok(/Divides each value by that year/.test(pcp.textContent), p + " (i) " + k + ": Per capita paragraph does not explain the division");
          ok(/On now/.test(pcp.textContent) === on, p + " (i) " + k + ": 'On now' should be " + on);
        } else ok(/no (further )?effect/.test(pcp.textContent), p + " (i) " + k + " (" + unit + "): should say Per capita has no effect");
      }
    }
    w.close();
  }
  ok(countryPages.length === 62, "B: expected 62 country pages, found " + countryPages.length);
  ok(cAxes >= 62 * 5, "A2: only " + cAxes + " country page axes checked");
  ok(countryPages.includes("taiwan.html"), "B: Taiwan page missing");

  // B2: Dashboard and Compare popovers
  const dash = read("dashboard.html"), cmp = read("compare.html");
  {
    const D = render("dashboard.html");
    await wait(2500);
    let shown = "";
    try {
      // Dashboard tiles are the viewer's own picks, so the test adds one (i) the way the page writes it
      const btn = D.d.createElement("button");
      btn.className = "infoBtn"; btn.dataset.country = "Slovenia"; btn.dataset.key = "gdp_level";
      D.d.body.appendChild(btn);
      btn.dispatchEvent(new D.w.MouseEvent("click", {bubbles: true}));
      shown = D.d.querySelector(".infoPopoverToggleCaveats").textContent;
    } catch (e) { shown = "error: " + e.message + " " + D.errs.slice(0, 2).join(" | "); }
    ok(/Per capita: (Divides each value|Not available)/.test(shown) && !/Make it real|Dollari[sz]e/.test(shown), "B2: Dashboard GDP (i) text: " + shown.slice(0, 160));
    D.w.close();
  }
  ok(/EA_PC\.infoNote\(key, \{\s*unit: s3 \? s3\.unit : undefined, noPopulation: !pcPopulation\(country\)\.length, on: !!perCapita \}\)/.test(dash), "B2: Dashboard (i) has no Per capita paragraph");
  ok(/EA_PC\.infoNote\(concept, \{on: typeof percapOn === "function" && percapOn\(concept\)\}\)/.test(cmp), "B2: Compare (i) has no Per capita paragraph");
  ok(pc.relabel("“Make it real” and “Dollarise”") === "“Adjust for inflation” and “Convert to USD$”", "B2: relabel wrong");
  ok(/no effect/.test(pc.infoNote("deficit", {unit: "% of GDP"})) && /Divides/.test(pc.infoNote("deficit", {unit: "£bn"})), "B2: deficit as % of GDP vs £bn");

  // ---------------- C2. homepage map on a phone ----------------
  const H = render("index.html", true);
  await wait(1200);
  const mw = H.d.querySelector(".mapwrap");
  ok(mw && mw.classList.contains("mm-collapsible") && !mw.classList.contains("mm-expanded"), "C2: phone homepage map does not start collapsed");
  const pill = mw && mw.querySelector(".minihint");
  ok(pill && /^Expand/.test(pill.textContent), "C2: no Expand pill on the phone homepage map");
  ok(mw && mw.querySelector(".home-mapcap") && mw.firstElementChild.classList.contains("home-mapcap"), "C2: hint is not above the map");
  if (mw) mw.dispatchEvent(new H.w.MouseEvent("click", {bubbles: true}));
  ok(mw && mw.classList.contains("mm-expanded"), "C2: a tap does not expand the phone homepage map");
  ok(pill && pill.textContent === "Collapse", "C2: pill does not change to Collapse, as on the country pages");
  const mcss = read("mobile.css");
  ok(/\.mapwrap\.mm-collapsible\{ max-height:190px;/.test(mcss) && /\.mapwrap\.mm-collapsible\.mm-expanded\{ max-height:1200px; \}/.test(mcss), "C2: mobile.css collapse rules missing");
  H.w.close();
  const Hd = render("index.html", false);
  await wait(800);
  ok(!Hd.d.querySelector(".mapwrap").classList.contains("mm-collapsible"), "C2: desktop homepage map must not collapse");
  Hd.w.close();

  console.log(`test_v19128: ${checks} checks, ${failures} failures (${rendered} indicator pages, ${axes} indicator axes, ${cAxes} country axes, ${popovers} popovers)`);
  process.exit(failures ? 1 : 0);
})();
