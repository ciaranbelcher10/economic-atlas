#!/usr/bin/env python3
"""Report which countries the OECD prices database can serve a price INDEX for.

Why this exists. Fourteen countries take their cpi series from the OECD live
prices system, which returns a 12-month rate (UNIT_MEASURE PA, TRANSFORMATION
GY). A month-on-month rate cannot be derived from a 12-month rate, so those
countries can only be offered MoM if the OECD also holds the index itself
(UNIT_MEASURE IX, TRANSFORMATION _Z).

fetch_oecd_cpi already lists the IX variant among its attempts, but it stops
trying as soon as a candidate with enough history is in hand, and the rate
variant is attempted first and nearly always answers. The IX attempt therefore
almost never runs, and its availability is unknown.

This script answers that question without touching the hourly pipeline: it is
read-only, writes no data file, is not imported by any fetch script, and is
never run on the schedule. Run it manually and read the table it prints.

    python3 tools/probe_oecd_ix.py            # every country below
    python3 tools/probe_oecd_ix.py BRA ZAF    # just these

Note for anyone running this in a sandbox: bash here cannot reach
sdmx.oecd.org. This has to run somewhere with outbound access to the OECD,
which in practice means a manually dispatched Actions run or a local machine.
"""
from __future__ import annotations

import csv
import io
import sys
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover - the probe is useless without it
    requests = None

# The countries whose cpi comes from the OECD prices system today, as served
# in data-XX.json. Australia is quarterly; the rest are monthly.
AREAS = {
    "AUS": ("Australia", "Q"),
    "BRA": ("Brazil", "M"),
    "CAN": ("Canada", "M"),
    "CHE": ("Switzerland", "M"),
    "CHL": ("Chile", "M"),
    "COL": ("Colombia", "M"),
    "IDN": ("Indonesia", "M"),
    "ISR": ("Israel", "M"),
    "IND": ("India", "M"),
    "KOR": ("South Korea", "M"),
    "MEX": ("Mexico", "M"),
    "NOR": ("Norway", "M"),
    "TUR": ("Turkey", "M"),
    "ZAF": ("South Africa", "M"),
}

BASES = (
    ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "C2018"),
    ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "C1999"),
)

MIN_POINTS = 24
# A monthly index more than about a year stale is a discontinued base series,
# not a current one -- the same trap that served Japan 2021 data as current.
MAX_AGE_DAYS = {"M": 370, "Q": 460}


def _age_days(period: str) -> float:
    try:
        if "-Q" in period:
            y, q = period.split("-Q")
            dt = datetime(int(y), int(q) * 3, 1, tzinfo=timezone.utc)
        else:
            y, m = period.split("-")[:2]
            dt = datetime(int(y), int(m), 1, tzinfo=timezone.utc)
    except Exception:
        return 0.0
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def _parse(text: str, area: str) -> dict:
    """Rows grouped by (METHODOLOGY, ADJUSTMENT), as fetch_oecd_cpi groups them."""
    groups: dict = {}
    for row in csv.DictReader(io.StringIO(text)):
        low = {k.upper(): (v or "") for k, v in row.items() if k}
        if low.get("REF_AREA", area) != area:
            continue
        period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
        if not (period and value):
            continue
        gkey = (low.get("METHODOLOGY", "?"), low.get("ADJUSTMENT", "?"))
        try:
            groups.setdefault(gkey, {})[period] = float(value)
        except ValueError:
            continue
    return groups


def probe(area: str, freq: str, get=None, pause: float = 0.5) -> dict:
    get = get or (requests.get if requests else None)
    if get is None:
        return {"area": area, "verdict": "NO REQUESTS MODULE"}
    best = None
    for base, tag in BASES:
        for meth, adj in (("N", "N"), ("", "")):
            url = f"{base}/{area}.{freq}.{meth}.CPI.IX._T.{adj}._Z?format=csvfile&startPeriod=2000"
            try:
                if pause:
                    time.sleep(pause)
                r = get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
                if r.status_code != 200:
                    print(f"  [probe-ix] {tag}.{area} meth={meth or '*'} HTTP {r.status_code}")
                    continue
                groups = _parse(r.text, area)
            except Exception as exc:
                print(f"  [probe-ix] {tag}.{area} meth={meth or '*'} request failed: {exc}")
                continue
            for gkey, pts in groups.items():
                periods = sorted(pts)
                if not periods:
                    continue
                cand = {
                    "base": tag, "methodology": gkey[0], "adjustment": gkey[1],
                    "points": len(periods), "first": periods[0], "last": periods[-1],
                    "age_days": round(_age_days(periods[-1])),
                }
                print(f"  [probe-ix] {tag}.{area} {gkey} {cand['points']} points "
                      f"{cand['first']} to {cand['last']} (age {cand['age_days']}d)")
                if best is None or (cand["last"], cand["points"]) > (best["last"], best["points"]):
                    best = cand
    if best is None:
        return {"area": area, "verdict": "NO INDEX"}
    if best["points"] < MIN_POINTS:
        return {"area": area, "verdict": "TOO SHORT", **best}
    if best["age_days"] > MAX_AGE_DAYS[freq]:
        return {"area": area, "verdict": "STALE", **best}
    return {"area": area, "verdict": "AVAILABLE", **best}


def main(argv: list[str]) -> int:
    wanted = [a.upper() for a in argv[1:]] or list(AREAS)
    unknown = [a for a in wanted if a not in AREAS]
    if unknown:
        print(f"unknown area(s): {', '.join(unknown)}")
        return 2
    results = []
    for area in wanted:
        name, freq = AREAS[area]
        print(f"== {name} ({area}, {freq}) ==")
        results.append((name, probe(area, freq)))

    print()
    print(f"{'country':<16} {'verdict':<10} {'base':<6} {'meth':<5} {'adj':<5} "
          f"{'points':>6}  span")
    for name, r in results:
        print(f"{name:<16} {r['verdict']:<10} {r.get('base', ''):<6} "
              f"{r.get('methodology', ''):<5} {r.get('adjustment', ''):<5} "
              f"{r.get('points', ''):>6}  {r.get('first', '')} to {r.get('last', '')}")
    available = sum(1 for _, r in results if r["verdict"] == "AVAILABLE")
    print(f"\nAVAILABLE {available} / {len(results)}. "
          f"Only an AVAILABLE country can be offered a month on month rate; "
          f"the rest keep year on year only and say so on the page.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
