#!/usr/bin/env python3
"""v1.9.116 checks: GDP per capita (complete calendar years / same year's population, offline),
generator metric, citation and US$ ranking, and the country pages' GDP section (order, USD$)."""
import glob, json, os, re, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import merge_population as mp  # noqa: E402
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()

# calendar years: complete only; summed, or averaged for annual-rate quarters
q = {"freq": "quarters", "unit": "£m", "points": [["2024-Q1", 1], ["2024-Q2", 2], ["2024-Q3", 3], ["2024-Q4", 4],
                                                   ["2025-Q1", 5], ["2025-Q2", 6], ["2025-Q3", 7]]}
check(mp.calendar_year_gdp(q, "UK") == {"2024": 10.0}, "quarters: complete years summed, part year left out")
check(mp.calendar_year_gdp(q, "US") == {"2024": 2.5}, "annual-rate quarters averaged (US, Japan)")
check(mp.calendar_year_gdp({"freq": "years", "points": [["2024", 7]]}, "X") == {"2024": 7.0}, "annual series as published")
# exact-year: per person uses that year's population only
g = {"freq": "years", "unit": "£m", "points": [["2023", 100], ["2024", 110], ["2025", 120], ["2026", 130]]}
s = mp.gdp_per_capita_series(g, [["2024", 2_000_000], ["2025", 2_200_000]], "UK", "2026-11-09T16:40:04Z")
check(s["points"] == [["2024", 55], ["2025", 55]], "per person: same year's population, years without one dropped")
check(s["unit"] == "£" and s["freq"] == "years" and s["derived"] is True, "per person: whole currency units, annual")
check(mp.gdp_per_capita_series({"unit": "%", "freq": "years", "points": [["2024", 1], ["2025", 2]]}, [["2024", 1], ["2025", 1]], "X", None) is None, "never from a percentage")

# merge writes both series, idempotently; Taiwan gets neither
d = tempfile.mkdtemp()
json.dump({"updated": "2026-11-09T16:40:04Z", "countries": {"UK": {"points": [["2024", 2_000_000], ["2025", 2_200_000]]}}}, open(os.path.join(d, "data-population.json"), "w"))
json.dump({"series": {"gdp_level": g}}, open(os.path.join(d, "data-uk.json"), "w"))
json.dump({"series": {"gdp_level": g}}, open(os.path.join(d, "data-tw.json"), "w"))
mp.main(d); S = json.load(open(os.path.join(d, "data-uk.json")))["series"]
check("population" in S and S.get("gdp_per_capita", {}).get("points") == [["2024", 55], ["2025", 55]], "merge: population and GDP per capita written")
b = open(os.path.join(d, "data-uk.json")).read(); mp.main(d)
check(open(os.path.join(d, "data-uk.json")).read() == b, "merge: idempotent")
check("gdp_per_capita" not in json.load(open(os.path.join(d, "data-tw.json")))["series"], "merge: no GDP per capita without population")
shutil.rmtree(d)

# generator
gen = read("generate_indicator_pages.py")
check('dict(slug="gdp-per-capita", keys=["gdp_per_capita"], title="GDP per Capita", cat="GDP & growth"' in gen, "generator: metric")
check('"gdp_per_capita"}' in gen.split("NATIVE_KEYS = {", 1)[1].split("\n", 1)[0], "generator: native symbols (A$, R$...)")
check('if "gdp_per_capita" in series and "gdp_per_capita" not in sources:' in gen, "generator: citation")
check('dict(slug="gdp-per-capita-by-country", metric="gdp-per-capita", title="GDP per Capita by Country", col="GDP per person (US$)", usd=True' in gen, "generator: US$ ranking")

# country pages
GEN = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html", "unemployment-by-country.html", "data-status.html"}
pages = [f for f in glob.glob(os.path.join(ROOT, "*.html")) if os.path.basename(f) not in GEN and 'id="tiles-gdp"' in open(f, encoding="utf-8").read()]
check(len(pages) >= 62, "62 country pages")
for f in pages:
    s = open(f, encoding="utf-8").read(); n = os.path.basename(f)
    tg = s.find('  const tg=document.getElementById("tiles-gdp");\n'); tinf = s.find('  const tinf=document.getElementById("tiles-inflation");\n')
    gpc = s.find('statTile(tg,"gdp_per_capita"')
    check(0 < tg < gpc < tinf, f"{n}: GDP per capita in the GDP tiles")
    check(s.count('statTile(tg,"gdp_per_capita"') == 1, f"{n}: one GDP per capita tile")
    check(len(re.findall(r'statTile\((tg|tmisc),"population"', s)) == 1, f"{n}: one population tile (Miscellaneous since v1.9.117)")
    check('chartPanel("gdp_per_capita","charts-gdp"' in s, f"{n}: GDP per capita chart in the GDP section")
    check('"imports","gdp_per_capita"];' in s, f"{n}: Convert to USD$ knows GDP per capita")
    check('gdp_per_capita:"gdp-per-capita", ' in s, f"{n}: tile links to its page")
    check('perHeadSym(' in s and 'curFmt(1,u+"m",0)' in s, f"{n}: symbol from the page's own formatter")
    if n != "us.html":
        check("out.gdp_per_capita = {...convertSeriesToUSD(out.gdp_per_capita, PAGE_DATA.fx_to_usd), unit:\"$\"};" in s
              and '!isAlreadyUSD(gu, "gdp_level")' in s, f"{n}: converts with GDP, never twice")

print(f"test_v19116: {checks} checks, {len(fails)} failed")
for x in fails[:20]: print("  FAIL", x)
sys.exit(1 if fails else 0)
