#!/usr/bin/env node
/* v1.9.72 Dashboard on phones + country page tweaks.
 *  - two-column compact tiles (phone-scoped CSS), drag handle hidden, 44px remove hit area
 *  - Make it real / Dollarise / Export collapse into one "⋯" options button + sheet that drives the real buttons
 *  - dashboard tabs: role=tablist/tab, active tab has a "⋯" opening Rename / Delete / New, routed to sidebar controls
 *  - map replaced on phones by a ranked bar list: same countries, sorted high to low, bars sized by value
 *  - UK inactivity bar: narrow segments lose in-bar label on phones, legend carries every figure
 *  - country pages: labelled section progress ("n of N: Name"), first-visit swipe hint once only
 * Run: NODE_PATH=/tmp/node_modules node tools/test_dashboard_mobile.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const NM = process.env.NODE_PATH || "/tmp/node_modules";
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const { JSDOM, VirtualConsole } = require("jsdom");
const MOBILE_JS = fs.readFileSync(path.join(ROOT, "mobile.js"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");
const D3 = fs.readFileSync(path.join(NM, "d3/dist/d3.min.js"), "utf8");
const TOPO = fs.readFileSync(path.join(NM, "topojson/dist/topojson.min.js"), "utf8");
const sleep = ms => new Promise(r => setTimeout(r, ms));

function boot(file, opts){
  opts = opts || {};
  let html = fs.readFileSync(path.join(ROOT, file), "utf8");
  if(file === "dashboard.html") html = require("./inline_local_scripts")(html, ROOT);
  const store = Object.assign({}, opts.store || {});
  const vc = new VirtualConsole();
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc,
    url: "https://theeconomicatlas.com/" + file,
    beforeParse(win){
      win.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get(){ return function(){ return { addColorStop(){} }; }; } });
      function C(c, cfg){ this.data = (cfg && cfg.data) || { datasets: [] }; this.options = {}; }
      C.prototype.update = function(){}; C.prototype.destroy = function(){}; C.prototype.resetZoom = function(){}; C.register = function(){};
      win.Chart = C;
      win.eval(D3); win.eval(TOPO);
      Object.defineProperty(win, "localStorage", { configurable: true, value: {
        getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
        removeItem: k => { delete store[k]; }, clear(){}, key: () => null, get length(){ return 0; } } });
      win.matchMedia = () => ({ matches: true, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){} });
      win.prompt = () => null; win.confirm = () => false;
      win.fetch = u => {
        const f = String(u).split("/").pop().split("?")[0];
        const p = /countries-110m/.test(String(u)) ? path.join(NM, "world-atlas/countries-110m.json") : path.join(ROOT, f);
        if(!fs.existsSync(p)) return Promise.reject(new Error("no " + f));
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(fs.readFileSync(p, "utf8"))), text: () => Promise.resolve(fs.readFileSync(p, "utf8")) });
      };
    } });
  return { dom, store };
}
async function loaded(win, extra){
  await new Promise(r => win.addEventListener("load", r, { once: true }));
  for(let i = 0; i < 100 && extra && !extra(); i++) await sleep(50);
  await sleep(400);
  win.eval(MOBILE_JS);
  await sleep(150);
}

(async () => {
  /* ---------------- dashboard ---------------- */
  const { dom } = boot("dashboard.html");
  const win = dom.window, doc = win.document;
  await loaded(win, () => win.REGISTRY && Object.keys(win.REGISTRY).length);
  ok(win.EATLAS_DASH && typeof win.EATLAS_DASH.ensurePinned === "function", "dashboard exposes ensurePinned");
  ["UK::cpi", "US::cpi", "Japan::cpi", "Germany::cpi", "Eurozone::cpi"].forEach(id => win.EATLAS_DASH.ensurePinned(id));
  await sleep(500);

  // options button + sheet
  const optBtn = doc.getElementById("dashOptsBtn");
  ok(!!optBtn, "dashboard has one options button");
  ok(doc.querySelectorAll("#dashOptsBtn").length === 1, "options button not duplicated");
  const row = doc.querySelector(".metric-toggles");
  ok(row && row.classList.contains("dash-opts-on"), "toggles row switched to options mode on phones");
  if(optBtn){
    ok(/Options/.test(optBtn.textContent), "options button reads Options when nothing is on");
    optBtn.click();
    const sheet = doc.getElementById("eaSheet");
    ok(!!sheet && sheet.getAttribute("role") === "dialog", "options sheet opens as a dialog");
    const labels = sheet ? [...sheet.querySelectorAll(".ea-sheet-item:not(.cancel) .l")].map(x => x.textContent) : [];
    ok(labels.join("|") === "Make it real|Dollarise|Export dashboard (PNG)", "sheet offers the three actions: " + labels.join("|"));
    const realItem = sheet && sheet.querySelector(".ea-sheet-item");
    ok(realItem && realItem.getAttribute("aria-pressed") === "false", "Make it real shows off state");
    realItem && realItem.click();
    await sleep(150);
    ok(doc.getElementById("makeRealBtn").getAttribute("aria-pressed") === "true", "sheet drives the real Make it real button");
    ok(!doc.getElementById("eaSheet"), "sheet closes after an action");
    await sleep(50);
    ok(/Showing: Real/.test(optBtn.textContent), "options button reflects state: " + optBtn.textContent);
    optBtn.click();
    ok(doc.querySelector("#eaSheet .ea-sheet-item").getAttribute("aria-pressed") === "true", "sheet reopens with Make it real on");
    doc.getElementById("eaSheetBackdrop").click();
    ok(!doc.getElementById("eaSheet"), "backdrop tap closes sheet");
    doc.getElementById("makeRealBtn").click(); await sleep(100);
  }

  // ranked list
  const list = doc.getElementById("mapRankList");
  ok(!!list, "map has a ranked list twin");
  if(list){
    const rows = [...list.querySelectorAll(".map-rank-row:not(.is-na)")];
    ok(rows.length >= 3, "ranked list has rows for pinned countries (" + rows.length + ")");
    const nums = rows.map(r => parseFloat(r.querySelector(".mr-v").textContent.replace(/[^0-9.\-]/g, "")));
    ok(nums.every((v, i) => i === 0 || v <= nums[i - 1] + 1e-9), "rows sorted highest first: " + nums.join(","));
    ok(rows.every((r, i) => r.querySelector(".mr-n").textContent === String(i + 1)), "rank numbers run 1..n");
    const widths = rows.map(r => parseFloat(r.querySelector(".mr-bar i").style.width));
    ok(widths[0] === 100 || widths.some(w => w === 100), "largest value has a full bar");
    ok(widths.every(w => w >= 2 && w <= 100), "bar widths within 2..100%");
    ok(rows.every(r => r.querySelector(".mr-bar i").style.background !== ""), "bars carry the map colour");
    ok(!rows.some(r => r.dataset.country === "Eurozone"), "Eurozone (no single geography) not ranked, same as the map");
    const slider = doc.getElementById("mapYearSlider");
    if(slider && +slider.min < +slider.max){
      slider.value = String(+slider.max - 1); slider.dispatchEvent(new win.Event("input"));
      ok(doc.getElementById("mapRankList").querySelectorAll(".map-rank-row").length >= 3, "list redraws with the year slider");
    }
  }

  // tabs (logged-in shape, built by hand: sidebar item + tab per dashboard)
  const tabs = doc.getElementById("dashMobileTabs"), side = doc.getElementById("dashSidebarList");
  if(typeof win.renderSidebarAndTabs === "function" && tabs && side){
    side.innerHTML = ""; tabs.innerHTML = "";
    let renamed = 0, deleted = 0, added = 0;
    [["Main", false, true], ["Inflation watch", true, false]].forEach(([name, del, act]) => {
      const item = doc.createElement("div"); item.className = "dash-sidebar-item" + (act ? "" : " active");
      item.innerHTML = '<span class="dash-sidebar-item-name">' + name + '</span><button class="dash-sidebar-menu-btn"></button><div class="dash-sidebar-menu"></div>';
      const menu = item.querySelector(".dash-sidebar-menu");
      const r = doc.createElement("button"); r.textContent = "Rename"; r.addEventListener("click", () => renamed++); menu.appendChild(r);
      if(del){ const d = doc.createElement("button"); d.className = "danger"; d.textContent = "Delete"; d.addEventListener("click", () => deleted++); menu.appendChild(d); }
      side.appendChild(item);
    });
    const add = doc.createElement("div"); add.className = "dash-sidebar-add"; add.innerHTML = '<span class="plus">+</span> Add dashboard'; add.addEventListener("click", () => added++); side.appendChild(add);
    const t1 = doc.createElement("div"); t1.className = "dash-mobile-tab"; t1.textContent = "Main";
    const t2 = doc.createElement("div"); t2.className = "dash-mobile-tab active"; t2.textContent = "Inflation watch";
    const t3 = doc.createElement("div"); t3.className = "dash-mobile-tab dash-mobile-tab-add"; t3.textContent = "+ Add";
    tabs.append(t1, t2, t3);
    await sleep(50);
    ok(tabs.getAttribute("role") === "tablist", "tabs row is a tablist");
    ok(t1.getAttribute("role") === "tab" && t1.getAttribute("aria-selected") === "false", "inactive tab marked");
    ok(t2.getAttribute("aria-selected") === "true", "active tab selected");
    ok(!t1.querySelector(".dash-tab-more") && !!t2.querySelector(".dash-tab-more"), "only the active tab has a ⋯ button");
    ok(t2.querySelectorAll(".dash-tab-more").length === 1, "⋯ not duplicated");
    t2.querySelector(".dash-tab-more").click();
    const sh = doc.getElementById("eaSheet");
    const ls = sh ? [...sh.querySelectorAll(".ea-sheet-item:not(.cancel) .l")].map(x => x.textContent) : [];
    ok(ls.join("|") === "Rename|Delete|New dashboard", "tab sheet: " + ls.join("|"));
    ok(sh && sh.querySelector(".ea-sheet-item.danger") && /Delete/.test(sh.querySelector(".ea-sheet-item.danger").textContent), "Delete styled as danger");
    sh.querySelectorAll(".ea-sheet-item")[0].click(); ok(renamed === 1, "Rename routes to the sidebar control");
    t2.querySelector(".dash-tab-more").click(); doc.querySelectorAll("#eaSheet .ea-sheet-item")[1].click(); ok(deleted === 1, "Delete routes to the sidebar control");
    t2.querySelector(".dash-tab-more").click(); doc.querySelectorAll("#eaSheet .ea-sheet-item")[2].click(); ok(added === 1, "New dashboard routes to Add");
    // default dashboard: no Delete
    t2.classList.remove("active"); t2.querySelector(".dash-tab-more").remove(); t1.classList.add("active");
    tabs.appendChild(doc.createElement("span")); await sleep(50);
    const m1 = t1.querySelector(".dash-tab-more"); ok(!!m1, "⋯ follows the active tab");
    if(m1){ m1.click(); ok(!doc.querySelector("#eaSheet .ea-sheet-item.danger"), "default dashboard offers no Delete"); doc.getElementById("eaSheetBackdrop").click(); }
  }

  /* ---------------- UK page ---------------- */
  const uk = boot("uk.html");
  const uw = uk.dom.window, ud = uw.document;
  await loaded(uw, () => ud.querySelectorAll("#reasonBar div").length);
  const segs = [...ud.querySelectorAll("#reasonBar div")];
  ok(segs.length >= 3, "UK reasons bar rendered (" + segs.length + " segments)");
  const shares = segs.map(d => parseFloat(d.style.flex));
  const tot = shares.reduce((a, b) => a + b, 0);
  segs.forEach((d, i) => {
    const narrow = shares[i] / tot * 100 < 14;
    ok(d.classList.contains("rb-narrow") === narrow, `segment ${d.textContent} narrow=${narrow}`);
  });
  const legendVals = [...ud.querySelectorAll("#reasonLegend .rb-v")].map(b => b.textContent);
  ok(legendVals.length === segs.length && legendVals.every((v, i) => v === segs[i].textContent.trim()), "legend carries every figure: " + legendVals.join(","));
  uw.dispatchEvent(new uw.Event("resize")); await sleep(30); uw.dispatchEvent(new uw.Event("resize")); await sleep(30);
  ok([...ud.querySelectorAll("#reasonLegend span")].every(sp => sp.querySelectorAll(".rb-v").length === 1), "legend figure not duplicated after re-runs");
  const prog = ud.querySelector(".sec-progress");
  const nav = ud.querySelector("nav.cat");
  ok(!!prog, "country page has a labelled section progress");
  if(prog && nav){
    const btns = [...nav.querySelectorAll("button")];
    ok(new RegExp("^\\d+ of " + btns.length + ": ").test(prog.querySelector(".t").textContent), "progress reads n of N: " + prog.querySelector(".t").textContent);
    ok(prog.classList.contains("first-visit") && /Swipe left or right/.test(prog.textContent), "first visit shows the swipe hint");
    ok(uk.store.ea_swipe_hint_seen === "1", "hint marked as seen");
    const target = btns[2];
    if(target && typeof uw.showSec === "function"){
      uw.showSec(target.dataset.sec); await sleep(50);
      ok(prog.querySelector(".t").textContent.indexOf("3 of " + btns.length + ": " + target.textContent.trim()) === 0, "progress follows the active section");
    }
    ok(ud.querySelectorAll(".sec-progress").length === 1, "progress not duplicated");
  }
  const uk2 = boot("uk.html", { store: { ea_swipe_hint_seen: "1" } });
  await loaded(uk2.dom.window);
  const p2 = uk2.dom.window.document.querySelector(".sec-progress");
  ok(p2 && !p2.classList.contains("first-visit") && !/Swipe/.test(p2.textContent), "hint not shown on later visits");

  /* ---------------- CSS ---------------- */
  const start = CSS.indexOf("@media (max-width:760px){", 140);
  ["\\.dashgrid\\{", "\\.dash-opts-btn\\{", "\\.map-rank\\{", "\\.ea-sheet-item\\{", "\\.sec-progress\\{", "\\.reasonbar div\\.rb-narrow"].forEach(sel => {
    const i = CSS.search(new RegExp(sel));
    ok(i > start && start > 0, sel + " is phone-scoped");
  });
  const rule = sel => { const m = CSS.match(new RegExp(sel.replace(/[.#()]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
  ok(/repeat\(2, minmax\(0,1fr\)\)/.test(rule("  .dashgrid")), "two shrinkable tile columns");
  ok(/min-height:44px/.test(rule("  .dash-opts-btn")), "options button 44px");
  ok(/min-height:48px/.test(rule("  .ea-sheet-item")), "sheet items 48px");
  ok(/min-height:44px/.test(rule("  .metric-toggles .mtoggle")), "toggles 44px");
  ok(/inset:-11px/.test(rule("  .tile .remove::before")), "remove button has a 44px hit area");
  ok(/inset:-6px/.test(rule("  .dash-tab-more::before")) && /width:32px/.test(rule("  .dash-tab-more")), "tab ⋯ hit area 44px");
  ok(/display:none !important/.test(rule("  #mapSvgWrap, #mapCard .legend-grad, #heatTip")), "map hidden on phones");
  const dhtml = fs.readFileSync(path.join(ROOT, "dashboard.html"), "utf8");
  ok(/\.map-rank\{display:none;\}/.test(dhtml), "ranked list hidden on desktop");
  ok(/mobile\.css\?v=20/.test(dhtml) && /mobile\.js\?v=22/.test(dhtml), "dashboard on mobile.css v20 / mobile.js v22");

  console.log(`test_dashboard_mobile: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.message); console.log(`test_dashboard_mobile: ${checks - failures} ok, ${failures + 1} failed`); process.exit(1); });
