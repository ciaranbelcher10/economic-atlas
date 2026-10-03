#!/usr/bin/env python3
"""Offline tests for eurostat_gdp.py and its wiring into fetch_at/dk/nl (v1.6.32).

    python3 tools/test_eurostat_gdp.py     # prints "N ok", exit 0
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import eurostat_gdp as eg

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print("FAIL", name)

def payload(periods, values, as_list=False):
    idx = {p: i for i, p in enumerate(periods)}
    vals = values if as_list else {str(i): v for i, v in enumerate(values) if v is not None}
    return {"dimension": {"time": {"category": {"index": idx}}}, "value": vals}

def quarters(y0, n):
    return [f"{y0 + i // 4}-Q{i % 4 + 1}" for i in range(n)]

# parse: dict values, gaps dropped, sorted
pts = eg.parse(payload(["1995-Q2", "1995-Q1", "1995-Q3"], [2.0, 1.0, None]))
check("parse dict + gap", pts == [["1995-Q1", 1.0], ["1995-Q2", 2.0]])
check("parse list form", eg.parse(payload(["1995-Q1", "1995-Q2"], [1.5, None], as_list=True)) == [["1995-Q1", 1.5]])

class R:
    def __init__(self, js, code=200): self.js, self.status_code = js, code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
    def json(self): return self.js

def with_reply(js, code=200):
    calls = []
    def get(url, **kw):
        calls.append(url); return R(js, code)
    eg.requests.get = get
    return calls

full = payload(quarters(1995, 126), [100.0 + i for i in range(126)])
calls = with_reply(full)
p = eg.fetch("DK", "CLV20_MNAC")
check("fetch accepts full history", p is not None and len(p) == 126 and p[0][0] == "1995-Q1")
check("query has geo/unit/SCA/B1GQ", all(x in calls[0] for x in ("geo=DK", "unit=CLV20_MNAC", "s_adj=SCA", "na_item=B1GQ")))
with_reply(payload(quarters(2010, 66), [1.0] * 66))
check("rejects late start", eg.fetch("NL", "CP_MEUR") is None)
with_reply(payload(quarters(1995, 50), [1.0] * 50))
check("rejects short history", eg.fetch("NL", "CP_MEUR") is None)
with_reply({}, 500)
check("HTTP error -> None", eg.fetch("AT", "CP_MEUR") is None)
with_reply({"junk": 1})
check("bad payload -> None", eg.fetch("AT", "CP_MEUR") is None)

with_reply(full)
lv = eg.fetch_levels("AT", "MEUR", "\u20acm")
check("levels both keys", set(lv) == {"gdp_level", "gdp_real"})
check("real label names CLV20", lv["gdp_real"]["label"] == "Real GDP, chain-linked volume, SA (Eurostat namq_10_gdp, CLV20_MEUR)")
check("nominal label names CP", lv["gdp_level"]["label"].endswith("(Eurostat namq_10_gdp, CP_MEUR)"))
check("unit + freq", lv["gdp_real"]["unit"] == "\u20acm" and lv["gdp_real"]["freq"] == "quarters")
with_reply({}, 500)
check("levels empty on failure", eg.fetch_levels("AT", "MEUR", "\u20acm") == {})

check("source_tag eurostat", eg.source_tag(lv["gdp_real"]) == "Eurostat namq_10_gdp, CLV20_MEUR")
check("source_tag FRED fallback", eg.source_tag({"label": "Real GDP, chain-linked volume, SA (CLVMNACSCAB1GQNL)"}) == "CLVMNACSCAB1GQNL")

# wiring in the three fetchers
for c, geo, cur in (("at", "AT", "MEUR"), ("dk", "DK", "MNAC"), ("nl", "NL", "MEUR")):
    s = open(os.path.join(ROOT, f"fetch_{c}.py"), encoding="utf-8").read()
    check(f"{c} imports module", "\nimport eurostat_gdp\n" in s)
    check(f"{c} calls fetch_levels", f'eurostat_gdp.fetch_levels("{geo}", "{cur}"' in s)
    check(f"{c} Eurostat before FRED", s.index("eurostat_gdp.fetch_levels(") < s.index('os.environ.get("FRED_API_KEY")'))
    check(f"{c} FRED skips Eurostat keys", re.search(r"FRED_SERIES\.items\(\):\n\s+if name in es_gdp:\n\s+continue", s) is not None)
    check(f"{c} growth label from source", "source_tag(out['series']['gdp_real'])" in s)
    check(f"{c} no hard-coded CLVM growth label", "derived from CLVMNACSCAB1GQ" not in s)
    check(f"{c} docstring CURRENT SOURCE", "CURRENT SOURCE (since v1.6.32)" in s[:3000])

print(f"{ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
