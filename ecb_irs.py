"""Monthly 10-year government bond yield direct from the ECB (dataset IRS).

CURRENT SOURCE (since v1.6.42) for bond_yield_10y in Poland, Italy and Spain.
IRS is the long-term interest rate for convergence purposes: the 10-year
benchmark government bond yield, monthly average, compiled by the ECB for
every EU member. Probe of 4 Oct 2026 (tools/probe_ecb_irs.py):
  * Poland's FRED copy (IRLTLT01PLM156N) matched IRS to 0.0005pp on 307
    months but ran one month behind.
  * Italy and Spain showed only the quarterly FRED series (IRLT..Q156N),
    chosen at build time because the monthly copy could not be confirmed
    live. Each quarter equals the mean of IRS's three months (IT 0.0001pp,
    ES 0.003pp mean gap), so IRS adds monthly detail without changing level.

A reply is accepted only with at least MIN_POINTS months, so a truncated
response never replaces the history; the FRED entry stays as the fallback.
"""
from __future__ import annotations

import csv
import io

import requests

BASE = "https://data-api.ecb.europa.eu/service/data/IRS/"
MIN_POINTS = 120
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}


def key(cc: str, cur: str) -> str:
    return f"M.{cc}.L.L40.CI.0000.{cur}.N.Z"


def parse(text: str) -> list:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        p, v = (row.get("TIME_PERIOD") or "").strip(), (row.get("OBS_VALUE") or "").strip()
        if len(p) == 7 and p[4] == "-" and v:
            try:
                out.append([p, round(float(v), 3)])
            except ValueError:
                pass
    return sorted(out)


def fetch(cc: str, cur: str) -> dict:
    """{"bond_yield_10y": series} on success, {} otherwise."""
    k = key(cc, cur)
    tag = f"[ecb-irs] {cc}"
    try:
        r = requests.get(f"{BASE}{k}?format=csvdata", timeout=60, headers=UA)
        print(f"  {tag} status={r.status_code}")
        r.raise_for_status()
        pts = parse(r.text)
    except Exception as exc:
        print(f"  {tag} failed: {exc}")
        return {}
    if len(pts) < MIN_POINTS:
        print(f"  {tag} rejected: {len(pts)} points (need >= {MIN_POINTS})")
        return {}
    bad = [p for p in pts if not (-2 < p[1] < 40)]
    if bad:
        print(f"  {tag} rejected: implausible value {bad[0]}")
        return {}
    print(f"  {tag} ok: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return {"bond_yield_10y": {
        "label": f"10-year government bond yield, monthly average (ECB IRS {k})",
        "unit": "%", "freq": "months", "points": pts}}
