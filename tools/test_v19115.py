#!/usr/bin/env python3
"""v1.9.115 checks: population merged into each data file (offline), generator pages and ranking,
country-page chart, tile and 'Not available' fallback, and the workflow step."""
import json, os, shutil, sys, tempfile, glob, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import merge_population as mp  # noqa: E402
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()

# merge (offline, temp dir)
d = tempfile.mkdtemp()
json.dump({"updated": "2026-11-09T16:40:04Z", "countries": {"UK": {"points": [["2024", 69281000], ["2025", 69487000]]}}},
          open(os.path.join(d, "data-population.json"), "w"))
json.dump({"series": {"fdi": {"unit": "%", "points": [["2025", 1.0]]}}}, open(os.path.join(d, "data-uk.json"), "w"))
json.dump({"series": {}}, open(os.path.join(d, "data-tw.json"), "w"))
mp.main(d); uk = json.load(open(os.path.join(d, "data-uk.json")))["series"]
check(uk.get("population", {}).get("points") == [["2024", 69281000], ["2025", 69487000]], "merge: UK population points")
check(uk["population"]["unit"] == "people" and uk["population"]["freq"] == "years", "merge: unit and frequency")
check(uk["population"]["confirmed_at"] == "2026-11-09T16:40Z", "merge: confirmed_at in the data files' format")
check("fdi" in uk, "merge: other series untouched")
check("population" not in json.load(open(os.path.join(d, "data-tw.json")))["series"], "merge: Taiwan not given a series")
before = open(os.path.join(d, "data-uk.json")).read(); mp.main(d)
check(open(os.path.join(d, "data-uk.json")).read() == before, "merge: idempotent")
os.remove(os.path.join(d, "data-population.json")); mp.main(d)
check(open(os.path.join(d, "data-uk.json")).read() == before, "merge: missing population file changes nothing")
shutil.rmtree(d)

# generator
g = read("generate_indicator_pages.py")
check('dict(slug="population", keys=["population"], title="Population", cat="Population"' in g, "generator: population metric")
check('"Population"]' in g.split("CATEGORIES = [", 1)[1].split("\n", 1)[0], "generator: Population category")
check('dict(slug="population-by-country", metric="population"' in g, "generator: population ranking")
check('if "population" in series and "population" not in sources:' in g and "SP.POP.TOTL" in g, "generator: built-in citation")

# country pages
GEN = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html", "unemployment-by-country.html", "data-status.html"}
pages = [f for f in glob.glob(os.path.join(ROOT, "*.html")) if os.path.basename(f) not in GEN and 'id="tiles-gdp"' in open(f, encoding="utf-8").read()]
check(len(pages) >= 62, f"62 country pages (found {len(pages)})")
for f in pages:
    s = open(f, encoding="utf-8").read(); n = os.path.basename(f)
    check(s.count('chartPanel("population","charts-gdp"') == 1, f"{n}: population chart in the GDP section")
    check(s.count('statTile(tg,"population","Population",s.population,') == 1, f"{n}: population tile in the GDP tiles")
    check("fmtD:fmtPeople," in s and "fmtPeopleD" not in s, f"{n}: delta formatter leaves the sign to statTile")
    check('Not available</p>' in s and 'World Bank does not publish a population figure' in s, f'{n}: Not available fallback')
    _m = re.search(r"const INDICATOR_PAGE_SLUGS = \{([^}]*)\}", s)
    check(bool(_m) and 'population:"population"' in _m.group(1), f"{n}: tile links to its page")
    check(s.index('chartPanel("population"') < s.index('statTile(tg,"population"'), f"{n}: chart before tile")

# workflow
wf = read(".github/workflows/update-data.yml")
i_f, i_m, i_c = wf.find("Run fetch_population.py"), wf.find("- name: Merge population into data files"), wf.find("- name: Commit updated data")
check(0 < i_f < i_m < i_c, "workflow: merge runs after the fetch and before the data commit")
check("python merge_population.py 2>&1 | tee -a pipeline_log.txt" in wf, "workflow: merge logs")
check(wf[i_m:i_c].count("continue-on-error: true") >= 1, "workflow: merge cannot fail the job")

print(f"test_v19115: {checks} checks, {len(fails)} failed")
for x in fails[:20]: print("  FAIL", x)
sys.exit(1 if fails else 0)
