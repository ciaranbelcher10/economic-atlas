#!/usr/bin/env node
/* Calendar tracking picker (v1.9.46): ChartMaker-style chooser with group and region chips,
 * search, per-country upcoming hints, release-type toggles and a live summary, plus the
 * reworded intro and the publication-date warning.
 * Run: NODE_PATH=/tmp/node_modules node tools/test_calendar_picker.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "..");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const eq = (a, b, m) => ok(JSON.stringify(a) === JSON.stringify(b), `${m}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
const { JSDOM, VirtualConsole } = require("jsdom");
const errors = [];
async function boot(seed){
  const html = fs.readFileSync(path.join(ROOT, "calendar.html"), "utf8");
  const vc = new VirtualConsole();
  vc.on("jsdomError", e => { const m = String(e && e.message || e).split("\n")[0]; if(!/Not implemented|supabase|EATLAS_PREFS/i.test(m)) errors.push(m); });
  const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, virtualConsole: vc, url: "https://theeconomicatlas.com/calendar",
    beforeParse(win){
      // v1.9.97: these tests cover a signed-in reader, who has no country cap. Signed out, the picker is capped
      // at 3 free countries (v1.9.90), which test_free_caps.js covers. Account prefs live in this browser's storage here.
      // (Supabase is not loaded in jsdom, so the page's own EATLAS_PREFS never gets built; this stands in for it.)
      win.EATLAS_PREFS = { isLoggedIn: () => true, isPro: () => true, onSettled(){}, onLogin(){}, registerBanner(){},
        get: (k, d) => { const s = win.localStorage.getItem("eatlas_" + k); return s == null ? d : JSON.parse(s); },
        set: (k, val) => win.localStorage.setItem("eatlas_" + k, JSON.stringify(val)) };
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
  const win = await boot(), doc = win.document, $ = s => doc.querySelector(s);
  const click = el => el.dispatchEvent(new win.MouseEvent("click", { bubbles: true }));
  const expl = $("header.page .expl").textContent;
  ok(/^Upcoming release dates for GDP, inflation, jobs, trade and central bank rate decisions/.test(expl), "intro is short and plain: " + expl);
  ok(!/never have to go hunting/.test(doc.body.innerHTML), "old intro wording gone");
  const note = $(".cal-head-note").textContent;
  ok(/publication dates, not site update dates/.test(note) && /days or weeks later/.test(note), "warning that release dates are not site update dates");
  ok(!/\u2014/.test(expl + note) && !/hourly/i.test(note), "no em dashes or hourly claims in the new copy");

  ok($("#calCountriesModal").hidden, "picker closed at start");
  click($("#calCountriesBtn"));
  ok(!$("#calCountriesModal").hidden, "Countries button opens the picker");
  const chips = [...doc.querySelectorAll("#ctpGroups button")].map(b => b.childNodes[0].textContent);
  eq(chips, ["G7", "G20", "EU", "Euro area", "OECD", "BRICS"], "group chips as in ChartMaker");
  ok(doc.querySelectorAll("#ctpRegions button").length >= 6, "region chips shown");
  const total = doc.querySelectorAll("#ctpCountries input").length;
  ok(total === win.document.querySelector("#ctpCount").textContent.split(" of ")[1] * 1 && total > 40, `every covered country listed (${total})`);
  const names = [...doc.querySelectorAll("#ctpCountries .nm")].map(n => n.textContent);
  eq(names, names.slice().sort((a, b) => a.localeCompare(b)), "countries A to Z");
  ok(/Not on the calendar yet:/.test($("#ctpNotYet").textContent) && /India/.test($("#ctpNotYet").textContent) && !names.includes("India"), "uncovered economies explained, not listed as trackable");
  const hint = c => { const l = [...doc.querySelectorAll("#ctpCountries label")].find(l => l.querySelector(".nm").textContent === c); return l && l.querySelector("small"); };
  ok(hint("Germany") && /ECB decisions/.test(hint("Germany").textContent), "euro member hint names the ECB: " + (hint("Germany") || {}).textContent);
  ok(hint("US") && !hint("US").classList.contains("none"), "US shows its upcoming releases: " + (hint("US") || {}).textContent);

  click($("#calPickNone"));
  eq($("#ctpCount").textContent.split(" of ")[0], "0", "None clears every country");
  ok(/Pick at least one country/.test($("#ctpSummary").textContent), "empty selection explained in the summary");
  click([...doc.querySelectorAll("#ctpGroups button")].find(b => b.textContent.startsWith("G7")));
  const g7 = ["Canada", "France", "Germany", "Italy", "Japan", "UK", "US"];
  eq([...doc.querySelectorAll("#ctpCountries input:checked")].map(i => i.dataset.country).sort(), g7.slice().sort(), "G7 chip ticks exactly the G7");
  ok([...doc.querySelectorAll("#ctpGroups button")].find(b => b.textContent.startsWith("G7")).classList.contains("on"), "G7 chip shows as on");
  ok([...doc.querySelectorAll("#ctpGroups button")].find(b => b.textContent.startsWith("G20")).classList.contains("part"), "G20 chip shows as partly on");
  eq(JSON.parse(win.localStorage.getItem("eatlas_calendar_tracked_countries")).sort(), g7.slice().sort(), "selection saved as it changes");
  ok(/release/.test($("#ctpSummary").textContent) && /countries you track/.test($("#ctpSummary").textContent), "summary counts the next 30 days: " + $("#ctpSummary").textContent);
  click([...doc.querySelectorAll("#ctpGroups button")].find(b => b.textContent.startsWith("G7")));
  eq($("#ctpCount").textContent.split(" of ")[0], "0", "G7 chip again unticks the G7");

  const de = doc.querySelector("#ctpCountries input[data-country='Denmark']") || doc.querySelector("#ctpCountries input[data-country='Norway']");
  de.checked = true; de.dispatchEvent(new win.Event("change", { bubbles: true }));
  eq([...doc.querySelectorAll("#ctpCountries input:checked")].map(i => i.dataset.country), [de.dataset.country], "ticking one country tracks it");
  eq($("#calCountriesCount").textContent.split(" of ")[0], "1", "Countries button count follows the picker");

  const s = $("#ctpSearch"); s.value = "nor"; s.dispatchEvent(new win.Event("input", { bubbles: true }));
  eq([...doc.querySelectorAll("#ctpCountries .nm")].map(n => n.textContent), ["Norway"], "search filters by name start");
  s.value = "korea"; s.dispatchEvent(new win.Event("input", { bubbles: true }));
  eq([...doc.querySelectorAll("#ctpCountries .nm")].map(n => n.textContent), ["South Korea"], "search matches any word of a name");
  s.value = "zz"; s.dispatchEvent(new win.Event("input", { bubbles: true }));
  ok(/No country on the calendar matches/.test($("#ctpCountries").textContent), "no-match message");
  s.value = ""; s.dispatchEvent(new win.Event("input", { bubbles: true }));

  const mbtn = k => doc.querySelector(`#calMetricsPickerGrid button[data-metric='${k}']`);
  eq([...doc.querySelectorAll("#calMetricsPickerGrid button")].map(b => b.dataset.metric)[0], "rate_decision", "rate decisions listed first");
  click(mbtn("cpi"));
  eq(mbtn("cpi").getAttribute("aria-pressed"), "false", "a release type toggles off");
  ok(!JSON.parse(win.localStorage.getItem("eatlas_calendar_tracked_metrics")).includes("cpi"), "release types saved as they change");
  click(mbtn("cpi"));
  eq(mbtn("cpi").getAttribute("aria-pressed"), "true", "and back on");

  click([...doc.querySelectorAll("#calColorModeSeg button")].find(b => b.dataset.mode === "country"));
  ok(doc.querySelector("#calColorModeSeg button[data-mode='country']").classList.contains("active"), "colour mode still works");
  click($("#ctpDone"));
  ok($("#calCountriesModal").hidden, "Done closes the picker");
  click($("#calCountriesBtn")); click($("#calCountriesModal"));
  ok($("#calCountriesModal").hidden, "clicking outside closes it");
  click($("#calCountriesBtn")); doc.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape" }));
  ok($("#calCountriesModal").hidden, "Escape closes it");
  click($("#calCountriesBtn")); click($("#calPickAll"));
  eq($("#ctpCount").textContent.split(" of ")[0], $("#ctpCount").textContent.split(" of ")[1], "All ticks every country");
  ok(/Email me when something I track/.test($("#calEmailAlertsRow").textContent), "signed-in email alerts toggle");
  ok(!$("#calPickerGrid") && !doc.querySelector(".cal-picker-grid"), "old picker grid removed");

  // a saved selection from before the rebuild is respected
  const w2 = await boot({ eatlas_calendar_tracked_countries: JSON.stringify(["UK", "Japan"]) });
  w2.document.querySelector("#calCountriesBtn").dispatchEvent(new w2.MouseEvent("click", { bubbles: true }));
  eq([...w2.document.querySelectorAll("#ctpCountries input:checked")].map(i => i.dataset.country).sort(), ["Japan", "UK"], "earlier saved picks carry over");
  ok(errors.length === 0, "no page errors: " + errors.slice(0, 3).join(" | "));
  console.log(`test_calendar_picker: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("CRASH " + (e && e.stack || e)); process.exit(2); });
