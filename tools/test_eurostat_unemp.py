#!/usr/bin/env python3
"""Offline tests for eurostat_unemp.py and its wiring (v1.6.34).
    python3 tools/test_eurostat_unemp.py     # "N ok, 0 failed"
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import eurostat_unemp as eu
ok = fail = 0
def check(n, c):
    global ok, fail
    if c: ok += 1
    else: fail += 1; print("FAIL", n)
class R:
    def __init__(s, js, code=200): s.js, s.status_code = js, code
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError(s.status_code)
    def json(s): return s.js
def reply(n, code=200):
    ps = [f"{1983 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]
    js = {"dimension": {"time": {"category": {"index": {p: i for i, p in enumerate(ps)}}}}, "value": {str(i): 5.0 + i / 100 for i in range(n)}}
    calls = []
    def get(url, **kw): calls.append(url); return R(js, code)
    eu.requests.get = get
    return calls
calls = reply(500)
r = eu.fetch("NL")
check("full reply accepted", "unemployment" in r and len(r["unemployment"]["points"]) == 500)
check("query SA, PC_ACT, TOTAL, T", all(x in calls[0] for x in ("geo=NL", "s_adj=SA", "unit=PC_ACT", "age=TOTAL", "sex=T")))
check("label names une_rt_m", r["unemployment"]["label"] == "Unemployment rate, SA (Eurostat une_rt_m)")
reply(60); check("short reply rejected", eu.fetch("NL") == {})
reply(500, 500); check("HTTP error -> {}", eu.fetch("NL") == {})
GEO = {"at": "AT", "de": "DE", "dk": "DK", "es": "ES", "fr": "FR", "ie": "IE", "it": "IT", "nl": "NL", "pl": "PL", "se": "SE"}
for c, g in GEO.items():
    s = open(os.path.join(ROOT, f"fetch_{c}.py"), encoding="utf-8").read()
    check(f"{c} calls fetch({g})", f'eurostat_unemp.fetch("{g}")' in s)
    check(f"{c} Eurostat before FRED", s.index("eurostat_unemp.fetch(") < s.index('os.environ.get("FRED_API_KEY")'))
    # Since v1.6.42, PL/IT/ES skip a combined `direct` mapping (unemployment
    # plus the ECB yield); it must still contain es_unemp.
    check(f"{c} FRED skips es_unemp", re.search(r"FRED_SERIES\.items\(\):\n\s+if [^\n]*name in es_unemp:\n\s+continue", s) is not None
          or (re.search(r"FRED_SERIES\.items\(\):\n\s+if [^\n]*name in direct:\n\s+continue", s) is not None
              and re.search(r"direct = \{\*\*es_unemp,", s) is not None))
    check(f"{c} allow_shrink unemployment", '"unemployment": "v1.6.34' in s)
s = open(os.path.join(ROOT, "fetch_ez.py"), encoding="utf-8").read()
check("ez GDP EA21 via eurostat_gdp", 'eurostat_gdp.fetch_levels("EA21", "MEUR"' in s)
check("ez gov EA21 first", 'for area in ("EA21", "EA20", "EA19"):\n        url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1' in s)
check("ez FRED skips Eurostat GDP", re.search(r"FRED_SERIES\.items\(\):\n\s+if name in es_gdp:\n\s+continue", s) is not None)
check("ez HICP from prc_hicp_minr EA21", "prc_hicp_minr?format=JSON&lang=EN" in s and "&geo=EA21&coicop18=TOTAL" in s)
check("ez HICP annual + monthly published rates", '"cpi", "RCH_A"' in s and '"cpi_mom", "RCH_M"' in s)
check("ez FRED skips HICP when Eurostat ok", "es_gdp = dict(es_gdp, **{name: out[\"series\"][name]})" in s)
print(f"{ok} ok, {fail} failed")
sys.exit(1 if fail else 0)
