"""Monthly unemployment rate direct from the OECD (DF_IALFS_UNE_M).

CURRENT SOURCE (since v1.6.43) for unemployment in South Korea, Israel and
Turkey. Their FRED copies (LRHUTTTT..M156S) ran one month behind OECD.
Probe of 4 Oct 2026 (tools/probe_oecd_unemp.py): Korea identical on 139
months, Turkey 0.002pp mean gap, Israel 0.0015pp (OECD carries later
revisions); OECD had 2026-08 for all three.

Measure UNE_LF_M (% of labour force), sex _T, age Y_GE15, seasonally
adjusted, monthly. Same definition as the FRED copy.

Runs only in the script's oecd_turn hour: fetch() raises
oecd_turn.NotThisHour otherwise, and the caller then leaves the key out so
series_guard carries the previous series over. Returns {} on any other
failure, so the caller can fall back to FRED. A reply is accepted only with
at least MIN_POINTS months.
"""
from __future__ import annotations

import csv
import io
import re

import requests

import oecd_turn

FLOW = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"
MIN_POINTS = 120
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)", "Accept": "text/csv"}


def url(iso3: str) -> str:
    # REF_AREA.MEASURE.UNIT_MEASURE.TRANSFORMATION.ADJUSTMENT.SEX.AGE.ACTIVITY.FREQ
    return f"{FLOW}{iso3}.UNE_LF_M.._Z.Y._T.Y_GE15..M?format=csvfile"


def parse(text: str) -> list:
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("MEASURE") or "UNE_LF_M") != "UNE_LF_M":
            continue
        p, v = (row.get("TIME_PERIOD") or "").strip(), (row.get("OBS_VALUE") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}", p) and v:
            try:
                out[p] = round(float(v), 3)
            except ValueError:
                pass
    return sorted([p, v] for p, v in out.items())


def fetch(iso3: str) -> dict:
    """{"unemployment": series} on success, {} on failure; NotThisHour off-turn."""
    oecd_turn.check()
    tag = f"[oecd-unemp] {iso3}"
    try:
        r = requests.get(url(iso3), timeout=60, headers=UA)
        print(f"  {tag} status={r.status_code}")
        r.raise_for_status()
        pts = parse(r.text)
    except Exception as exc:
        print(f"  {tag} failed: {exc}")
        return {}
    if len(pts) < MIN_POINTS:
        print(f"  {tag} rejected: {len(pts)} points (need >= {MIN_POINTS})")
        return {}
    bad = [p for p in pts if not (0 <= p[1] < 60)]
    if bad:
        print(f"  {tag} rejected: implausible value {bad[0]}")
        return {}
    print(f"  {tag} ok: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return {"unemployment": {
        "label": f"Unemployment rate, 15+, SA (OECD DF_IALFS_UNE_M {iso3}.UNE_LF_M)",
        "unit": "%", "freq": "months", "points": pts}}
