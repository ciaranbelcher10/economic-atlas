#!/usr/bin/env python3
"""v1.6.45: euro-area current account from Eurostat bop_gdp6_q.

    python3 tools/test_ez_ca.py   # "N ok", exit 1 on failure
"""
import json, os, sys
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import fetch_ez  # noqa: E402

ok, fails = 0, []
def check(c, msg):
    global ok
    ok += bool(c)
    if not c: fails.append(msg)

def jstat(vals, extra_dim=None):
    years = list(vals)
    dims = {"time": {"category": {"index": {y: i for i, y in enumerate(years)}}},
            "geo": {"category": {"index": {"EA20": 0}}}}
    if extra_dim:
        dims["partner"] = {"category": {"index": {"A": 0, "B": 1}}}
    return json.dumps({"id": list(dims), "dimension": dims,
                       "value": {str(i): v for i, v in enumerate(vals.values())}})

class R:
    def __init__(self, code, text=""): self.status_code, self.text = code, text
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")

GOOD = {"2023": 1.7, "2024": 2.7, "2025": 1.6}
calls = []
def fake(responses):
    def g(url, **kw):
        calls.append(url)
        return responses.pop(0)
    return g

# 1. EA20 succeeds first time
calls.clear()
with mock.patch.object(fetch_ez.requests, "get", fake([R(200, jstat(GOOD))])):
    p = fetch_ez.fetch_eurostat_current_account()
check(p == [["2023", 1.7], ["2024", 2.7], ["2025", 1.6]] or
      p == [("2023", 1.7), ("2024", 2.7), ("2025", 1.6)] or
      (p and [list(x) for x in p] == [["2023", 1.7], ["2024", 2.7], ["2025", 1.6]]),
      f"EA20 parse: {p}")
u = calls[0]
for frag in ("bop_gdp6_q", "freq=A", "geo=EA20", "partner=EXT_EA20", "bop_item=CA",
             "stk_flow=BAL", "unit=PC_GDP", "s_adj=NSA"):
    check(frag in u, f"query has {frag}")
check(len(calls) == 1, "stops after first success")

# 2. EA20 fails (504) -> EA21 tried with matching partner
calls.clear()
with mock.patch.object(fetch_ez.requests, "get", fake([R(504), R(200, jstat(GOOD))])):
    p = fetch_ez.fetch_eurostat_current_account()
check(p and len(p) == 3, "falls back to EA21")
check(len(calls) == 2 and "geo=EA21" in calls[1] and "partner=EXT_EA21" in calls[1],
      "EA21 query uses EXT_EA21")

# 3. under-filtered (multi-series) response refused, both fail -> None
calls.clear()
with mock.patch.object(fetch_ez.requests, "get",
                       fake([R(200, jstat(GOOD, True)), R(200, jstat(GOOD, True))])):
    p = fetch_ez.fetch_eurostat_current_account()
check(p is None, "multi-series response refused")

# 4. all down -> None (guard then carries any previous series)
calls.clear()
with mock.patch.object(fetch_ez.requests, "get", fake([R(503), R(503)])):
    check(fetch_ez.fetch_eurostat_current_account() is None, "all down -> None")

# 5. wiring: World Bank no longer used for EZ current account; label cites dataset
src = open("fetch_ez.py", encoding="utf-8").read()
check('fetch_worldbank("BN.CAB.XOKA.GD.ZS")' not in src, "WB EMU current account removed")
check('("current_account", lambda: fetch_eurostat_current_account()' in src, "extras wired")
check("Eurostat bop_gdp6_q" in src, "label cites bop_gdp6_q")

# 6. citations agree on every surface
ms = json.load(open("data-metric-sources.json", encoding="utf-8"))
c = ms["Eurozone"]["current_account"]["source"]
check(c.startswith("Eurostat bop_gdp6_q") and "EA20" in c and "annual" in c, "metric-sources citation")
ez = open("eurozone.html", encoding="utf-8").read()
cmp_ = open("compare.html", encoding="utf-8").read()
check("World Bank \\u00b7 % of GDP, annual, euro-area aggregate" not in ez, "eurozone.html WB text gone")
check(ez.count("bop_gdp6_q") >= 2, "eurozone.html popover + chart cite bop_gdp6_q")
check("World Bank · % of GDP, annual, euro-area aggregate" not in cmp_, "compare.html WB text gone")
check('current_account: "Eurostat bop_gdp6_q' in cmp_, "compare.html cites bop_gdp6_q")

for f in fails: print("FAIL", f)
print(f"{ok} ok")
sys.exit(1 if fails else 0)
