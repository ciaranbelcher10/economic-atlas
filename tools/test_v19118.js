#!/usr/bin/env node
/* v1.9.118: Compare + Dashboard per capita and pickers, Miscellaneous freshness key, centred short
   tile rows (desktop only), Latest banner names. Run: NODE_PATH=/tmp/node_modules node tools/test_v19118.js */
const fs = require("fs"), path = require("path");
const ROOT = path.join(__dirname, "..");
const PC = require(path.join(ROOT, "percapita.js"));
const boot = require("./compare_harness");
let checks = 0, fails = 0;
const ok = (c, m) => { checks++; if(!c){ fails++; console.log("  FAIL  " + m); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");

(async () => {
  // ---------- Compare ----------
  const { win, doc, errs } = await boot({ desktop: true, noMobile: true });
  const api = win.EATLAS_COMPARE;
  ok(errs.length === 0, "Compare: no page errors: " + errs.join("; "));
  const keys = api.allMetrics().map(m => m.key);
  ok(keys.includes("gdp_per_capita") && keys.includes("population"), "Compare: GDP per capita and Population in the picker");
  ok(/"Miscellaneous"\]/.test(read("compare.html")) , "Compare: Miscellaneous category listed");
  for (const k of ["gdp_level", "gdp_per_capita", "population", "cpi"]) if (!api.getMetrics().includes(k)) api.addMetric(k);
  await sleep(400);
  const card = k => doc.querySelector('#chartGrid .metric-card[data-concept="' + k + '"]');
  ok(card("gdp_level") && card("gdp_level").querySelector(".card-percap-btn"), "Compare: Per capita button on GDP level");
  ok(card("cpi") && !card("cpi").querySelector(".card-percap-btn"), "Compare: no Per capita button on inflation");
  ok(card("gdp_per_capita") && !card("gdp_per_capita").querySelector(".card-percap-btn"), "Compare: no Per capita button on GDP per capita itself");
  const countries = api.getSelected();
  const total = {}; countries.forEach(c => total[c] = api.displayValue(c, "gdp_level"));
  card("gdp_level").querySelector(".card-percap-btn").click(); await sleep(300);
  ok(api.getPercap("gdp_level") === true, "Compare: Per capita switches on");
  ok(card("gdp_level").querySelector(".card-percap-btn").getAttribute("aria-pressed") === "true", "Compare: button pressed state");
  ok(/per person/.test(card("gdp_level").querySelector(".card-title").textContent), "Compare: title says per person");
  let compared = 0;
  for (const c of countries) {
    const dv = api.displayValue(c, "gdp_level"), t = total[c];
    if (!t) continue;
    const file = { UK: "data-uk.json", US: "data-us.json", Germany: "data-de.json", Japan: "data-jp.json" }[c];
    const pop = PC.popIndex(JSON.parse(read(file)).series.population.points)[String(t.year)];
    if (!pop) { ok(dv == null, `Compare: ${c} ${t.year} has no population, so no per-person figure`); continue; }
    ok(dv && Math.abs(dv.value - t.value / pop) <= Math.abs(t.value / pop) * 1e-6, `Compare: ${c} ${t.year} = total / that year's population (${dv && dv.value} vs ${t.value / pop})`);
    const s = api.displayString(dv);
    ok(/^\$\d{1,3}(,\d{3})+$/.test(s), `Compare: ${c} per-person figure printed whole (${s})`);
    compared++;
  }
  ok(compared >= 3, "Compare: per capita checked for at least 3 economies");
  // exact-year rule: a year without population is never filled
  const st = api.getCardTime("gdp_level");
  ok(/population/.test(api.noDataReason("UK", "gdp_level", 2099) || "") || api.displayValue("UK", "gdp_level") != null, "Compare: reason available");
  // GDP per capita concept: UK in US$ = £ figure converted
  const gpc = api.displayValue("UK", "gdp_per_capita");
  ok(gpc && gpc.value > 0.04 && gpc.value < 0.08, "Compare: UK GDP per capita in US$ (" + (gpc && api.displayString(gpc)) + ")");
  const pop = api.displayValue("UK", "population");
  ok(pop && /^\d+\.\dm$/.test(api.displayString(pop)), "Compare: population printed as millions (" + (pop && api.displayString(pop)) + ")");
  // saved and restored
  ok(/percap: !!st\.percap/.test(read("compare.html")) && /percap: v\.percap === true/.test(read("compare.html")), "Compare: Per capita saved and restored");
  // ---------- Compare & Chartmaker unitCompatible identical (also in test_dollarise_parity) ----------
  const fn = (src, n) => { const i = src.indexOf("function " + n + "("); return src.slice(i, src.indexOf("\n}\n", i)); };
  ok(fn(read("compare.html"), "unitCompatible") === fn(read("chartmaker.html"), "unitCompatible"), "unitCompatible identical in Compare and Chartmaker");

  // ---------- Dashboard ----------
  const dash = read("dashboard.html");
  ok(/gdp_per_capita: "Miscellaneous", population: "Miscellaneous"/.test(dash), "Dashboard: both in Miscellaneous");
  ok(/"Exchange rates", "Miscellaneous", "Other"\]/.test(dash), "Dashboard: Miscellaneous category ordered");
  ok(/gdp_per_capita: "GDP per capita", population: "Population"/.test(dash), "Dashboard: labels");
  ok(/if\(unit === "people"\) return peopleFmt\(v\);/.test(dash), "Dashboard: population formatted");

  // ---------- Country pages ----------
  const pages = fs.readdirSync(ROOT).filter(f => f.endsWith(".html") && read(f).includes('prefix.textContent="Latest:"'));
  ok(pages.length === 62, "62 country pages");
  for (const f of pages) {
    const s = read(f);
    for (const sec of ["headline", "gdp", "inflation", "labour", "trade", "public", "markets", "misc"]) {
      const i = s.indexOf('id="sec-' + sec + '"'); if (i < 0) continue;
      const j = s.indexOf("</section>", i);
      ok((s.slice(i, j).match(/class="lightskey( compact)?"/g) || []).length === 1, `${f}: ${sec} has exactly one freshness key`);
    }
    const a = s.indexOf("const _KEY_NAMES="), b = s.indexOf("function renderNewDataBanner", a);
    const nameOf = new Function(s.slice(a, b) + "; return _nameOf;")();
    ok(nameOf("gdp_per_capita") === "GDP per capita" && nameOf("population") === "Population", `${f}: banner names`);
    ok(nameOf("gdp_real_quarterly") === "GDP real quarterly" && nameOf("core_cpi_sa") === "Core CPI sa", `${f}: fallback keeps acronyms`);
  }

  // ---------- Tile centring (desktop only; phones left-aligned) ----------
  const css = read("mobile.css");
  const want = [[1181, 5], [961, 4], [761, 3]];
  for (const [, cols] of want)
    for (let k = 1; k < cols; k++)
      ok(css.includes(`body .hero > .stat:nth-child(${cols}n+1):nth-last-child(${k}){ grid-column:${cols - k + 1} / span 2; }`), `centre ${k} of ${cols}`);
  ok(/repeat\(10,minmax\(0,1fr\)\)/.test(css) && /repeat\(8,minmax\(0,1fr\)\)/.test(css) && /repeat\(6,minmax\(0,1fr\)\)/.test(css), "two tracks per column at each width");
  const phone = css.slice(css.indexOf("@media (max-width:760px)"));
  ok(!/nth-last-child\(1\)\{ grid-column/.test(phone.slice(0, phone.indexOf("\n}\n"))), "phones: no centring (single tile stays left)");

  console.log(`test_v19118: ${checks} checks, ${fails} failed`);
  process.exit(fails ? 1 : 0);
})();
