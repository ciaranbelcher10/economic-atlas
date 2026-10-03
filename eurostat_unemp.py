"""Monthly unemployment rate direct from Eurostat (une_rt_m).

CURRENT SOURCE (since v1.6.34) for unemployment in Austria, Denmark,
France, Germany, Ireland, Italy, the Netherlands, Poland, Spain and Sweden.
Their FRED copies of the OECD harmonised rate (LRHUTTTT..M156S) ran a month
behind Eurostat, Italy's sat 0.2pp below Eurostat's revised figures, and
the Netherlands' was LRHUTTTTNLM156N, the NOT seasonally adjusted variant,
under an "SA" label (sweep of 3 Oct 2026). Same definition as before (ILO,
15-74, seasonally adjusted, % of labour force); the Eurozone page already
used this dataset.

A reply is accepted only with at least MIN_POINTS months, so a truncated
response never replaces the history; FRED stays as the fallback.
"""
from __future__ import annotations

import requests

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m"
MIN_POINTS = 120
UA = {"User-Agent": "economic-atlas/0.1"}
LABEL = "Unemployment rate, SA (Eurostat une_rt_m)"


def parse(payload: dict) -> list:
    idx = payload["dimension"]["time"]["category"]["index"]
    vals = payload.get("value", {})
    out = []
    for period, pos in idx.items():
        v = vals.get(str(pos)) if isinstance(vals, dict) else (vals[pos] if pos < len(vals) else None)
        if v is not None:
            out.append([period, float(v)])
    return sorted(out)


def fetch(geo: str) -> dict:
    """{"unemployment": series} on success, {} otherwise."""
    url = (f"{BASE}?format=JSON&lang=EN&geo={geo}&sex=T&age=TOTAL&unit=PC_ACT"
           f"&s_adj=SA&sinceTimePeriod=1983")
    tag = f"[eurostat-unemp] {geo}"
    try:
        r = requests.get(url, timeout=60, headers=UA)
        print(f"  {tag} status={r.status_code}")
        r.raise_for_status()
        pts = parse(r.json())
    except Exception as exc:
        print(f"  {tag} failed: {exc}")
        return {}
    if len(pts) < MIN_POINTS:
        print(f"  {tag} rejected: {len(pts)} points (need >= {MIN_POINTS})")
        return {}
    print(f"  {tag} ok: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return {"unemployment": {"label": LABEL, "unit": "%", "freq": "months", "points": pts}}
