#!/usr/bin/env node
/* v1.9.119 Compare: a money card stays in the selected countries' shared currency (all euro, or one
   country alone) and converts to US$ only when currencies differ. Decided from each series'
   actual currency, never the "$" glyph. Run: NODE_PATH=/tmp/node_modules node tools/test_v19119.js */
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, "..");
const boot = require("./compare_harness");
let checks = 0, fails = 0;
const ok = (c, m) => { checks++; if(!c){ fails++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const data = f => JSON.parse(fs.readFileSync(path.join(ROOT, f), "utf8"));
const FILE = { Germany: "data-de.json", France: "data-fr.json", Italy: "data-it.json", Spain: "data-es.json",
  Netherlands: "data-nl.json", UK: "data-uk.json", US: "data-us.json", Australia: "data-au.json", Canada: "data-ca.json", Japan: "data-jp.json" };
const SCALE = u => { const c = u.replace(/\s*\(.*\)$/, ""); return /tn$/.test(c) ? 1e12 : /bn$/.test(c) ? 1e9 : /m$/.test(c) ? 1e6 : 1; };
// Published annual GDP, in millions of the country's own currency: four quarters summed
// (averaged for US/Japan, which publish at annual rates); an annual series as published.
function nativeGDP(country, year){
  const s = data(FILE[country]).series.gdp_level, sc = SCALE(s.unit) / 1e6;
  if (s.freq === "years") { const p = s.points.find(p => p[0] === String(year)); return p ? p[1] * sc : null; }
  const q = s.points.filter(p => p[0].startsWith(year + "-Q"));
  if (q.length !== 4) return null;
  const sum = q.reduce((a, p) => a + p[1], 0);
  return (country === "US" || country === "Japan" ? sum / 4 : sum) * sc;
}
(async () => {
  const { win, errs } = await boot({ desktop: true, noMobile: true });
  const api = win.EATLAS_COMPARE;
  ok(errs.length === 0, "no page errors: " + errs.join("; "));
  if (!api.getMetrics().includes("gdp_level")) api.addMetric("gdp_level");
  if (!api.getMetrics().includes("cpi")) api.addMetric("cpi");
  // signed in: no 4-country cap, so a full euro group plus one more fits
  win.EATLAS_PREFS = { isLoggedIn: () => true, set(){}, get(k, d){ return d; }, ready: Promise.resolve() };
  const pick = async arr => { api.setSelected(arr); await sleep(250); };
  const year = () => api.getCardTime("gdp_level").snapshotYear;

  // 1. all euro: euros, matching the published figures exactly
  const euro = ["Germany", "France", "Italy", "Spain", "Netherlands"];
  await pick(euro);
  ok(api.getSelected().length === 5, "five euro countries selected");
  ok(api.cardCurrency("gdp_level") === "EUR" && api.cardUnit("gdp_level") === "\u20acm", "all euro: card in euros (" + api.cardCurrency("gdp_level") + ")");
  const nat = {};
  for (const c of euro) {
    const dv = api.displayValue(c, "gdp_level"), want = nativeGDP(c, year());
    nat[c] = dv && dv.value;
    ok(dv && want != null && Math.abs(dv.value - want) <= Math.abs(want) * 1e-9 + 0.01, `all euro: ${c} ${year()} = published euros (${dv && dv.value} vs ${want})`);
    ok(dv && /^\u20ac/.test(api.displayString(dv)), `all euro: ${c} printed in euros (${dv && api.displayString(dv)})`);
  }
  ok(api.cardCurrency("cpi") === null, "a rate card has no currency");

  // 2. add the UK: the whole card converts to US$
  await pick(euro.concat(["UK"]));
  ok(api.getSelected().length === 6 && api.getSelected().includes("UK"), "UK added to all five");
  ok(api.cardCurrency("gdp_level") === "USD", "euro + UK: US dollars");
  for (const c of euro) {
    const dv = api.displayValue(c, "gdp_level");
    ok(dv && /^\$/.test(api.displayString(dv)), `euro + UK: ${c} printed in $ (${dv && api.displayString(dv)})`);
    const ratio = dv && nat[c] ? dv.value / nat[c] : 0;
    ok(ratio > 0.9 && ratio < 1.4, `euro + UK: ${c} converted at a EUR/USD rate (${ratio.toFixed(3)})`);
  }

  // 3. one country alone keeps its own currency
  await pick(["UK"]);
  ok(api.cardCurrency("gdp_level") === "GBP", "UK alone: pounds");
  const uk = api.displayValue("UK", "gdp_level");
  ok(uk && Math.abs(uk.value - nativeGDP("UK", year())) < 0.01 && /^\u00a3/.test(api.displayString(uk)), "UK alone: published pounds (" + (uk && api.displayString(uk)) + ")");
  await pick(["US"]);
  ok(api.cardCurrency("gdp_level") === "USD", "US alone: US dollars");
  await pick(["Australia"]);
  ok(api.cardCurrency("gdp_level") === "AUD", "Australia alone: Australian dollars");
  const au = api.displayValue("Australia", "gdp_level");
  ok(au && /^A\$/.test(api.displayString(au)), "Australia alone: printed A$ (" + (au && api.displayString(au)) + ")");

  // 4. the $ glyph is not a shared currency
  await pick(["Australia", "Canada"]);
  ok(api.cardCurrency("gdp_level") === "USD", "Australia + Canada: US dollars, not a shared \"$\"");
  await pick(["Australia", "US"]);
  ok(api.cardCurrency("gdp_level") === "USD", "Australia + US: US dollars");

  // 5. Per capita follows the card's currency
  await pick(euro);
  const btn = win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .card-percap-btn');
  btn.click(); await sleep(250);
  const de = api.displayValue("Germany", "gdp_level");
  const pop = Object.fromEntries(data("data-de.json").series.population.points)[String(year())];
  ok(de && pop && Math.abs(de.value * 1e6 - nativeGDP("Germany", year()) * 1e6 / pop) < 1, "all euro, per capita: euros per person");
  ok(de && /^\u20ac\d{1,3}(,\d{3})+$/.test(api.displayString(de)), "all euro, per capita: printed whole euros (" + (de && api.displayString(de)) + ")");
  btn.click(); await sleep(250);

  // 6. the line chart follows too: Germany's 2025 points in euros, in millions
  const lineBtn = win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .charttoggle button[data-mode="line"]');
  lineBtn.click(); await sleep(300);
  const ds = (api.chartData("gdp_level") || {datasets: []}).datasets.find(d => d.label === "Germany");
  const s = data("data-de.json").series.gdp_level, q4 = s.points.filter(p => p[0].startsWith(year() + "-Q"));
  const pt = ds && ds.data.find(p => p.x === year() + "-Q4");
  const want = q4.reduce((a, p) => a + p[1], 0) * SCALE(s.unit) / 1e6;
  ok(pt && Math.abs(pt.y - want) < 0.01, `all euro, line: Germany ${year()}-Q4 rolling year in euros (${pt && pt.y} vs ${want})`);
  win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .charttoggle button[data-mode="bar"]').click(); await sleep(300);
  // 6. card text says so
  const expl = win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .card-expl').textContent;
  ok(/Shown in euros/.test(expl), "all euro: card says it is shown in euros");
  await pick(euro.concat(["US"]));
  const expl2 = win.document.querySelector('#chartGrid .metric-card[data-concept="gdp_level"] .card-expl').textContent;
  ok(!/Shown in euros/.test(expl2), "mixed: no euro note");

  console.log(`test_v19119: ${checks} checks, ${fails} failed`);
  process.exit(fails ? 1 : 0);
})();
