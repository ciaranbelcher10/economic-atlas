#!/usr/bin/env python3
"""Compare ECB long-term interest rates (IRS dataset, convergence-criterion
10-year yields) with what the site shows for Poland, Italy and Spain.

Why this exists. Poland's monthly 10-yr (OECD via FRED) runs a month behind
ECB IRS. Italy and Spain show a QUARTERLY yield only because, when they were
built, nobody could confirm the monthly FRED copy was live. ECB IRS publishes
all three monthly. Before switching, check ECB matches the current figures
where they overlap and see how far ahead it runs.

Read-only: writes nothing, imported by nothing, never scheduled.
    python3 tools/probe_ecb_irs.py
Needs outbound access to data-api.ecb.europa.eu (not the sandbox).
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
CASES = [("PL", "PLN", "data-pl.json"), ("IT", "EUR", "data-it.json"), ("ES", "EUR", "data-es.json")]


def ecb(cc, cur):
    key = f"M.{cc}.L.L40.CI.0000.{cur}.N.Z"
    url = f"https://data-api.ecb.europa.eu/service/data/IRS/{key}?format=csvdata"
    r = requests.get(url, timeout=90, headers=UA)
    print(f"  IRS/{key} status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    if rows:
        extra = {k: rows[-1][k] for k in rows[-1] if k.upper() in ("TITLE", "TITLE_COMPL", "UNIT", "COMPILATION", "DECIMALS")}
        print(f"  metadata: {extra}")
    return {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in rows if row.get("OBS_VALUE")}


def main():
    for cc, cur, fname in CASES:
        print(f"\n== {cc} ==")
        site = json.loads((ROOT / fname).read_text(encoding="utf-8"))["series"]["bond_yield_10y"]
        pts = dict(map(tuple, site["points"]))
        print(f"  site: {site.get('label')} | freq={site.get('freq')} | {len(pts)} pts, last {max(pts)}")
        try:
            e = ecb(cc, cur)
        except Exception as ex:  # noqa: BLE001
            print(f"  ECB FAILED: {ex}")
            continue
        print(f"  ecb: {len(e)} pts, {min(e)} to {max(e)}")
        diffs = []
        if site.get("freq") == "quarters":
            for q, v in pts.items():
                y, n = q.split("-Q")
                ms = [f"{y}-{3*int(n)-2+i:02d}" for i in range(3)]
                if all(m in e for m in ms):
                    diffs.append((q, v, sum(e[m] for m in ms) / 3))
            print("  (quarterly site value vs mean of ECB's 3 months)")
        else:
            diffs = [(m, v, e[m]) for m, v in pts.items() if m in e]
        if not diffs:
            print("  no overlap")
            continue
        gaps = [abs(a - b) for _, a, b in diffs]
        print(f"  overlap n={len(gaps)} mean |gap|={sum(gaps)/len(gaps):.4f} max={max(gaps):.4f}")
        for p, a, b in diffs[-8:]:
            print(f"    {p}  site {a:.3f}  ecb {b:.3f}  {a-b:+.3f}")
        newer = sorted(m for m in e if m > max(pts)) if site.get("freq") != "quarters" else sorted(e)[-3:]
        print(f"  ECB beyond site / latest months: {[(m, e[m]) for m in newer]}")


if __name__ == "__main__":
    main()
