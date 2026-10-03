"""Quarterly GDP levels direct from Eurostat (namq_10_gdp).

CURRENT SOURCE (since v1.6.32) for gdp_level and gdp_real in Austria,
Denmark and the Netherlands. Their FRED copies (CPMNACSCAB1GQ.. and
CLVMNACSCAB1GQ..) had stopped picking up Eurostat revisions: the audit of
2 Oct 2026 found Denmark Q2 2026 growth at 0.28% on the site against 0.89%
at Eurostat, Austria Q1 0.11% against 0.28%, Netherlands Q2 0.40% against
0.63%. Germany and Sweden's FRED copies were exact and stay on FRED.

Units: CP_MEUR / CP_MNAC (current prices, millions), CLV20_MEUR /
CLV20_MNAC (chain-linked volumes, reference year 2020). Seasonally and
calendar adjusted (SCA). If Eurostat rebases the CLV reference year the
CLV20 query returns nothing; the fetcher then falls back to FRED and logs
"[eurostat-gdp] ... rejected", which is the cue to update CLV_UNIT.

A reply is accepted only if it has at least MIN_POINTS quarters starting
no later than MAX_FIRST, so a truncated response can never replace the
full history (series_guard would keep the old series anyway, but this
makes the reason visible in the log).
"""
from __future__ import annotations

import json
import requests

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp"
CLV_UNIT = "CLV20"
MIN_POINTS = 100
MAX_FIRST = "1999-Q4"
UA = {"User-Agent": "economic-atlas/0.1"}


def parse(payload: dict) -> list:
    """JSON-stat 2.0 from Eurostat, one series -> [[period, value], ...]."""
    idx = payload["dimension"]["time"]["category"]["index"]
    vals = payload.get("value", {})
    out = []
    for period, pos in idx.items():
        v = vals.get(str(pos)) if isinstance(vals, dict) else (vals[pos] if pos < len(vals) else None)
        if v is not None:
            out.append([period, float(v)])
    return sorted(out)


def fetch(geo: str, unit: str) -> list | None:
    url = (f"{BASE}?format=JSON&lang=EN&geo={geo}&na_item=B1GQ&s_adj=SCA"
           f"&unit={unit}&sinceTimePeriod=1995")
    tag = f"[eurostat-gdp] {geo} {unit}"
    try:
        r = requests.get(url, timeout=60, headers=UA)
        print(f"  {tag} status={r.status_code}")
        r.raise_for_status()
        pts = parse(r.json())
    except Exception as exc:
        print(f"  {tag} failed: {exc}")
        return None
    if len(pts) < MIN_POINTS or pts[0][0] > MAX_FIRST:
        first = pts[0][0] if pts else None
        print(f"  {tag} rejected: {len(pts)} points from {first} "
              f"(need >= {MIN_POINTS} from <= {MAX_FIRST})")
        return None
    print(f"  {tag} ok: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return pts


def fetch_levels(geo: str, cur: str, unit_label: str) -> dict:
    """Return {"gdp_level": series, "gdp_real": series} for whatever succeeded.

    cur is "MEUR" or "MNAC"; unit_label is the site unit ("\u20acm", "DKKm").
    """
    out = {}
    spec = {
        "gdp_level": (f"CP_{cur}", "GDP nominal, current prices, SA"),
        "gdp_real": (f"{CLV_UNIT}_{cur}", "Real GDP, chain-linked volume, SA"),
    }
    for key, (unit, label) in spec.items():
        pts = fetch(geo, unit)
        if pts:
            out[key] = {"label": f"{label} (Eurostat namq_10_gdp, {unit})",
                        "unit": unit_label, "freq": "quarters", "points": pts}
    return out


def source_tag(series: dict) -> str:
    """Short source name for a derived series' label, from gdp_real's label."""
    label = series.get("label", "")
    if "Eurostat namq_10_gdp" in label:
        return label[label.index("Eurostat namq_10_gdp"):].rstrip(")")
    return label[label.rfind("(") + 1:].rstrip(")") if "(" in label else "real GDP"
