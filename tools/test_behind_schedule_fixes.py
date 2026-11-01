"""v1.9.55: the behind-schedule series (item 1 of the v2.0 list).

    python3 tools/test_behind_schedule_fixes.py   -> "N ok, 0 failed"

1. Canada and India business confidence are retired: not fetched, and dropped after the guard even
   though the guard carries missing series forward.
2. The IMF overlay for Chile/Colombia deficit and Morocco debt asks api.imf.org (imf_weo), not the
   DataMapper URL that answers 403 to GitHub's runners; a failed or disagreeing answer keeps the FRED copy.
3. awaiting_sources.json: Colombia trade balance is awaiting; the retired series are not listed.
Offline.
"""
import io, json, os, re, sys
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import imf_datamapper as DM  # noqa: E402
import imf_weo  # noqa: E402

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

# 1. retired series
for f, last in (("fetch_ca.py", "April 2026"), ("fetch_in.py", "February 2026")):
    src = open(os.path.join(ROOT, f), encoding="utf-8").read()
    extras = src[src.index("extras = ["):src.index("for name, fn, label, unit, fr in extras")]
    check('"business_confidence"' not in extras, f"{f}: business confidence no longer fetched")
    check(re.search(r'RETIRED = \{"business_confidence": "OECD stopped publishing it after ' + last + r'"\}', src), f"{f}: RETIRED names the series and why")
    main = src[src.index("def main"):]
    g, r = main.find("series_guard.apply_guard("), main.find("for _k, _why in RETIRED.items():")
    check(0 < g < r, f"{f}: retired keys are dropped after the guard, so it cannot carry them forward")
    check('out["series"].pop(_k, None)' in main and 'print(f"RETIRED {_k}: {_why}")' in main, f"{f}: drop is logged")
# the drop itself, run the way main runs it
series = {"business_confidence": {"points": [["2026-02", 95.4]]}, "cpi": {"points": [["2026-08", 3.0]]}}
RETIRED = {"business_confidence": "x"}
with redirect_stdout(io.StringIO()) as buf:
    for _k, _why in RETIRED.items():
        if series.pop(_k, None) is not None:
            print(f"RETIRED {_k}: {_why}")
check(list(series) == ["cpi"] and "RETIRED business_confidence" in buf.getvalue(), "the drop removes only the retired key")

# 2. overlay goes through imf_weo
check(DM.overlay.__defaults__[0] is DM.fetch_weo, "overlay asks imf_weo by default, not the DataMapper URL")
calls = []
real = imf_weo.fetch
try:
    imf_weo.fetch = lambda iso3, ind: (calls.append((iso3, ind)), [["2024", -2.9], ["2025", -2.4]])[1]
    s = {"deficit": {"label": "FRED copy", "points": [["2023", -2.4], ["2024", -2.739]]}}
    with redirect_stdout(io.StringIO()):
        note = DM.overlay(s, "deficit", "GGXCNL_NGDP", "CHL", "General government net lending/borrowing, % of GDP (IMF World Economic Outlook, GGXCNL_NGDP)")
    check(calls == [("CHL", "GGXCNL_NGDP")], f"imf_weo asked with country first: {calls}")
    check("DataMapper applied" in note and s["deficit"]["points"][-1] == ["2025", -2.4], f"IMF's 2025 replaces the 2024-only copy: {note}")
    check("DataMapper" not in s["deficit"]["label"] and "GGXCNL_NGDP" in s["deficit"]["label"], "label names the IMF code, not the DataMapper")
    imf_weo.fetch = lambda iso3, ind: None          # a 403 or any failure
    s = {"deficit": {"label": "FRED copy", "points": [["2024", -2.739]]}}
    with redirect_stdout(io.StringIO()):
        note = DM.overlay(s, "deficit", "GGXCNL_NGDP", "COL", "x")
    check(s["deficit"]["label"] == "FRED copy" and "unavailable" in note, "a failed IMF answer keeps the FRED copy")
    imf_weo.fetch = lambda iso3, ind: [["2023", 75.0], ["2024", 76.0]]   # disagrees by more than 1.5 points
    s = {"debt_gdp": {"label": "FRED copy", "points": [["2022", 69.0], ["2023", 69.47]]}}
    with redirect_stdout(io.StringIO()):
        note = DM.overlay(s, "debt_gdp", "GGXWDG_NGDP", "MAR", "x")
    check(s["debt_gdp"]["label"] == "FRED copy" and "differs" in note, "a disagreeing IMF series keeps the FRED copy")
finally:
    imf_weo.fetch = real
for f, code in (("fetch_cl.py", "GGXCNL_NGDP"), ("fetch_co.py", "GGXCNL_NGDP"), ("fetch_ma.py", "GGXWDG_NGDP")):
    src = open(os.path.join(ROOT, f), encoding="utf-8").read()
    check(f"(IMF World Economic Outlook, {code})" in src and "DataMapper GG" not in src, f"{f}: label names the IMF code")
cites = open(os.path.join(ROOT, "data-metric-sources.json"), encoding="utf-8").read()
check("via the IMF DataMapper" not in cites, "no citation still says the figures come via the DataMapper")

# 3. awaiting list
aw = json.load(open(os.path.join(ROOT, "awaiting_sources.json"), encoding="utf-8"))["series"]
pairs = {(e["economy"], k) for e in aw for k in e["keys"]}
check(("Colombia", "trade_balance") in pairs, "Colombia trade balance is awaiting the OECD")
check(not {("Canada", "business_confidence"), ("India", "business_confidence")} & pairs, "retired series are not listed as awaiting")
check(not {("Chile", "deficit"), ("Colombia", "deficit")} & pairs, "Chile and Colombia deficits are not parked as awaiting; IMF serves them now")

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
