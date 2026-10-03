#!/usr/bin/env python3
"""GDP growth basis gate (v1.6.33).

1. No fetcher derives gdp_growth from gdp_level (nominal). Mexico did, so
   its "real" growth included inflation.
2. No fetcher labels a gdp_growth QoQ when it is is derived from a not-seasonally-
   adjusted series (Argentina's QoQ showed the seasons: +9.6%, -5.2%).
3. The GDP growth ranking uses one definition: every ranked row equals the
   quarter-on-quarter change of seasonally adjusted quarterly real GDP, or a
   published SA quarter-on-quarter rate; nothing year on year, annualised or
   annual is ranked.
Run after generate_indicator_pages.py.    python3 tools/test_growth_basis.py
"""
import glob, json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL", name, detail)

for f in sorted(glob.glob("fetch_*.py")):
    s = open(f, encoding="utf-8").read()
    for m in re.finditer(r'out\["series"\]\["gdp_level"\]\["points"\]', s):
        ctx = s[m.start():m.start() + 400]
        check(f"{f}: gdp_growth not from nominal", "gdp_growth" not in ctx or "annual" in ctx.lower(), ctx[:120])

# Checked in the fetchers (what ships), not data-*.json (which follows an
# hour later, after CI runs them).
for f in sorted(glob.glob("fetch_*.py")):
    s = open(f, encoding="utf-8").read()
    for lab in re.findall(r'"label":\s*f?"(Real GDP growth[^"]*)"', s):
        check(f"{f}: QoQ not from NSA", not ("QoQ" in lab and re.search(r"NSA|NGDPRNSAXDC|NSAB1", lab)), lab)

import generate_indicator_pages as gip
cat = {}
for country, (iso2, cslug, a2, reg) in gip.COUNTRIES.items():
    path = gip.data_file_for(iso2)
    if not os.path.exists(path):
        continue
    data = json.load(open(path, encoding="utf-8"))
    sources = json.load(open("data-metric-sources.json", encoding="utf-8")).get(country, {})
    c = gip.build_country_catalogue(country, data, sources)
    cat[country] = dict(data=data, sources=sources, by_slug={e["m"]["slug"]: e for e in c})
rk = next(r for r in gip.RANKINGS if r["slug"] == "gdp-growth-rate-by-country")
rows, unranked = gip.rank_rows(rk, cat)
Y = gip.flow_year()
check("ranking has rows", len(rows) >= 20, len(rows))
for r in rows:
    info = cat[r["country"]]
    rs = info["data"]["series"].get("gdp_real", {})
    if rs.get("freq") == "quarters":
        d = dict(gip.clean_points(rs))
        q4, q3 = f"{Y}-Q4", f"{Y}-Q3"
        want = round((d[q4] / d[q3] - 1) * 100, 2)
        check(f"{r['country']} row = real QoQ", abs(r["value"] - want) < 1e-9, (r["value"], want))
    else:
        lab = info["data"]["series"]["gdp_growth"]["label"]
        check(f"{r['country']} published rate is SA QoQ", "QoQ" in lab and "annualis" not in lab.lower(), lab)
names = {r["country"] for r in rows}
for c in ("India", "Argentina", "Singapore", "Thailand"):
    check(f"{c} not ranked", c not in names)
check("US ranked on real QoQ", "US" in names)
print(f"{ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
