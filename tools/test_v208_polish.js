#!/usr/bin/env node
/* v2.0.8 (v2.0.9: regions, slider label): Chartmaker and Compare polish.
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
  const vb = s => (s.match(/viewBox='0 0 ([\d.]+) ([\d.]+)'/) || []).slice(1).map(Number);
  const labelRows = s => [...s.matchAll(/<text x='[^']+' y='([\d.]+)' font-size='(\d+(?:\.\d+)?)' fill='[^']+' text-anchor='end'>([^<]*)</g)].map(m => [+m[1], +m[2], m[3]]).filter(r => !/^Made on/.test(r[2]));
  const golden = s => { const [w, h] = vb(s); return Math.abs(w / h - 820 / 507) < 0.005; };
  const noOverlap = ys => { let g = Infinity; for(let i = 1; i < ys.length; i++) g = Math.min(g, ys[i][0] - ys[i - 1][0]); return g >= ys[0][1]; };
  const [vw, vh] = vb(vsvg);
  run(`style.barOrient = "horizontal"; renderChart();`);
  const hsvg = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; SNAPSHOT_ROWS = buildSnapshotRows(); czmBuildBars("light", true)`));
  const [hw, hh] = vb(hsvg);
  ok(golden(vsvg) && golden(hsvg), "column and horizontal keep the golden ratio: " + vw + " x " + vh + ", " + hw + " x " + hh);
  let ys = labelRows(hsvg);
  ok(ys.length >= 3 && ys.every(r => +r[2] % 5 === 0) && noOverlap(ys), "51-year horizontal labels round years, no overlap: " + ys.map(r => r[2]).join(" "));
  ok(!/<rect x='(?!0')[^>]* rx=/.test(hsvg), "horizontal bars are square");
  run(`series.length = 0; Object.keys(REGISTRY).forEach(function(c){ addSeries(c, "bond_yield_10y", false, true); }); chartType = "bar"; style.barOrient = "horizontal"; syncBarLegendTitle(); renderChart();`);
  const csvg = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; SNAPSHOT_ROWS = buildSnapshotRows(); czmBuildBars("light", true)`));
  ys = labelRows(csvg);
  ok(golden(csvg), "every country horizontal still golden ratio (" + vb(csvg).join(" x ") + ")");
  run(`style.barOrient = "vertical"; renderChart();`);
  const cvs = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; SNAPSHOT_ROWS = buildSnapshotRows(); czmBuildBars("light", true)`));
  ok(golden(cvs), "every country vertical, long source footer, still golden ratio (" + vb(cvs).join(" x ") + ")");
  run(`chartType = "line"; renderChart();`);
  const lsv = String(run(`czmState = buildCzmState(); G.W = CM_DESK_W; czmBuildSVG("light", true)`));
  ok(golden(lsv), "every country line chart still golden ratio (" + vb(lsv).join(" x ") + ")");
  ok(ys.length >= 60 && noOverlap(ys) && ys[0][1] >= 8, "all " + ys.length + " countries labelled, " + (ys[0] || [0, 0])[1] + "px text, no overlap");
  run(`series.length = 0; addSeries("UK", "policy_rate", false, true); chartType = "bar"; style.barOrient = "vertical"; renderChart();`);
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
  const hs = [...win.document.querySelectorAll("#cmzCountries h4")].map(h => h.textContent);
  ok(hs.length >= 6 && hs.indexOf("Europe") !== -1 && hs.indexOf("Asia") !== -1, "chooser grouped by region: " + hs.join(", "));
  const firstGroup = []; let el = win.document.querySelector("#cmzCountries h4").nextElementSibling;
  while(el && el.tagName === "LABEL"){ firstGroup.push(el.textContent.replace(/No data$/, "").trim()); el = el.nextElementSibling; }
  ok(firstGroup.length > 3 && JSON.stringify(firstGroup) === JSON.stringify(firstGroup.slice().sort((a, b) => a.localeCompare(b))), "alphabetical within a region: " + firstGroup.slice(0, 5).join(", ") + "...");
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
  // v2.0.9: grouped by region, alphabetical within each region
  const regs = [...doc.querySelectorAll("#pickerRegions .picker-region")].map(s => ({ h: (s.querySelector("h4") || {}).textContent, n: [...s.querySelectorAll(".picker-item")].map(l => l.textContent.trim()) }));
  const total = regs.reduce((a, r) => a + r.n.length, 0);
  ok(regs.length >= 6 && regs.every(r => r.h) && total >= 60, "picker grouped by region: " + regs.map(r => r.h + " " + r.n.length).join(", "));
  ok(regs.every(r => JSON.stringify(r.n) === JSON.stringify(r.n.slice().sort((a, b) => a.localeCompare(b)))), "alphabetical within each region");
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
  ok((html.match(/snapLabel\.textContent = st\.snapshotYear \+ \(\+st\.snapshotYear >= new Date\(\)\.getFullYear\(\) \? " so far" : ""\)/g) || []).length === 2, "the year slider says so far for the year in progress");
  const sl = [...doc.querySelectorAll(".card-snapshot-label")].map(e => e.textContent);
  ok(sl.length === 0 || sl.every(s => !/^\d{4}$/.test(s) || +s < new Date().getFullYear()), "no slider shows the current year bare: " + sl.join(" | "));
  ok(/" so far" : ""/.test(html) && /Figures for " \+ firstReal\.year \+ " so far/.test(html), "the year in progress is labelled so far");
  console.log(`test_v208_polish: ${checks} checks, ${failures} failures`);
  process.exit(failures ? 1 : 0);
})().catch(e => { console.log("ERROR " + e.stack); process.exit(1); });
