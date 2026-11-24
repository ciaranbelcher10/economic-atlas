#!/usr/bin/env python3
"""v2.0.16: PPP data layer (ppp_data.py, merge_population.merge_ppp). Offline. python3 tools/test_v216_ppp_data.py"""
import datetime as dt, json, os, shutil, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import ppp_data as P, merge_population as M
fails = 0
def ok(c, m):
    global fails
    if not c: fails += 1; print("  FAIL", m)
c2n = {f"C{i}": f"N{i}" for i in range(55)}
fac = [{}, [{"country": {"id": k}, "date": y, "value": v} for k in c2n for y, v in (("2023", 1.9), ("2024", 2.0))]]
gdp = [{}, [{"country": {"id": k}, "date": "2024", "value": 50e9} for k in c2n]]
d = P.build_doc(fac, gdp, None, c2n, dt.date(2026, 11, 24))
ok(len(d["countries"]) == 55 and d["countries"]["N0"]["points"][-1] == ["2024", 2.0], "factors parsed")
try: P.build_doc([{}, fac[1][:10]], gdp, None, c2n); ok(False, "too few economies must not write")
except ValueError: pass
try: P.build_doc([{}, [r for r in fac[1] if r["date"] == "2023"]], gdp, None, c2n, dt.date(2030, 1, 1)); ok(False, "stale factors must not write")
except ValueError: pass
g = {"N0": {"freq": "years", "unit": "£bn", "points": [["2024", 100]]}, "N1": {"freq": "years", "unit": "£bn", "points": [["2024", 130]]}}
P.apply_checks(d, g)
ok(d["countries"]["N0"]["ok"] and abs(d["countries"]["N0"]["check"]["diff_pct"]) < 0.01, "matching GDP at PPP passes")
ok(not d["countries"]["N1"]["ok"] and "+30.0%" in d["countries"]["N1"]["reason"], "a 30% gap is not offered")
ok(not d["countries"]["N2"]["ok"], "no GDP to check against: not offered")
ok(P.calendar_years({"freq": "quarters", "unit": "$bn", "points": [["2024-Q1", 4], ["2024-Q2", 4], ["2024-Q3", 4], ["2024-Q4", 4], ["2025-Q1", 4]]}, "US") == {"2024": 4e9}, "US quarters at annual rate: mean; part year left out")
# merge into a copy of the real data files: only checked economies get a "ppp" series; idempotent; population untouched
tmp = tempfile.mkdtemp()
for f in os.listdir(ROOT):
    if f.startswith("data-") and f.endswith(".json"): shutil.copy(os.path.join(ROOT, f), tmp)
uk = M.calendar_year_gdp(json.load(open(os.path.join(tmp, "data-uk.json")))["series"]["gdp_level"], "UK") if hasattr(M, "calendar_year_gdp") else None
pop_before = json.load(open(os.path.join(tmp, "data-population.json")))["countries"]
P.save_doc({"countries": {"UK": {"points": [["2023", 0.672], ["2024", 0.675]], "gdp_ppp": [["2023", 4.15e12], ["2024", 4.31e12]]},
                          "Japan": {"points": [["2024", 95.0]], "gdp_ppp": [["2024", 4.0e12]]}}}, os.path.join(tmp, "data-population.json"))
M.merge_ppp(tmp)
S = json.load(open(os.path.join(tmp, "data-uk.json")))["series"]
ok(S.get("ppp", {}).get("points") == [["2023", 0.672], ["2024", 0.675]], "UK gets its checked factors")
ok(S["ppp"].get("real_anchor", {}).get("gdp_real", {}).get("year") == "2024", "real GDP priced in the newest year with a factor")
ok("ppp" not in json.load(open(os.path.join(tmp, "data-jp.json")))["series"], "Japan (failed check) gets none")
ok(json.load(open(os.path.join(tmp, "data-population.json")))["countries"] == pop_before, "population figures untouched")
before = {f: open(os.path.join(tmp, f)).read() for f in os.listdir(tmp)}
M.merge_ppp(tmp)
ok(all(open(os.path.join(tmp, f)).read() == before[f] for f in before), "second run changes nothing")
shutil.rmtree(tmp)
print(f"test_v216_ppp_data: {'all passed' if not fails else str(fails) + ' failed'}"); sys.exit(1 if fails else 0)
