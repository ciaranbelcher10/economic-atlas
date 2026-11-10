// v1.9.116: percapita.js against every economy's real data. Exact-year rule: each point divided
// by its own year's population; periods without one dropped and named.
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, "..");
const PC = require(path.join(ROOT, "percapita.js"));
let checks = 0, fails = [];
const ok = (c, m) => { checks++; if(!c) fails.push(m); };

// units and scale
ok(PC.scaleOf("£m") === 1e6 && PC.scaleOf("$bn") === 1e9 && PC.scaleOf("€tn") === 1e12 && PC.scaleOf("CNYm") === 1e6 && PC.scaleOf("¥") === 1, "scaleOf");
ok(PC.unitLabel("£m") === "£ per person" && PC.unitLabel("US$bn") === "US$ per person", "unitLabel");
ok(PC.eligible("gdp_level") && PC.eligible("trade_balance") && !PC.eligible("cpi") && !PC.eligible("debt_gdp") && !PC.eligible("population"), "eligible metrics");

// synthetic: exact year, drops, note
const pop = [["2024", 1000], ["2025", 2000]];
const r = PC.divide([{x:"2024-Q4", y:5}, {x:"2025-Q1", y:8}, {x:"2026-Q1", y:9}, {x:"2023", y:1}], "£k", pop);
ok(JSON.stringify(r.pts) === JSON.stringify([{x:"2024-Q4", y:5}, {x:"2025-Q1", y:4}]), "divide uses each period's own year");
ok(JSON.stringify(r.droppedYears) === '["2023","2026"]' && r.droppedCount === 2, "dropped years named");
const n = PC.note(r.droppedYears, PC.latestYear(pop));
ok(/2026 not shown: population for 2026 not yet published\./.test(n), "note: future year");
ok(/2023 not shown: no population figure for that year\./.test(n), "note: early year");
ok(PC.divide([{x:"2025", y:1}], "£m", []).ok === false, "no population at all -> ok false");
ok(/not available for this economy/.test(PC.note([], null, true)), "note: no population");

// every real economy, every eligible series
let series = 0, points = 0, maxErr = 0;
for (const f of fs.readdirSync(ROOT).filter(f => /^data-[a-z]{2}\.json$/.test(f))) {
  const d = JSON.parse(fs.readFileSync(path.join(ROOT, f), "utf8")), S = d.series || {};
  if (!S.population) continue;
  const idx = PC.popIndex(S.population.points);
  for (const k of PC.ELIGIBLE) {
    const s = S[k]; if (!s || !s.points || /%|index/.test(s.unit || "")) continue;
    const pts = s.points.filter(p => p[1] != null).map(p => ({x: p[0], y: p[1]}));
    const out = PC.divide(pts, s.unit, S.population.points);
    series++;
    const kept = pts.filter(p => idx[String(p.x).slice(0,4)]);
    ok(out.pts.length === kept.length, `${f} ${k}: kept exactly the periods with a population`);
    out.pts.forEach((p, i) => {
      points++;
      const want = kept[i].y * PC.scaleOf(s.unit) / idx[String(kept[i].x).slice(0,4)];
      maxErr = Math.max(maxErr, Math.abs(p.y - want) / Math.max(1, Math.abs(want)));
      // a neighbouring year's population must never give this value
      const y = +String(p.x).slice(0,4), other = idx[String(y-1)] || idx[String(y+1)];
      if (other && other !== idx[String(y)]) ok(Math.abs(p.y - kept[i].y * PC.scaleOf(s.unit) / other) > 1e-9 * Math.abs(p.y), `${f} ${k} ${p.x}: matches another year`);
    });
    out.droppedYears.forEach(y => ok(!idx[y], `${f} ${k}: dropped ${y} though population exists`));
  }
}
ok(series > 200, `covered many series (${series})`);
ok(maxErr < 1e-12, `exact arithmetic (max rel err ${maxErr})`);

// sanity: UK GDP per person, 2025, annual total of quarters (country pages annualise the same way)
const uk = JSON.parse(fs.readFileSync(path.join(ROOT, "data-uk.json"), "utf8")).series;
const q25 = uk.gdp_level.points.filter(p => String(p[0]).startsWith("2025-Q"));
if (q25.length === 4) {
  const annual = q25.reduce((a, p) => a + p[1], 0);
  const pp = PC.divide([{x: "2025", y: annual}], uk.gdp_level.unit, uk.population.points).pts[0].y;
  ok(pp > 38000 && pp < 46000, `UK 2025 GDP per person plausible (£${Math.round(pp)})`);
  console.log(`  UK 2025 GDP per person: £${Math.round(pp).toLocaleString("en-GB")}`);
}
console.log(`test_v19118_percapita: ${checks} checks (${series} series, ${points} points), ${fails.length} failed`);
fails.slice(0, 15).forEach(m => console.log("  FAIL", m));
process.exit(fails.length ? 1 : 0);
