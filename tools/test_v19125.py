#!/usr/bin/env python3
"""v1.9.125: Cyprus population covers the same area as its GDP; the World Bank cross-check compares
like with like. Offline (no network): simulated World Bank and Eurostat replies, real data files.

 1. fetch_population.build: Cyprus comes from Eurostat (nama_10_pe, government-controlled area), never
    from the World Bank rows, even when they are present; source and label say so.
 2. Eurostat fails: the last Eurostat copy is kept; with none, Cyprus is MISSING (no per capita),
    never filled with the World Bank whole-island figure. An implausible reply (the whole island,
    too short, starting too late) is refused the same way.
 3. merge_population: Cyprus population series and GDP per capita label name Eurostat; on the real
    Cyprus GDP, an area-matched population of about 1.04m gives about EUR 36,980 for 2025, within
    0.1% of the World Bank's own EUR 36,977 (the -24% gap is gone). Other economies unchanged.
 4. generate_indicator_pages.add_derived: Cyprus citations name Eurostat; the UK's still World Bank.
 5. cyprus.html: no "World Bank" population wording left; migrate_v19125 idempotent.
 6. Shared wording (percapita.js, Compare, Dashboard) names Eurostat for Cyprus; percapita.js?v=4.
 7. check_wb_gdp_per_capita: Switzerland compared in US$, Australia (unit "$") in its own currency.
Run: python3 tools/test_v19125.py
"""
import datetime as dt, json, os, re, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch_population as fp          # noqa: E402
import merge_population as mp          # noqa: E402

checks, fails = 0, []
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)

TODAY = dt.date(2026, 11, 10)
codes = fp.wb_codes()
def wb_payload():
    rows = []
    for code, name in codes.items():
        base = 1_370_000 if name == "Cyprus" else 5_000_000
        for y in range(1960, 2026):
            rows.append({"country": {"id": code}, "date": str(y), "value": int(base * (1.005 ** (y - 1960)))})
    return [{"page": 1}, rows]
def eurostat(first=1995, last=2025, base=650_000, step=1.012):
    years = [str(y) for y in range(first, last + 1)]
    return {"dimension": {"time": {"category": {"index": {y: i for i, y in enumerate(years)}}}},
            "value": {str(i): round(base * step ** i / 1000, 1) for i in range(len(years))}}   # thousands

# 1. Eurostat used, World Bank rows ignored
doc = fp.build(wb_payload(), {}, TODAY, coverage={"Cyprus": eurostat()})
cy = doc["countries"].get("Cyprus", {})
check(cy.get("source") == "Eurostat" and "nama_10_pe" in cy.get("label", ""), "Cyprus population from Eurostat nama_10_pe")
check(cy.get("points", [[0, 0]])[0][0] == "1995" and cy["points"][-1][0] == "2025", "Cyprus 1995 to 2025 (Eurostat range only)")
check(all(v < 1_250_000 for _, v in cy["points"]), "no whole-island World Bank value used for Cyprus")
check(abs(cy["points"][0][1] - 650_000) <= 100, "thousands converted to people")
check("Cyprus" not in doc["missing"], "Cyprus not missing when Eurostat replies")
check(doc["countries"]["UK"].get("wb_code") == "GB" and doc["countries"]["UK"]["points"][0][0] == "1960", "other economies still World Bank from 1960")

# 2. failure paths
d2 = fp.build(wb_payload(), {}, TODAY, coverage={"Cyprus": None})
check("Cyprus" not in d2["countries"] and "Cyprus" in d2["missing"], "Eurostat down, no earlier copy: Cyprus missing, not World Bank")
d3 = fp.build(wb_payload(), doc, TODAY, coverage={"Cyprus": None})
check(d3["countries"]["Cyprus"]["points"] == cy["points"] and "Cyprus" in d3["kept_previous"], "Eurostat down: last Eurostat copy kept")
prev_wb = {"countries": {"Cyprus": {"wb_code": "CY", "points": [[str(y), 1_300_000] for y in range(1960, 2026)]}}}
d4 = fp.build(wb_payload(), prev_wb, TODAY, coverage={"Cyprus": None})
check("Cyprus" not in d4["countries"], "an earlier World Bank copy of Cyprus is never kept")
for bad, why in ((eurostat(base=1_300_000, step=1.003), "whole island"), (eurostat(first=2015), "starts too late"),
                 (eurostat(first=2018, last=2025), "too short"), ({"oops": 1}, "malformed")):
    d5 = fp.build(wb_payload(), {}, TODAY, coverage={"Cyprus": bad})
    check("Cyprus" not in d5["countries"], f"implausible Eurostat reply refused ({why})")
d6 = fp.build(wb_payload(), {}, TODAY, coverage={"Cyprus": eurostat(base=650_000, step=1.25)})
check("Cyprus" not in d6["countries"], "a break in the Eurostat series is refused")

