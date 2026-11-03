#!/usr/bin/env node
/* v1.9.76 Compare on phones.
 *  - sticky bar: one chip per selected country (+ Edit), one tab per metric card (+ Add metric)
 *  - exactly one metric card visible; tabs switch it; a newly added metric becomes active
 *  - ranked list gets bars sized by value; trade-page note not shown on Compare
 *  - summary: one card per metric, a row per country, Highest / Lowest from the table's own markers
 *  - Add a metric: search filters items and hides empty categories; + / tick rows
 *  - countries panel opens as a sheet with Done + backdrop
 *  - desktop untouched; dark-mode "Order countries by" strip no longer light
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
(async () => {
  const { win, doc, errs } = await boot();
  const $ = s => doc.querySelector(s), $$ = s => [...doc.querySelectorAll(s)];
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  ok(doc.body.classList.contains("cmp-m"), "phone layout switched on");
  ok($$("#cmpMBar").length === 1, "one sticky bar");

  const chipCountries = $$("#chipRow .chip[data-country]").map(c => c.dataset.country);
  const barChips = $$("#cmpMChips .cmp-m-chip:not(.cmp-m-add)");
  ok(chipCountries.length > 0 && barChips.map(b => b.textContent).join() === chipCountries.join(), "one bar chip per selected country: " + barChips.map(b => b.textContent));
  ok(barChips.every((b, i) => b.querySelector("i").style.background === $$("#chipRow .chip[data-country]")[i].style.background), "chips keep each country's colour");
  ok(!!$("#cmpMChips .cmp-m-add"), "chip bar has + Edit");

  const cards = () => $$("#chartGrid .metric-card");
  const visible = () => cards().filter(c => !c.classList.contains("cmp-m-off"));
  const tabs = () => $$("#cmpMTabs .cmp-m-tab:not(.cmp-m-tab-add)");
  ok(cards().length >= 2, "default comparison has several metrics (" + cards().length + ")");
  ok(tabs().length === cards().length, "one tab per metric card");
  ok(tabs().every((t, i) => t.textContent === cards()[i].querySelector(".card-title").textContent.trim()), "tab labels match card titles");
  ok(!!$("#cmpMTabs .cmp-m-tab-add"), "tabs end with + Add metric");
  ok($("#cmpMTabs").getAttribute("role") === "tablist" && tabs().every(t => t.getAttribute("role") === "tab"), "tab roles");
  ok(visible().length === 1 && visible()[0] === cards()[0], "exactly one card visible, the first");
  ok(tabs()[0].getAttribute("aria-selected") === "true" && tabs().filter(t => t.getAttribute("aria-selected") === "true").length === 1, "first tab selected, only one");

  tabs()[cards().length - 1].click(); await sleep(50);
  ok(visible().length === 1 && visible()[0] === cards()[cards().length - 1], "tapping a tab shows that card only");
  ok(tabs()[cards().length - 1].getAttribute("aria-selected") === "true", "tapped tab selected");

  // ranked bars on the visible card
  const rows = $$(".metric-card:not(.cmp-m-off) .tpm-rankrow");
  const widths = rows.map(r => r.querySelector(".cmp-rk-bar i") ? parseFloat(r.querySelector(".cmp-rk-bar i").style.width) : NaN);
  ok(rows.length >= 2 && widths.every(w => w >= 2 && w <= 100), "every ranked row has a bar: " + widths.join(","));
  ok(widths.some(w => w === 100), "largest value has a full bar");
  ok(rows.every(r => r.querySelectorAll(".cmp-rk-bar").length === 1), "one bar per row");
  ok(rows.every(r => r.querySelector(".cmp-rk-bar i").style.background === r.querySelector(".tpm-rankswatch").style.background), "bars use the country colour");
  ok($$(".metric-card .tpm-mobile-note").length === 0 && $$(".tpm-mobile-note").length === 0, "no trade-page note on Compare");

  // v1.9.77: labelled full-screen button on every card, after the ranking, pressing the card's own button
  ok(cards().every(c => c.querySelectorAll(".cmp-m-fs").length === 1), "every card has one full-screen button");
  { const v = visible()[0], fs = v.querySelector(".cmp-m-fs");
    ok(/full-screen chart/i.test(fs.textContent), "button is labelled: " + fs.textContent.trim());
    let pressed = 0; v.querySelector(".card-fullscreen-btn").addEventListener("click", () => pressed++);
    fs.click(); await sleep(50);
    ok(pressed === 1, "it presses the card's own Fullscreen button");
    const m = doc.getElementById("cardFullscreenModal"); ok(m && !m.hidden, "full-screen chart opens");
    const cl = doc.getElementById("cardFullscreenClose"); if(cl) cl.click(); await sleep(30); }
  ok(/order:2;/.test(rule("  body.cmp-m .metric-card > .cmp-m-fs")) && /min-height:44px/.test(rule("  body.cmp-m .metric-card > .cmp-m-fs")), "button sits with the ranking, 44px");

  // summary per metric
  const ths = $$("#rankTable thead th");
  const sums = $$("#cmpCardsWrap .cmp-metric-sum");
  ok(sums.length === ths.length - 1, "one summary card per metric (" + sums.length + ")");
  ok(sums.every((s, i) => s.querySelector("h4").textContent === ths[i + 1].textContent.trim()), "summary card titles match columns");
  const trs = $$("#rankTable tbody tr");
  sums.forEach((s, i) => {
    const srs = [...s.querySelectorAll(".sr")];
    ok(srs.length === trs.length, `summary ${i}: a row per country`);
    trs.forEach((tr, j) => {
      const cell = tr.querySelectorAll("td")[i + 1];
      const hi = cell.classList.contains("col-hi"), lo = cell.classList.contains("col-lo");
      ok(srs[j].classList.contains("is-hi") === hi && srs[j].classList.contains("is-lo") === lo, `summary ${i} row ${j}: highest/lowest follow the table`);
      ok(srs[j].querySelector(".cn").textContent === tr.querySelector("td.country").textContent.trim(), `summary ${i} row ${j}: country`);
      ok(srs[j].querySelector("b").textContent === cell.childNodes[0].textContent.trim(), `summary ${i} row ${j}: value ${srs[j].querySelector("b").textContent}`);
    });
  });
  ok(!$(".cmp-country-card"), "old per-country summary cards gone");

  // Add a metric sheet
  $("#cmpMTabs .cmp-m-tab-add").click(); await sleep(50);
  ok($("#metricPicker") && !$("#metricPicker").hidden, "+ Add metric opens the picker");
  const search = $("#metricPickerSearch");
  ok(!!search && $$("#metricPickerSearch").length === 1, "picker has one search box");
  search.value = "unemployment"; search.dispatchEvent(new win.Event("input"));
  const shown = $$("#metricPickerGrid .pickeritem:not([hidden])");
  ok(shown.length >= 1 && shown.every(e => /unemployment/i.test(e.textContent)), "search filters items: " + shown.map(e => e.dataset.key));
  const cats = $$("#metricPickerGrid .pickercat:not([hidden])").map(c => c.textContent);
  ok(cats.length === 1 && /labour/i.test(cats[0]), "empty categories hidden: " + cats);
  search.value = "zzzz"; search.dispatchEvent(new win.Event("input"));
  ok($$("#metricPickerGrid .pickeritem:not([hidden])").length === 0, "no match hides everything");
  search.value = "unemployment"; search.dispatchEvent(new win.Event("input"));
  const before = cards().length;
  $$("#metricPickerGrid .pickeritem:not([hidden]):not(.added)")[0].click(); await sleep(300);
  ok(cards().length === before + 1, "picking adds a card");
  ok(visible().length === 1 && visible()[0] === cards()[cards().length - 1], "new metric becomes the visible card");
  ok(tabs().length === cards().length && tabs()[tabs().length - 1].getAttribute("aria-selected") === "true", "new tab added and selected");
  $("#metricPickerClose").click(); await sleep(50);
  ok(search.value === "", "search clears when the picker closes");

  // remove active card -> falls back
  visible()[0].querySelector(".card-remove").click(); await sleep(300);
  ok(cards().length === before && visible().length === 1 && visible()[0] === cards()[0], "removing the active metric shows the first");

  // countries sheet
  barChips[0].click(); await sleep(50);
  ok($("#countriesPanelBody").style.display === "block", "chip opens the countries panel");
  ok(!!$("#countriesPanelBody .cmp-m-done") && $$(".cmp-m-done").length === 1, "panel has one Done button");
  ok(!$("#cmpPanelBackdrop").hidden, "backdrop shown");
  $("#cmpPanelBackdrop").click(); await sleep(50);
  ok($("#countriesPanelBody").style.display === "none" && $("#cmpPanelBackdrop").hidden, "backdrop closes the panel");
  $("#cmpMChips .cmp-m-add").click(); await sleep(30); $(".cmp-m-done").click(); await sleep(50);
  ok($("#countriesPanelBody").style.display === "none", "Done closes the panel");

  // re-runs stay idempotent
  win.dispatchEvent(new win.Event("resize")); await sleep(50); win.dispatchEvent(new win.Event("resize")); await sleep(50);
  ok($$("#cmpMBar").length === 1 && $$("#metricPickerSearch").length === 1 && $$(".cmp-m-done").length === 1 && $$("#cmpPanelBackdrop").length === 1, "nothing duplicated after re-runs");

  /* desktop */
  const d = await boot({ desktop: true });
  ok(!d.doc.body.classList.contains("cmp-m") && !d.doc.getElementById("cmpMBar"), "desktop: no phone layout");
  ok([...d.doc.querySelectorAll(".metric-card")].every(c => !c.classList.contains("cmp-m-off")), "desktop: every card visible");
  ok(!d.doc.querySelector(".cmp-rk-bar") && !d.doc.getElementById("metricPickerSearch"), "desktop: no phone extras");

  /* CSS + markup */
  const start = CSS.indexOf("@media (max-width:760px){", 140);
  ["#cmpMBar\\{", "\\.cmp-m-tab\\{", "\\.cmp-metric-sum\\{", "#metricPicker \\.pickeritem::after", "body\\.cmp-m #countriesPanelBody\\{"].forEach(sel => {
    const i = CSS.search(new RegExp(sel)); ok(i > start && start > 0, sel + " phone-scoped");
  });
  ok(/min-height:44px/.test(rule("  .cmp-m-tab")), "tabs 44px");
  ok(/min-height:48px/.test(rule("  #metricPicker .pickeritem")), "picker rows 48px");
  ok(/display:none !important/.test(rule("  body.cmp-m .metric-card.cmp-m-off")), "inactive cards hidden");
  ok(/order:2/.test(rule("  body.cmp-m .metric-card > .tpm-layout")) && /order:3/.test(rule("  body.cmp-m .metric-card > .card-time-row")), "ranking before controls");
  ok(/display:none !important/.test(rule("  body.cmp-m .metric-card .card-sort-row")), "Order by hidden until More options");
  ok(/\[data-theme="dark"\] \.card-sort-row\{background:var\(--panel\) !important;/.test(HTML), "dark Order-by strip uses the panel colour");
  { const cv = +(HTML.match(/mobile\.css\?v=(\d+)/) || [0, 0])[1], jv = +(HTML.match(/mobile\.js\?v=(\d+)/) || [0, 0])[1];
    ok(cv >= 24 && jv >= 25, `compare on mobile.css >= v24 / mobile.js >= v25 (v${cv} / v${jv})`); }

  console.log(`test_compare_mobile: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.stack); console.log(`test_compare_mobile: ${checks - failures} ok, ${failures + 1} failed`); process.exit(1); });
