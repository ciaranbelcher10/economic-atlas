#!/usr/bin/env node
/* v2.0.8: Chartmaker and Compare polish.
 *  Chartmaker: round-year labels on a long single-series column chart; a horizontal chart grows so
 *  no two row labels overlap; the notes sit in one collapsed "About these figures" line; the
 *  country chooser has All countries and Clear; bars are square.
 *  Compare: G7/G20/EU... group buttons in the country picker, one alphabetical list, and the year
 *  still in progress labelled "so far".
 * Run: NODE_PATH=/tmp/node_modules node tools/test_v208_polish.js */
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, ".."), NM = (process.env.NODE_PATH || "/tmp/node_modules").split(path.delimiter)[0] + "/";
const { JSDOM, VirtualConsole } = require(NM + "jsdom");
let checks = 0, failures = 0;
const ok = (c, m) => { checks++; if(!c){ failures++; console.log("  FAIL  " + m); } };
const src = fs.readFileSync(path.join(__dirname, "test_v203_bar_colours.js"), "utf8");
eval(src.slice(src.indexOf("async function boot"), src.indexOf("(async () => {")));
(async () => {
  // ---------------- Chartmaker ----------------
  const win = await boot(); const run = js => win.__cmEval(js);
  run(`series.length = 0; addSeries("UK", "policy_rate", false, true); chartType = "bar"; style.barOrient = "vertical"; renderChart();`);
  const vsvg = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; SNAPSHOT_ROWS = buildSnapshotRows(); czmBuildBars("light", true)`));
  const yearLabs = [...vsvg.matchAll(/>((?:19|20)\d\d)</g)].map(m => +m[1]);
  ok(yearLabs.length >= 3 && yearLabs.every(y => y % 5 === 0), "column chart labels round years: " + yearLabs.join(" "));
  ok(!/<rect x='(?!0')[^>]* rx=/.test(vsvg), "column bars are square");
  run(`style.barOrient = "horizontal"; renderChart();`);
  const hsvg = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; SNAPSHOT_ROWS = buildSnapshotRows(); czmBuildBars("light", true)`));
  const ys = [...hsvg.matchAll(/<text x='[^']+' y='([\d.]+)' font-size='(\d+(?:\.\d+)?)' fill='[^']+' text-anchor='end'>/g)].map(m => [+m[1], +m[2]]);
  let minGap = Infinity; for(let i = 1; i < ys.length; i++) minGap = Math.min(minGap, ys[i][0] - ys[i - 1][0]);
  ok(ys.length > 30 && minGap >= ys[0][1], "horizontal row labels never overlap: " + ys.length + " rows, closest " + minGap.toFixed(1) + "px for " + (ys[0] || [0, 0])[1] + "px text");
  ok(!/<rect x='(?!0')[^>]* rx=/.test(hsvg), "horizontal bars are square");
  const box = win.document.getElementById("cmNotesBox");
  ok(box && box.tagName === "DETAILS" && !box.open, "notes sit in a collapsed details line");
  await new Promise(r => setTimeout(r, 30));
  ok(box.hidden === false, "notes line shows while Bar has a note");
  run(`chartType = "line"; syncBarModeVisibility && syncBarModeVisibility(); renderChart();`);
  const tn = win.document.getElementById("mtoggleNote").textContent.trim();
  await new Promise(r => setTimeout(r, 30));
  ok(box.hidden === !tn, "notes line hidden when there is nothing to say (" + (tn ? "has note" : "empty") + ")");
  ok(win.document.querySelector('#cmManyBarColourSeg button[data-mode="country"]').classList.contains("active"), "Country colours button active by default");
  // chooser: All countries and Clear
  run(`openChooser()`);
  const groups = () => win.document.getElementById("cmzGroups");
  const allBtn = groups().querySelector("button[data-all]");
  ok(!!allBtn && /All countries \(\d+\)/.test(allBtn.textContent), "chooser has All countries: " + (allBtn && allBtn.textContent));
  allBtn.click();
  const nAll = win.document.querySelectorAll("#cmzCountries input:checked").length;
  ok(nAll >= 60, "All countries ticks every country (" + nAll + ")");
  const clr = groups().querySelector("button[data-clear]");
  ok(!!clr, "Clear appears once countries are chosen");
  clr.click();
  ok(win.document.querySelectorAll("#cmzCountries input:checked").length === 0, "Clear unticks every country");
  win.close();
  // ---------------- Compare ----------------
  const boot2 = require("./compare_harness");
  const { win: w2, doc } = await boot2({ desktop: true, noMobile: true });
  const C = w2.EATLAS_COMPARE || {};
  doc.getElementById("addCountryBtn") ? doc.getElementById("addCountryBtn").click() : null;
  if(doc.getElementById("countryModal").hidden){ const b = [...doc.querySelectorAll("button")].find(x => /Add countries|Choose countries/.test(x.textContent)); if(b) b.click(); }
  ok(!doc.getElementById("countryModal").hidden, "country picker opens");
  const gb = [...doc.querySelectorAll("#pickerGroups button")].map(b => b.textContent);
  ok(["G7", "G20", "EU", "Euro area", "OECD", "BRICS"].every(n => gb.some(t => t.indexOf(n + " (") === 0)), "group buttons: " + gb.join(", "));
  const names = [...doc.querySelectorAll("#pickerRegions .picker-item")].map(l => l.textContent.trim());
  const sorted = names.slice().sort((a, b) => a.localeCompare(b));
  ok(names.length >= 60 && JSON.stringify(names) === JSON.stringify(sorted), "picker is one alphabetical list (" + names.length + ")");
  doc.getElementById("pickerClearAll").click();
  // signed out, Compare holds 4 countries: a group fills the free slots and flags the limit
  doc.querySelector('#pickerGroups button[data-g="0"]').click();
  ok([...doc.querySelectorAll("#chipRow .chip")].length === 4, "signed out, a group fills the 4 free slots");
  doc.getElementById("pickerClearAll").click();
  w2.EATLAS_PREFS = Object.assign(w2.EATLAS_PREFS || {}, { isLoggedIn: () => true, set(){} });   // signed in: no cap
  doc.querySelector('#pickerGroups button[data-g="0"]').click();
  const chips = [...doc.querySelectorAll("#chipRow .chip")].length;
  ok(chips === 7, "G7 button selects the 7 (" + chips + " chips)");
  ok(doc.querySelector('#pickerGroups button[data-g="0"]').classList.contains("on"), "G7 button shows as on");
  doc.querySelector('#pickerGroups button[data-g="0"]').click();
  ok([...doc.querySelectorAll("#chipRow .chip")].length === 0, "G7 button again removes them");
  const html = fs.readFileSync(path.join(ROOT, "compare.html"), "utf8");
  ok(/" so far" : ""/.test(html) && /Figures for " \+ firstReal\.year \+ " so far/.test(html), "the year in progress is labelled so far");
  console.log(`test_v208_polish: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
