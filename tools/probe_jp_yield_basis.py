#!/usr/bin/env python3
"""Find out what Japan's monthly 10-year yield on the site actually measures.

Why this exists. Japan's bond_yield_10y comes from OECD (FRED copy
IRLTLT01JPM156N) and the citation says "monthly average". Spot checks found it
differs from the Ministry of Finance daily constant-maturity 10Y by 0.02-0.07pp
and matches neither the MoF monthly average nor the MoF month-end.

A clue in the data: from 2015 every value sits on a 0.005 grid (0.455, 2.345,
2.515 ...), the way single-day market quotes for the benchmark JGB issue are
quoted. Before 2015 most values are not. A monthly average of daily yields
almost never lands on that grid, so the citation is probably wrong for
recent years.

This script is read-only: it writes no file, is imported by nothing and is
never run on the schedule. It prints:
  1. every descriptive column OECD attaches to the Japan series (labels on),
  2. OECD dataflow annotations that mention Japan or long-term rates,
  3. how many values per year sit on the 0.005 grid,
  4. for each month since 2015, the site value against the MoF monthly
     average, MoF month-end, and the nearest single MoF day.

    python3 tools/probe_jp_yield_basis.py

Needs outbound access to sdmx.oecd.org and www.mof.go.jp (not the sandbox).
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("needs requests")

UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ROOT = Path(__file__).resolve().parent.parent
OECD = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK/"
        "JPN..IRLT......?format=csvfilewithlabels&startPeriod=2014")
FLOW = ("https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.STES/"
        "DSD_STES@DF_FINMARK/latest?references=none&detail=full")
MOF = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/"


def on_grid(v):
    return abs(round(v * 1000)) % 5 == 0


def site_points():
    d = json.loads((ROOT / "data-jp.json").read_text(encoding="utf-8"))
    return dict(map(tuple, d["series"]["bond_yield_10y"]["points"]))


def oecd_section():
    print("== 1. OECD columns for JPN IRLT (monthly) ==")
    try:
        r = requests.get(OECD, timeout=90, headers=dict(UA, Accept="text/csv"))
        print(f"status={r.status_code}")
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}")
        return {}
    rows = list(csv.DictReader(io.StringIO(r.text)))
    vals = {}
    distinct = defaultdict(set)
    for row in rows:
        if (row.get("FREQ") or "").strip() != "M":
            continue
        for k, v in row.items():
            if k not in ("TIME_PERIOD", "OBS_VALUE") and v:
                distinct[k].add(v.strip())
        try:
            vals[row["TIME_PERIOD"].strip()] = float(row["OBS_VALUE"])
        except (KeyError, ValueError):
            pass
    for k in sorted(distinct):
        print(f"  {k}: {' | '.join(sorted(distinct[k]))[:300]}")
    print(f"  monthly observations: {len(vals)}")
    return vals


def flow_section():
    print("\n== 2. Dataflow annotations mentioning Japan / long-term ==")
    try:
        r = requests.get(FLOW, timeout=90, headers=UA)
        print(f"status={r.status_code}")
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"FAILED: {e}")
        return
    text = re.sub(r"<[^>]+>", " ", r.text)
    text = re.sub(r"\s+", " ", text)
    hits = [m.start() for m in re.finditer(r"Japan|long-term|long term|benchmark|average|end of", text, re.I)]
    seen = set()
    for h in hits:
        snip = text[max(0, h - 200): h + 300]
        key = snip[:80]
        if key in seen:
            continue
        seen.add(key)
        print("  ..." + snip + "...")
        if len(seen) >= 12:
            break
    if not seen:
        print("  no matching annotation text")


def grid_section(site):
    print("\n== 3. Values on the 0.005 grid, by year (site data) ==")
    by = defaultdict(list)
    for p, v in site.items():
        by[p[:4]].append(v)
    for y in sorted(by):
        if y >= "2008":
            n = sum(on_grid(v) for v in by[y])
            print(f"  {y}: {n}/{len(by[y])}")


def mof_days():
    by = {}
    for url in (MOF + "historical/jgbcme_all.csv", MOF + "jgbcme.csv"):
        r = requests.get(url, timeout=120, headers=UA)
        r.raise_for_status()
        lines = r.content.decode("utf-8", "replace").splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("Date,"))
        for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
            d, v = (row.get("Date") or "").strip(), (row.get("10Y") or "").strip()
            m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", d)
            if m and v not in ("", "-"):
                by[f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"] = float(v)
    return by


def compare_section(site, oecd):
    print("\n== 4. Site value vs MoF daily 10Y (constant maturity) ==")
    try:
        days = mof_days()
    except Exception as e:  # noqa: BLE001
        print(f"MoF FAILED: {e}")
        return
    months = defaultdict(list)
    for d in sorted(days):
        months[d[:7]].append((d, days[d]))
    print("  month    site    oecd    mof_avg  mof_end  nearest_day(val, diff)")
    stats = defaultdict(list)
    for mth in sorted(site):
        if mth < "2015-01" or mth not in months:
            continue
        s = site[mth]
        obs = months[mth]
        avg = sum(v for _, v in obs) / len(obs)
        end = obs[-1][1]
        nd, nv = min(obs, key=lambda t: abs(t[1] - s))
        o = oecd.get(mth)
        stats["avg"].append(abs(s - avg))
        stats["end"].append(abs(s - end))
        stats["near"].append(abs(s - nv))
        if o is not None:
            stats["site_vs_oecd"].append(abs(s - o))
        print(f"  {mth}  {s:6.3f}  {'' if o is None else f'{o:6.3f}':>6}  {avg:7.3f}  {end:7.3f}  "
              f"{nd} {nv:.3f} {s - nv:+.3f}")
    print("\n  Summary (mean absolute gap, pp):")
    for k in ("site_vs_oecd", "avg", "end", "near"):
        xs = stats[k]
        if xs:
            print(f"    {k:13s} n={len(xs):3d}  mean={sum(xs)/len(xs):.4f}  max={max(xs):.4f}")
    print("  Reading: if 'near' is tiny but 'avg' and 'end' are not, the series is a "
          "single-day quote of a different instrument (likely the benchmark issue), "
          "not a monthly average of the MoF curve.")


def main():
    site = site_points()
    oecd = oecd_section()
    flow_section()
    grid_section(site)
    compare_section(site, oecd)


if __name__ == "__main__":
    main()
