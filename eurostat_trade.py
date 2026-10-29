"""Monthly total (world-partner) goods trade balance for one EU member state, from Eurostat (v1.9.25).

Dataset ext_st_27_2020msbec, partner WORLD, TRD_VAL, all BEC products, exports less imports, million euro, not
seasonally adjusted. The same query has run live for Croatia, Bulgaria, Lithuania, Portugal, Greece, Belgium and
Austria (each current to August 2026 in the repo on 29 October 2026). Germany, France, Italy, the Netherlands and
Spain used FRED's copy of OECD figures, which ran a month or more behind Eurostat.

balance(geo) returns [[period, value], ...] or None. On None the caller keeps whatever else it fetched, and
series_guard keeps a longer, more current previous series over a staler one.
"""
from __future__ import annotations

import requests

import eurostat_unemp

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
LABEL = "Trade balance, goods, total (Eurostat, world partner, derived EXP-IMP)"
UNIT = "\u20acm"


def flow(geo: str, stk_flow: str) -> list | None:
    url = (f"{BASE}/ext_st_27_2020msbec?format=JSON&lang=EN&geo={geo}&partner=WORLD&indic_et=TRD_VAL"
           f"&bclas_bec=TOTAL&stk_flow={stk_flow}&sinceTimePeriod=2002")
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-trade-world-{stk_flow}] {geo} status={r.status_code}")
        r.raise_for_status()
        return eurostat_unemp.parse(r.json()) or None
    except Exception as exc:
        print(f"  [eurostat-trade-world-{stk_flow}] {geo} failed: {exc}")
        return None


def balance(geo: str) -> list | None:
    """Exports less imports, matched by period. None if either flow is missing or nothing matches: a balance
    built from mismatched months would be wrong, not just incomplete."""
    exp, imp = flow(geo, "EXP"), flow(geo, "IMP")
    if not exp or not imp:
        return None
    imp_by = dict(imp)
    out = sorted([p, round(v - imp_by[p], 1)] for p, v in exp if p in imp_by)
    if not out:
        print(f"  [eurostat-trade-world] {geo}: exports and imports share no months")
        return None
    return out


def series(geo: str) -> dict | None:
    pts = balance(geo)
    if not pts:
        return None
    return {"label": LABEL, "unit": UNIT, "freq": "months", "points": pts}