# 3. merge_population on the real Cyprus file
tmp = tempfile.mkdtemp()
try:
    shutil.copy(os.path.join(ROOT, "data-cy.json"), tmp); shutil.copy(os.path.join(ROOT, "data-uk.json"), tmp)
    real = eurostat(first=1995, last=2025, base=1_036_000 / 1.012 ** 30)   # 2025 about 1.036m
    pop_doc = fp.build(wb_payload(), {}, TODAY, coverage={"Cyprus": real})
    json.dump(pop_doc, open(os.path.join(tmp, "data-population.json"), "w"))
    mp.main(tmp)
    S = json.load(open(os.path.join(tmp, "data-cy.json")))["series"]
    check(S["population"]["source"] == "Eurostat" and "government-controlled" in S["population"]["label"], "Cyprus population series names Eurostat")
    check("Eurostat population" in S["gdp_per_capita"]["label"], "Cyprus GDP per capita label names Eurostat")
    g25 = dict(S["gdp_per_capita"]["points"]).get("2025")
    check(g25 and abs(g25 / 36977 - 1) < 0.001, f"Cyprus 2025 GDP per person {g25} within 0.1% of World Bank 36,977")
    U = json.load(open(os.path.join(tmp, "data-uk.json")))["series"]
    check(U["population"]["source"] == "World Bank" and "World Bank population" in U["gdp_per_capita"]["label"], "UK still World Bank")
finally:
    shutil.rmtree(tmp)

# 4. generator citations
import generate_indicator_pages as g   # noqa: E402
cyd = json.load(open(os.path.join(ROOT, "data-cy.json")))
cyd["series"]["population"] = {"label": fp.COVERAGE_SOURCE["Cyprus"]["label"], "source": "Eurostat", "unit": "people", "freq": "years",
                               "points": [["2024", 1020000], ["2025", 1036000]]}
cyd["series"]["gdp_per_capita"] = {"unit": "\u20ac", "freq": "years", "points": [["2024", 1], ["2025", 2]]}
_, src = g.add_derived("Cyprus", cyd, {"gdp_level": {"source": "Eurostat namq_10_gdp"}})
check(src["population"]["source"].startswith("Eurostat") and "World Bank" not in src["population"]["source"], "generator: Cyprus population cited as Eurostat")
check("Population: Eurostat" in src["gdp_per_capita"]["source"], "generator: Cyprus GDP per capita cites Eurostat population")
ukd = json.load(open(os.path.join(ROOT, "data-uk.json")))
_, usrc = g.add_derived("UK", ukd, {"gdp_level": {"source": "ONS"}})
check(usrc["population"]["source"].startswith("World Bank"), "generator: UK population still World Bank")

# 5. Cyprus page
cyp = open(os.path.join(ROOT, "cyprus.html"), encoding="utf-8").read()
check("v1.9.125 Cyprus population" in cyp, "cyprus.html migrated")
check(not re.search(r"World Bank[^\"']{0,40}(SP\.POP|population)|population \(World Bank\)|World Bank does not publish a population", cyp), "cyprus.html: no World Bank population wording")
check(cyp.count("Eurostat population (same area)") == 2, "both GDP per capita tiles cite Eurostat population")
r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "migrate_v19125.py"), ROOT], capture_output=True, text=True)
check(r.stdout.strip() == "1 page(s) checked, 0 changed", "migrate_v19125 idempotent: " + r.stdout.strip())

# 6. shared wording and version
pc = open(os.path.join(ROOT, "percapita.js"), encoding="utf-8").read()
check("Eurostat for Cyprus" in pc and "(World Bank)." not in pc, "percapita.js note names Eurostat for Cyprus")
for f in ("compare.html", "dashboard.html"):
    t = open(os.path.join(ROOT, f), encoding="utf-8").read()
    check("(World Bank)" not in t and "Eurostat for Cyprus" in t, f + ": population wording names Eurostat for Cyprus")
for f in ("compare.html", "dashboard.html", "chartmaker.html", "uk.html", "cyprus.html"):
    t = open(os.path.join(ROOT, f), encoding="utf-8").read()
    check(t.count("percapita.js?v=4") == 1 and not re.search(r"percapita\.js\?v=[0-3]\b", t), f + ": percapita.js?v=4")
check('PERCAPITA_VERSION = "4"' in open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read(), "indicator pages load percapita.js v4")

# 7. cross-check compares like with like
import check_wb_gdp_per_capita as wbc   # noqa: E402
usd = wbc.already_usd()
check(wbc.indicator_for("Switzerland", usd) == wbc.USD, "Switzerland (held in US$) compared with NY.GDP.PCAP.CD")
check(all(wbc.indicator_for(n, usd) == wbc.LOCAL for n in ("Australia", "Canada", "Mexico", "Cyprus", "UK")), "\"$\"-unit local currencies compared in their own currency")

print(f"test_v19125: {checks} checks, {len(fails)} failed")
for m in fails: print("  FAIL", m)
sys.exit(1 if fails else 0)
