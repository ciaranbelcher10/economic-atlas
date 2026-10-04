#!/usr/bin/env python3
"""Compare OECD's own monthly unemployment rate with what the site serves for
South Korea, Israel and Turkey.

Why this exists. These three take the FRED copy of the OECD harmonised rate
(LRHUTTTT..M156S), which ends 2026-07 while OECD itself is believed to have
2026-08. Before switching to OECD direct (inside the oecd_turn rotation),
check that values agree where they overlap and how far ahead OECD runs.

Read-only: writes nothing, imported by nothing, never scheduled.
    python3 tools/probe_oecd_unemp.py
Needs outbound access to sdmx.oecd.org (not the sandbox).
"""
from __future__ import annotations

import csv, io, json, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)", "Accept": "text/csv"}
FLOW = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"
CASES = [("KOR", "data-kr.json"), ("ISR", "data-il.json"), ("TUR", "data-tr.json")]


def oecd(iso3):
    # REF_AREA.MEASURE.UNIT_MEASURE.TRANSFORMATION.ADJUSTMENT.SEX.AGE.ACTIVITY.FREQ
    url = f"{FLOW}{iso3}..._Z.Y._T.Y_GE15..M?startPeriod=2015&format=csvfilewithlabels"
    r = requests.get(url, timeout=90, headers=UA)
    print(f"  status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    keys = sorted({(row.get("MEASURE"), row.get("UNIT_MEASURE")) for row in rows})
    print(f"  MEASURE/UNIT variants: {keys}")
    pts = {}
    for row in rows:
        if row.get("MEASURE") == "UNE_LF_M" and row.get("OBS_VALUE"):
            pts[row["TIME_PERIOD"]] = float(row["OBS_VALUE"])
    return pts


def main():
    for iso3, fname in CASES:
        print(f"\n== {iso3} ==")
        s = json.loads((ROOT / fname).read_text(encoding="utf-8"))["series"]["unemployment"]
        site = dict(map(tuple, s["points"]))
        print(f"  site: {s['label']} | last {max(site)}")
        try:
            o = oecd(iso3)
        except Exception as e:  # noqa: BLE001
            print(f"  OECD FAILED: {e}")
            time.sleep(5)
            continue
        if not o:
            print("  OECD returned no UNE_LF_M rows")
            continue
        print(f"  oecd: {len(o)} pts, {min(o)} to {max(o)}")
        both = sorted(m for m in o if m in site)
        gaps = [abs(site[m] - o[m]) for m in both]
        print(f"  overlap n={len(both)} mean |gap|={sum(gaps)/len(gaps):.4f} max={max(gaps):.4f}")
        for m in both[-6:]:
            print(f"    {m}  site {site[m]:.3f}  oecd {o[m]:.3f}  {site[m]-o[m]:+.3f}")
        print(f"  OECD beyond site: {[(m, o[m]) for m in sorted(o) if m > max(site)]}")
        time.sleep(5)  # be gentle: OECD rate-limits


if __name__ == "__main__":
    main()
