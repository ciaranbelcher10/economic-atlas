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
4. (v1.9.13) Every row is the same quarter, and it is the newest quarter that at
   least 75% of the countries with a usable growth series have published (v1.9.5;
   the page says so). Until v1.9.13 this test compared every row with Q4 of the
   last completed year, the rule before v1.9.5, so it failed on 42 correct rows.
   The selection rule is written out again below on purpose: changing it has to
   be done in both places.
Run after generate_indicator_pages.py.    python3 tools/test_growth_basis.py
"""
import datetime, glob, json, os, re, sys
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


def prev_q(p):
    y, q = int(p[:4]), int(p[-1])
    return f"{y - 1}-Q4" if q == 1 else f"{y}-Q{q - 1}"


periods = {r["period"] for r in rows}
check("every row is the same quarter", len(periods) == 1, sorted(periods))
# the newest quarter at least 75% of the eligible countries have published (eligible: has a usable growth series)
today = datetime.date.today()
qq, yy = (today.month - 1) // 3 + 1, today.year
cands = []
for _ in range(8):
    cands.append(f"{yy}-Q{qq}")
    qq, yy = (qq - 1, yy) if qq > 1 else (4, yy - 1)
have = {c: {t for t in cands if isinstance(gip._real_qoq_row(c, info, Y, t), dict)} for c, info in cat.items()}
eligible = sum(1 for v in have.values() if v)
want_period = next((t for t in cands if eligible and sum(1 for v in have.values() if t in v) >= 0.75 * eligible), f"{Y}-Q4")
check("ranking quarter is the newest with 75% coverage", periods == {want_period}, (sorted(periods), want_period))
for r in rows:
    info = cat[r["country"]]
    rs = info["data"]["series"].get("gdp_real", {})
    if rs.get("freq") == "quarters":
        d = dict(gip.clean_points(rs))
        per = r["period"]
        prv = prev_q(per)
        if per in d and prv in d:
            want = round((d[per] / d[prv] - 1) * 100, 2)
            check(f"{r['country']} row = real QoQ", abs(r["value"] - want) < 1e-9, (r["value"], want, per))
        else:
            check(f"{r['country']} row = real QoQ", False, f"no {per} / {prv} in gdp_real")
    else:
        lab = info["data"]["series"]["gdp_growth"]["label"]
        check(f"{r['country']} published rate is SA QoQ", "QoQ" in lab and "annualis" not in lab.lower(), lab)
names = {r["country"] for r in rows}
for c in ("India", "Argentina", "Singapore", "Thailand"):
    check(f"{c} not ranked", c not in names)
check("US ranked on real QoQ", "US" in names)
print(f"{ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
