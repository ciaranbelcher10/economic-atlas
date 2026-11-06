#!/usr/bin/env node
/* v1.9.83 Compare on phones, rebuilt.
 *  - one view: Metric and Countries buttons, average + High/Low toggle, one ranked list; old page hidden
 *  - rows: rank, name, value, thin bar; year tag only when it differs from most rows; tap expands a trend line
 *  - one full-screen sheet at a time: metric list (search, groups, tap = switch) or countries (presets, tick list, count, Done)
 *  - state kept in localStorage and the URL (?metric=, countries=all or set=preset); Back closes the sheet
 *  - desktop untouched
 * Run: NODE_PATH=/tmp/node_modules node tools/test_compare_mobile.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
const boot = require("./compare_harness");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const CSS = fs.readFileSync(path.join(ROOT, "mobile.css"), "utf8");
const HTML = fs.readFileSync(path.join(ROOT, "compare.html"), "utf8");
const num = t => parseFloat(String(t).replace(/[^0-9.\-]/g, ""));

(async () => {
  const { win, doc, errs, store } = await boot();
  const $ = s => doc.querySelector(s), $$ = s => [...doc.querySelectorAll(s)];
  const rows = () => $$("#cmpP .cmpp-list li[data-c]");
  const sheet = () => $("#cmpPSheet");
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  ok(doc.body.classList.contains("cmp-p") && !doc.body.classList.contains("cmp-m"), "rebuilt phone view on, old phone layer off");
  ok($$("#cmpP").length === 1 && !$("#cmpMBar"), "one view, no old chip/tab bar");
  ok(/body\.cmp-p #mainContent, body\.cmp-p #loadMsg, body\.cmp-p #saveBar[^{]*\{ display:none !important; \}/.test(CSS), "old page, loading line and save bar hidden on phones");

  // default: debt across all 62, highest first
  ok($(".cmpp-metric").textContent === "Government debt, % of GDP", "default metric: " + $(".cmpp-metric").textContent);
  ok($(".cmpp-set").textContent === "All 62", "default set: " + $(".cmpp-set").textContent);
  ok(rows().length >= 50, "ranks every country with data: " + rows().length);
  const vals = rows().map(r => num(r.querySelector(".v").textContent));
  ok(vals.every((v, i) => i === 0 || v <= vals[i - 1]), "highest first");
  ok(rows().every((r, i) => r.querySelector(".r").textContent === String(i + 1)), "ranks numbered 1..n");
  ok(rows()[0].querySelector(".b i").style.width === "100%" && rows().every(r => { const w = parseFloat(r.querySelector(".b i").style.width); return w >= 2 && w <= 100; }), "bars scaled to the largest");
  ok(/^Average \d+(\.\d+)?% · Latest, mostly 20\d\d$/.test($(".cmpp-avg").textContent), "average and main year: " + $(".cmpp-avg").textContent);
  { const modeY = $(".cmpp-avg").textContent.slice(-4);
    const tags = rows().map(r => r.querySelector(".n em")).filter(Boolean);
    ok(rows().filter(r => !r.querySelector(".n em")).length > rows().length / 2, "most rows carry no year tag");
    ok(tags.every(t => t.textContent !== modeY && /^20\d\d$/.test(t.textContent)), "year tag only where it differs"); }
  ok(!$$("#cmpP i[style*='background']").length && !$$("#cmpP .tpm-rankswatch").length, "no colour dots");

  // order toggle
  $(".cmpp-order").click(); await sleep(20);
  const asc = rows().map(r => num(r.querySelector(".v").textContent));
  ok(asc.every((v, i) => i === 0 || v >= asc[i - 1]) && /Lowest first/.test($(".cmpp-order").textContent), "toggle: lowest first");
  $(".cmpp-order").click(); await sleep(20);

  // row expands to a trend
  rows()[0].click(); await sleep(20);
  ok(rows()[0].classList.contains("open") && rows()[0].getAttribute("aria-expanded") === "true", "tap opens a row");
  ok(/<path d="M[\d.]+ [\d.]+ L/.test(rows()[0].querySelector(".cmpp-detail").innerHTML) && /^Latest: 20\d\d/.test(rows()[0].querySelector(".cmpp-detail p").textContent), "trend line and latest period");
  rows()[1].click(); await sleep(20);
  ok($$("#cmpP li.open").length === 1 && rows()[1].classList.contains("open"), "one open row at a time");
  rows()[1].click(); await sleep(20);
  ok(!$$("#cmpP li.open").length, "tap again closes");

  // metric sheet
  $(".cmpp-pick[data-open=metric]").click(); await sleep(20);
  ok(!sheet().hidden && sheet().dataset.kind === "metric" && doc.body.classList.contains("cmpp-sheet-open"), "metric sheet opens full screen");
  ok($$("#cmpPSheet .cmpp-item").length >= 10 && $$("#cmpPSheet .cmpp-grp h3").length >= 4, "metrics grouped by topic");
  ok($$("#cmpPSheet .cmpp-item[aria-pressed=true]").map(b => b.dataset.k).join() === "debt_gdp", "current metric ticked");
  ok(!$$("#cmpPSheet .cmpp-item").some(b => b.dataset.k === "cpih" || b.dataset.k === "unemployment_1624"), "single-country metrics left out");
  const q = $("#cmpPSheet .cmpp-q"); q.value = "unemploy"; q.dispatchEvent(new win.Event("input"));
  const shown = $$("#cmpPSheet .cmpp-item").filter(b => !b.hidden);
  ok(shown.length >= 1 && shown.every(b => /unemploy/i.test(b.textContent)) && $$("#cmpPSheet .cmpp-grp").filter(g => !g.hidden).length === 1, "search filters and hides empty groups");
  $("#cmpPSheet .cmpp-item[data-k=unemployment]").click(); await sleep(700);
  ok(sheet().hidden && !doc.body.classList.contains("cmpp-sheet-open"), "tapping a metric closes the sheet");
  ok($(".cmpp-metric").textContent === "Unemployment rate" && rows().length >= 40, "ranking switched to unemployment");
  ok(/metric=unemployment/.test(win.location.search) && /countries=all/.test(win.location.search), "URL carries metric and all: " + win.location.search);
  ok(JSON.parse(store.eatlas_cmp_phone).metric === "unemployment", "metric remembered");

  // countries sheet: presets
  $(".cmpp-pick[data-open=countries]").click(); await sleep(20);
  ok(!sheet().hidden && sheet().dataset.kind === "countries", "countries sheet opens");
  ok($$("#cmpPSheet .cmpp-presets button").map(b => b.textContent).join("|") === "All|G7|G20|EU|Europe|Asia-Pacific|Americas|Emerging|None", "presets");
  ok($(".cmpp-count").textContent === "62 selected" && $$("#cmpPSheet .cmpp-c[aria-pressed=true]").length === 62, "all ticked to start");
  $("#cmpPSheet .cmpp-presets [data-p=g7]").click(); await sleep(10);
  ok($(".cmpp-count").textContent === "7 selected" && $("#cmpPSheet .cmpp-presets [data-p=g7]").getAttribute("aria-pressed") === "true", "G7 one tap, count live");
  ok(rows().length >= 40, "list waits for Done");
  $("#cmpPSheet .cmpp-done").click(); await sleep(700);
  ok(rows().length === 7 && $(".cmpp-set").textContent === "G7 (7)", "G7 applied: " + rows().length);
  ok(/set=g7/.test(win.location.search) && !/countries=/.test(win.location.search), "URL: set=g7");

  // custom tick list
  $(".cmpp-pick[data-open=countries]").click(); await sleep(20);
  $("#cmpPSheet .cmpp-presets [data-p=none]").click(); await sleep(10);
  ok($(".cmpp-count").textContent === "0 selected", "None clears");
  ["UK", "Germany", "Japan", "Brazil", "India"].forEach(c => $(`#cmpPSheet .cmpp-c[data-c="${c}"]`).click());
  ok($(".cmpp-count").textContent === "5 selected" && $(`#cmpPSheet .cmpp-c[data-c="UK"]`).getAttribute("aria-pressed") === "true", "ticks and count");
  $(`#cmpPSheet .cmpp-c[data-c="India"]`).click();
  ok($(".cmpp-count").textContent === "4 selected", "tap again unticks");
  const cq = $("#cmpPSheet .cmpp-q"); cq.value = "kor"; cq.dispatchEvent(new win.Event("input"));
  ok($$("#cmpPSheet .cmpp-c").filter(b => !b.hidden).map(b => b.dataset.c).join() === "South Korea", "country search");
  $(`#cmpPSheet .cmpp-c[data-c="South Korea"]`).click();
  $("#cmpPSheet .cmpp-done").click(); await sleep(700);
  ok(rows().map(r => r.dataset.c).sort().join() === "Brazil,Germany,Japan,South Korea,UK" && $(".cmpp-set").textContent === "5 chosen", "custom set applied: " + rows().map(r => r.dataset.c));
  ok(JSON.parse(store.eatlas_cmp_phone).custom.sort().join() === "Brazil,Germany,Japan,South Korea,UK", "custom set remembered");

  // Back closes the sheet, and only one sheet ever exists
  $(".cmpp-pick[data-open=metric]").click(); await sleep(20);
  win.history.back(); await sleep(400);
  ok(sheet().hidden, "Back closes the sheet");
  ok(/metric=unemployment/.test(win.location.search), "URL kept after Back: " + win.location.search);
  win.dispatchEvent(new win.Event("resize")); await sleep(50); win.dispatchEvent(new win.Event("resize")); await sleep(50);
  ok($$("#cmpPSheet").length === 1 && $$("#cmpP").length === 1, "nothing duplicated after re-runs");

  // restored from storage on the next visit
  const r2 = await boot({ store: { eatlas_cmp_phone: store.eatlas_cmp_phone } });
  ok(r2.doc.querySelector(".cmpp-metric").textContent === "Unemployment rate" && r2.doc.querySelectorAll("#cmpP .cmpp-list li[data-c]").length === 5, "choices restored on return");
  // a desktop-style link opens that metric across all countries
  const r3 = await boot({ query: "?metric=cpi&countries=all" });
  ok(r3.doc.querySelector(".cmpp-metric").textContent === "Inflation" && r3.doc.querySelector(".cmpp-set").textContent === "All 62", "?metric=cpi&countries=all link");

  /* desktop */
  const d = await boot({ desktop: true });
  ok(!d.doc.body.classList.contains("cmp-p") && !d.doc.body.classList.contains("cmp-m"), "desktop: no phone layout");
  ok(/^#cmpP, #cmpPSheet\{ display:none; \}$/m.test(CSS), "phone view hidden outside phone widths");
  ok(d.doc.querySelectorAll(".metric-card").length >= 2 && d.doc.getElementById("mainContent").style.display === "block", "desktop: cards as before");
  ok(d.doc.querySelector("h1").nextElementSibling.textContent.indexOf("Rank and compare all 62") === 0, "desktop keeps the full intro");
  { const cv = +(HTML.match(/mobile\.css\?v=(\d+)/) || [0, 0])[1], jv = +(HTML.match(/mobile\.js\?v=(\d+)/) || [0, 0])[1];
    ok(cv >= 30 && jv >= 30, `compare on mobile.css/js >= v30 (v${cv} / v${jv})`); }
  ok(/window\.EATLAS_COMPARE_DATA = \{/.test(HTML), "compare exposes its data helpers");

  console.log(`test_compare_mobile: ${checks - failures} ok, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("  FAIL  crashed: " + e.stack); console.log(`test_compare_mobile: ${checks - failures} ok, ${failures + 1} failed`); process.exit(1); });
