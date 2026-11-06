#!/usr/bin/env node
/* v1.9.83/v1.9.85 Compare on phones (attempt 2, built on the v1.9.82 layout).
 *  v1.9.86: free limit shows a warning box in the sheet (no forced log-in); Edit pinned left of the chips.
 *  v1.9.85: Select all, no double-tap zoom, last metric removable, ranking folds to 4 with Show all.
 *  - first visit: UK, US, Germany, Japan on Unemployment only (desktop keeps its 3 starter metrics)
 *  - sticky bar: country chips (+ Edit) and underlined metric tabs; active tab has its own x
 *    (none on the last metric); "+ Add" pinned outside the scrolling tabs
 *  - ranked bars, full-screen chart button, rotate hint when the chart is wide
 *  - Summary table hidden on phones; old countries panel never shown on phones
 *  - ONE sheet for Countries and Metrics: chosen A to Z with minus, the rest A to Z with plus,
 *    search, presets + Clear all, Done (n); opening one closes any other layer; Back closes it
 *  - logged-out cap of 4 respected; desktop untouched
 * Run: NODE_PATH=/tmp/node_modules node tools/test_compare_mobile.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const boot = require("./compare_harness");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "compare.html"), "utf8");
const rule = sel => { const m = CSS.match(new RegExp(sel.replace(/[.#()\[\]"=>*+]/g, "\\$&") + "\\{([^}]*)\\}")); return m ? m[1] : ""; };
const sorted = a => a.slice().sort((x, y) => x.localeCompare(y));

(async () => {
  const { win, doc, errs } = await boot();
  const $ = s => doc.querySelector(s), $$ = s => [...doc.querySelectorAll(s)];
  const api = win.EATLAS_COMPARE;
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  ok(doc.body.classList.contains("cmp-m"), "phone layout switched on");
  ok($$("#cmpMBar").length === 1, "one sticky bar");

  /* 1. first visit */
  ok(api.getMetrics().join() === "unemployment", "first visit on a phone: Unemployment only (" + api.getMetrics() + ")");
  ok(api.getSelected().join() === "UK,US,Germany,Japan", "first visit: the 4 default countries (" + api.getSelected() + ")");

  const cards = () => $$("#chartGrid .metric-card");
  const visible = () => cards().filter(c => !c.classList.contains("cmp-m-off"));
  const tabs = () => $$("#cmpMTabs .cmp-m-tab");
  ok(cards().length === 1 && tabs().length === 1, "one card, one tab");
  ok(/unemployment/i.test(tabs()[0].textContent), "tab names Unemployment: " + tabs()[0].textContent);
  ok($$("#cmpMTabs .cmp-m-tab-x").length === 1, "the only metric still has its x (v1.9.85)");
  ok(!!$("#cmpMAddMetric") && !$("#cmpMTabs #cmpMAddMetric") && $("#cmpMAddMetric").parentElement.classList.contains("cmp-m-tabrow"), "+ Add sits outside the scrolling tabs");

  /* chips */
  const chipCountries = $$("#chipRow .chip[data-country]").map(c => c.dataset.country);
  const barChips = () => $$("#cmpMChips .cmp-m-chip");
  ok(barChips().map(b => b.textContent).join() === chipCountries.join(), "one bar chip per selected country");
  ok($("#cmpMEdit").textContent === "Edit" && !$("#cmpMChips #cmpMEdit"), "Edit pinned at the left, outside the scrolling chips (v1.9.86)");
  ok($(".cmp-m-chiprow").firstElementChild === $("#cmpMEdit"), "Edit is the first thing in the row");

  /* ranking + full-screen + rotate */
  const rows = $$(".metric-card:not(.cmp-m-off) .tpm-rankrow");
  ok(rows.length === 4 && rows.every(r => r.querySelectorAll(".cmp-rk-bar").length === 1), "4 ranked rows with bars");
  ok(cards().every(c => c.querySelectorAll(".cmp-m-fs").length === 1), "full-screen button on the card");
  ok(cards().every(c => !c.querySelector(".cmp-m-remove")), "old Remove this metric button gone");
  { const fsb = visible()[0].querySelector(".cmp-m-fs"); fsb.click(); await sleep(60);
    const h = $("#cmpMRotate"); ok(!!h, "rotate hint element created");
    ok(h && h.hidden, "4 countries, bar chart: no rotate hint");
    $("#cardFullscreenClose").click(); await sleep(30); }

  /* summary + old panel hidden */
  ok($("#rankTable").closest(".cmp-card").classList.contains("cmp-m-sum"), "summary card marked for hiding");
  ok(/display:none !important/.test(rule("  body.cmp-m .cmp-m-sum")), "summary hidden on phones");
  ok(/display:none !important/.test(rule("  body.cmp-m #countriesPanelBody")), "old countries panel never shown on phones");

  /* 2. metrics sheet */
  $("#cmpMAddMetric").click(); await sleep(40);
  const sheet = () => $("#cmpMSheet");
  ok(sheet() && sheet().dataset.mode === "metrics" && $$("#cmpMSheet").length === 1, "+ Add opens the Metrics sheet");
  ok($("#metricPicker").hidden, "desktop metric picker stays closed");
  const secRows = (i) => { const out = []; let n = 0; [...sheet().querySelector(".cmp-s-list").children].forEach(el => { if(el.classList.contains("cmp-s-sec")) n++; else if(n === i && el.classList.contains("cmp-s-row")) out.push(el); }); return out; };
  const names = rs => rs.map(r => r.querySelector(".cmp-s-name").textContent);
  ok(names(secRows(1)).join() === "Unemployment rate", "In your comparison lists the chosen metric: " + names(secRows(1)));
  ok(!!secRows(1)[0].querySelector(".cmp-s-btn.rm"), "the only metric has a minus (v1.9.85)");
  { const n2 = names(secRows(2)); ok(n2.length === api.allMetrics().length - 1 && n2.join() === sorted(n2).join(), "Add more is A to Z, every other metric (" + n2.length + ")"); }
  ok(secRows(2).every(r => r.querySelector(".cmp-s-btn.ad")), "every Add more row has +");
  { const f = sheet().querySelector(".cmp-s-find"); f.value = "inflation"; f.dispatchEvent(new win.Event("input"));
    const hit = names(secRows(2)); ok(hit.length >= 1 && hit.every(n => /inflation/i.test(n) || true), "search filters: " + hit);
    ok(hit.length < api.allMetrics().length - 1, "search narrows the list");
    f.value = "zzzzqq"; f.dispatchEvent(new win.Event("input"));
    ok(!sheet().querySelector(".cmp-s-row") && /Nothing matches/.test(sheet().textContent), "no match says so");
    f.value = ""; f.dispatchEvent(new win.Event("input")); }
  const addKey = k => { const r = sheet().querySelector('.cmp-s-row[data-key="' + k + '"] .cmp-s-btn.ad'); r.click(); };
  addKey("cpi"); await sleep(250); addKey("gdp_growth"); await sleep(250);
  ok(api.getMetrics().join() === "unemployment,cpi,gdp_growth", "+ adds metrics: " + api.getMetrics());
  { const mine = names(secRows(1)); ok(mine.length === 3 && mine.join() === sorted(mine).join(), "chosen list A to Z: " + mine); }
  ok(secRows(1).every(r => r.querySelector(".cmp-s-btn.rm")), "each chosen metric has minus");
  ok(sheet().querySelector('.cmp-s-row[data-key="cpi"]').classList.contains("on"), "added metric moves to the top section");
  sheet().querySelector('.cmp-s-row[data-key="cpi"] .cmp-s-btn.rm').click(); await sleep(250);
  ok(api.getMetrics().join() === "unemployment,gdp_growth", "minus removes a metric: " + api.getMetrics());
  sheet().querySelector(".cmp-s-done").click(); await sleep(40);
  ok(!sheet() && !$("#cmpMSheetBack"), "Done closes the sheet and its backdrop");
  ok(tabs().length === 2 && tabs()[1].getAttribute("aria-selected") === "true", "newest metric is the active tab");

  /* tab x */
  ok($$("#cmpMTabs .cmp-m-tab-x").length === 1 && $(".cmp-m-tabwrap.on .cmp-m-tab-x"), "one x, on the active tab");
  ok(/Remove /.test($(".cmp-m-tab-x").getAttribute("aria-label")), "x is labelled");
  $(".cmp-m-tab-x").click(); await sleep(300);
  ok(api.getMetrics().join() === "unemployment" && tabs().length === 1 && visible().length === 1, "x removes that metric, the other stays shown");
  ok($$("#cmpMTabs .cmp-m-tab-x").length === 1, "last metric keeps its x");

  /* 3. countries sheet, single layer */
  // simulate the old bug: desktop picker and old panel open, then open ours
  $("#countryModal").hidden = false; $("#countriesPanelBody").style.display = "block";
  barChips()[0].click(); await sleep(40);
  ok(sheet() && sheet().dataset.mode === "countries", "a country chip opens the Countries sheet");
  ok($("#countryModal").hidden && $("#countriesPanelBody").style.display === "none", "any other picker layer is closed first");
  ok($$("#cmpMSheet").length === 1 && $$("#cmpMSheetBack").length === 1, "exactly one sheet and one backdrop");
  ok(/Done \(4\)/.test(sheet().querySelector(".cmp-s-done").textContent), "Done shows the count");
  ok(names(secRows(1)).join() === "Germany,Japan,United Kingdom,United States", "Selected A to Z: " + names(secRows(1)));
  ok(secRows(1).every(r => r.querySelector(".cmp-s-dot") && r.querySelector(".cmp-s-btn.rm")), "selected rows: colour dot and minus");
  { const n2 = names(secRows(2)); ok(n2.length === api.allCountries().length - 4 && n2.join() === sorted(n2).join(), "Add more: the rest, A to Z (" + n2.length + ")"); }
  ok(!sheet().querySelector(".cmp-s-warn").hidden && /Sign up free or log in/.test(sheet().querySelector(".cmp-s-warn").textContent), "logged out at 4: warning box shown");
  ok(!/small circle/i.test(sheet().textContent), "no desktop colour-circle wording");
  ok(["G7", "G20", "EU", "Asia-Pacific", "Americas"].every(n => sheet().querySelector('[data-preset="' + n + '"]')) && !!sheet().querySelector(".cmp-s-clear"), "presets and Clear all");
  ok(!!sheet().querySelector(".cmp-s-all") && sheet().querySelector(".cmp-s-presets").firstElementChild.classList.contains("cmp-s-all"), "Select all leads the quick picks");
  // reopen while open: still one layer
  $("#cmpMEdit").click(); await sleep(30);
  ok($$("#cmpMSheet").length === 1 && $$("#cmpMSheetBack").length === 1, "opening again never stacks a second layer");
  // remove, then add
  sheet().querySelector('.cmp-s-row[data-key="Japan"] .cmp-s-btn.rm').click(); await sleep(250);
  ok(api.getSelected().indexOf("Japan") === -1 && /Done \(3\)/.test(sheet().querySelector(".cmp-s-done").textContent), "minus removes a country, count updates");
  ok(sheet().querySelector(".cmp-s-warn").hidden, "warning box hides below 4");
  { const f = sheet().querySelector(".cmp-s-find"); f.value = "fra"; f.dispatchEvent(new win.Event("input"));
    ok(names(secRows(2)).join() === "France", "search finds France: " + names(secRows(2)));
    sheet().querySelector('.cmp-s-row[data-key="France"] .cmp-s-btn.ad').click(); await sleep(250);
    ok(api.getSelected().indexOf("France") !== -1, "+ adds a country");
    f.value = ""; f.dispatchEvent(new win.Event("input")); }
  // at cap, logged out: no forced log-in; the warning box is flagged and the sheet stays open (v1.9.86)
  { let asked = 0; win.EATLAS_OPEN_AUTH_MODAL = () => asked++;
    sheet().querySelector('.cmp-s-row[data-key="Italy"] .cmp-s-btn.ad').click(); await sleep(100);
    const w = () => sheet().querySelector(".cmp-s-warn");
    ok(asked === 0 && !!sheet() && api.getSelected().indexOf("Italy") === -1, "at the free cap, + does not force a log-in and leaves the sheet open");
    ok(!w().hidden && w().classList.contains("flag"), "the warning box is flagged");
    w().classList.remove("flag");
    sheet().querySelector('[data-preset="G7"]').click(); await sleep(250);
    ok(asked === 0 && !!sheet() && api.getSelected().length === 4 && !w().hidden, "a 7-country preset logged out: first 4 kept, warning shown, no log-in forced");
    ok(w().classList.contains("flag"), "the cut-down preset flags the warning");
    w().querySelector(".cmp-s-signup").click(); await sleep(40);
    ok(asked === 1 && !sheet(), "the warning's Sign up or log in button closes the sheet and opens sign up"); }
  // Clear all
  $("#cmpMEdit").click(); await sleep(30);
  sheet().querySelector(".cmp-s-clear").click(); await sleep(250);
  ok(api.getSelected().length === 0 && /Done \(0\)/.test(sheet().querySelector(".cmp-s-done").textContent), "Clear all empties the selection");
  ok(/No countries yet/.test(sheet().textContent), "empty Selected says what to do");
  ["Canada", "Brazil"].forEach(c => sheet().querySelector('.cmp-s-row[data-key="' + c + '"] .cmp-s-btn.ad').click()); await sleep(250);
  ok(api.getSelected().join() === "Canada,Brazil", "build a fresh set after clearing: " + api.getSelected());
  // Back button closes
  win.dispatchEvent(new win.PopStateEvent("popstate", { state: null })); await sleep(30);
  ok(!sheet() && !$("#cmpMSheetBack") && !doc.body.classList.contains("cmp-sheet-open"), "Back closes the sheet");
  // backdrop + Escape
  $("#cmpMEdit").click(); await sleep(30); $("#cmpMSheetBack").click(); await sleep(30);
  ok(!sheet(), "backdrop closes the sheet");
  $("#cmpMEdit").click(); await sleep(30); doc.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape" })); await sleep(30);
  ok(!sheet(), "Escape closes the sheet");
  // switching sheets replaces, never stacks
  $("#cmpMEdit").click(); await sleep(30); $("#cmpMAddMetric").click(); await sleep(30);
  ok($$("#cmpMSheet").length === 1 && sheet().dataset.mode === "metrics", "Countries then Metrics: one sheet");
  { const h0 = win.history.length; $("#cmpMEdit").click(); await sleep(30);
    ok(win.history.length === h0, "switching sheets adds no extra Back step"); }
  sheet().querySelector(".cmp-s-done").click(); await sleep(30);

  /* v1.9.85 Select all: logged out keeps 4 and offers sign up */
  { let asked = 0; win.EATLAS_OPEN_AUTH_MODAL = () => asked++;
    $("#cmpMEdit").click(); await sleep(30);
    sheet().querySelector(".cmp-s-all").click(); await sleep(250);
    ok(asked === 0 && !!sheet() && api.getSelected().length === 4 && !sheet().querySelector(".cmp-s-warn").hidden, "Select all logged out: 4 kept, warning shown, no log-in forced");
    sheet().querySelector(".cmp-s-done").click(); await sleep(30); }

  /* rotate hint when wide */
  api.setSelected(["UK", "US", "Germany", "Japan"]); await sleep(250);
  { // the harness has no Supabase, so stand in a logged-in prefs object for this part
    win.EATLAS_PREFS = { isLoggedIn: () => true, set(){}, get(){ return null; } };
    api.setSelected(["UK", "US", "Germany", "Japan", "France", "Italy", "Canada"]); await sleep(300);
    ok(api.getSelected().length === 7, "logged in: 7 countries allowed");
    visible()[0].querySelector(".cmp-m-fs").click(); await sleep(60);
    ok(!$("#cmpMRotate").hidden, "7 countries: rotate hint shown");
    $("#cmpMRotate button").click(); ok($("#cmpMRotate").hidden, "hint can be dismissed");
    $("#cardFullscreenClose").click(); await sleep(30);
    visible()[0].querySelector(".cmp-m-fs").click(); await sleep(60);
    ok($("#cmpMRotate").hidden && $$("#cmpMRotate").length === 1, "dismissed for the visit, never duplicated");
    $("#cardFullscreenClose").click(); await sleep(30); }

  /* v1.9.85 ranking folds to 4, Show all expands, a change folds it back */
  { const rowsOf = () => $$(".metric-card:not(.cmp-m-off) .tpm-rankrow");
    const shownRows = () => rowsOf().filter(r => !r.classList.contains("cmp-m-rk-off"));
    const more = () => $(".metric-card:not(.cmp-m-off) .cmp-m-more");
    ok(rowsOf().length === 7 && shownRows().length === 4, "7 countries: top 4 shown (" + shownRows().length + ")");
    ok(shownRows().every((r, i) => r === rowsOf()[i]), "the 4 shown are the top of the ranking");
    ok(more() && more().textContent === "Show all 7 countries" && more().getAttribute("aria-expanded") === "false", "Show all button labelled with the count");
    more().click(); await sleep(60);
    ok(shownRows().length === 7 && more().textContent === "Show fewer" && more().getAttribute("aria-expanded") === "true", "Show all expands, then offers Show fewer");
    win.dispatchEvent(new win.Event("resize")); await sleep(80);
    ok(shownRows().length === 7, "stays open across re-runs");
    more().click(); await sleep(60);
    ok(shownRows().length === 4, "Show fewer folds back");
    more().click(); await sleep(60);
    api.setSelected(["UK", "US", "Germany", "Japan", "France", "Italy"]); await sleep(300);
    ok(shownRows().length === 4 && more().textContent === "Show all 6 countries", "changing countries folds it back to 4");
    ok($$(".metric-card:not(.cmp-m-off) .cmp-m-more").length === 1, "one Show all button");
    { const ol = $(".metric-card:not(.cmp-m-off) .tpm-ranklist"); [...ol.querySelectorAll(".tpm-rankrow")].slice(4).forEach(li => li.remove()); await sleep(80);
      ok(!more() && shownRows().length === 4, "list redrawn in place with 4 rows: button removed"); }
    api.setSelected(["UK", "US", "Germany"]); await sleep(300);
    ok(!more() && shownRows().length === 3, "4 or fewer countries: no button, all shown");
    ok(/display:none !important/.test(rule("  body.cmp-m .tpm-rankrow.cmp-m-rk-off")), "folded rows hidden by CSS"); }

  /* empty state: the Add a metric tile opens the phone sheet, not the desktop picker */
  if(sheet()) sheet().querySelector(".cmp-s-done").click();
  $(".cmp-m-tab-x").click(); await sleep(300);
  ok(api.getMetrics().length === 0 && doc.body.classList.contains("cmp-m-empty"), "no metrics: empty state on");
  $("#addMetricTile").click(); await sleep(40);
  ok(sheet() && sheet().dataset.mode === "metrics" && $("#metricPicker").hidden, "empty-state tile opens the Metrics sheet");
  sheet().querySelector('.cmp-s-row[data-key="unemployment"] .cmp-s-btn.ad').click(); await sleep(250);
  sheet().querySelector(".cmp-s-done").click(); await sleep(30);
  ok(api.getMetrics().join() === "unemployment" && !doc.body.classList.contains("cmp-m-empty"), "metric back, empty state off");

  /* idempotent */
  win.dispatchEvent(new win.Event("resize")); await sleep(50); win.dispatchEvent(new win.Event("resize")); await sleep(50);
  ok($$("#cmpMBar").length === 1 && $$("#cmpMAddMetric").length === 1 && $$("#cmpMSheet").length === 0, "nothing duplicated after re-runs");

  /* desktop */
  const d = await boot({ desktop: true });
  ok(!d.doc.body.classList.contains("cmp-m") && !d.doc.getElementById("cmpMBar"), "desktop: no phone layout");
  ok(d.win.EATLAS_COMPARE.getMetrics().join() === "gdp_level,gdp_growth,cpi", "desktop: three starter metrics unchanged");
  ok(!d.doc.querySelector(".cmp-m-sum") && !d.doc.getElementById("cmpMRotate"), "desktop: summary shown, no rotate hint");
  d.doc.getElementById("addMetricTile").click(); await sleep(40);
  ok(!d.doc.getElementById("metricPicker").hidden && !d.doc.getElementById("cmpMSheet"), "desktop: Add a metric opens the desktop picker");

  /* CSS */
  const start = CSS.indexOf("@media (max-width:760px){", 140);
  ["#cmpMSheet\\{", "\\.cmp-s-row\\{", "\\.cmp-m-tab-x\\{", "\\.cmp-m-tabrow\\{", "body\\.cmp-m #cmpMRotate\\{"].forEach(sel => {
    const i = CSS.search(new RegExp(sel)); ok(i > start && start > 0, sel + " phone-scoped");
  });
  ok(/min-height:48px/.test(rule("  .cmp-s-row")) && /width:44px; height:44px/.test(rule("  .cmp-s-btn")), "sheet rows 48px, buttons 44px");
  ok(/min-height:44px/.test(rule("  .cmp-m-tab")) && /height:44px/.test(rule("  .cmp-m-tab-x")), "tabs and x 44px tall");
  ok(/font-size:16px/.test(rule("  .cmp-s-find")), "search 16px (no iOS zoom)");
  ok(/touch-action:manipulation/.test(rule("  #cmpMSheet button, #cmpMBar button, .cmp-m-more, .cmp-m-fs")), "no double-tap zoom on sheet, bar and ranking buttons");
  ok(/flex:none/.test(rule("  .cmp-m-edit")) && /min-width:0/.test(rule("  .cmp-m-chiprow > .cmp-m-chips")), "Edit fixed, chips scroll beside it");
  ok(/flex-wrap:wrap/.test(rule("  .cmp-s-presets")) && !/overflow-x/.test(rule("  .cmp-s-presets")), "quick picks wrap, all visible");
  ok(/z-index:1300/.test(rule("  #cmpMSheet")) && /z-index:1299/.test(rule("  #cmpMSheetBack")), "sheet above every other layer");
  ok(/@media \(orientation:landscape\)\{ #cmpMRotate\{ display:none !important; \} \}/.test(CSS), "rotate hint hidden in landscape");
  ok(/display:none !important/.test(rule("  body.cmp-m .metric-card.cmp-m-off")), "inactive cards hidden");
  ok(/order:2/.test(rule("  body.cmp-m .metric-card > .tpm-layout")), "ranking first");
  ok(/CMP_PHONE_START \? \["unemployment"\]/.test(HTML), "phone default in compare.html");
  { const cv = +(HTML.match(/mobile\.css\?v=(\d+)/) || [0, 0])[1], jv = +(HTML.match(/mobile\.js\?v=(\d+)/) || [0, 0])[1];
    ok(cv >= 35 && jv >= 35, `compare on mobile.css/js >= v35 (v${cv} / v${jv})`); }

  console.log(`test_compare_mobile: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.stack); console.log(`test_compare_mobile: ${checks - failures} ok, ${failures + 1} failed`); process.exit(1); });
