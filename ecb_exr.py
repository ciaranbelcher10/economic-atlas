"""Monthly ECB euro reference rates (dataset EXR), national currency per euro.

Added v1.7.33 for Czechia. Eurostat publishes member states' goods trade
in euro only (ext_st_27_2020msbec). A Czech page shows koruna, and the
Dollarise toggle divides every currency figure by koruna per US$, so trade
left in euro would be dollarised wrongly. Each month's euro figure is
converted at that month's average ECB reference rate (EXR
M.CZK.EUR.SP00.A), the rate the ECB publishes daily for every EU currency.

A month without a published rate gives no converted point; nothing is
carried across or invented. A reply is accepted only with at least
MIN_POINTS months, so a truncated response never converts the history at
a partial set of rates.
"""
from __future__ import annotations

import csv
import io

import requests

BASE = "https://data-api.ecb.europa.eu/service/data/EXR/"
MIN_POINTS = 120
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}


def key(cur: str) -> str:
    return f"M.{cur}.EUR.SP00.A"


def parse(text: str) -> dict:
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        p, v = (row.get("TIME_PERIOD") or "").strip(), (row.get("OBS_VALUE") or "").strip()
        if len(p) == 7 and p[4] == "-" and v:
            try:
                out[p] = float(v)
            except ValueError:
                pass
    return out


def fetch_monthly(cur: str, get=None) -> dict:
    """{YYYY-MM: units of `cur` per euro, monthly average}, or {} on failure."""
    get = get or requests.get
    k = key(cur)
    tag = f"[ecb-exr] {cur}"
    try:
        r = get(f"{BASE}{k}?format=csvdata", timeout=60, headers=UA)
        print(f"  {tag} status={r.status_code}")
        r.raise_for_status()
        rates = parse(r.text)
    except Exception as exc:
        print(f"  {tag} failed: {exc}")
        return {}
    if len(rates) < MIN_POINTS:
        print(f"  {tag} rejected: {len(rates)} months (need >= {MIN_POINTS})")
        return {}
    bad = [(p, v) for p, v in rates.items() if not v > 0]
    if bad:
        print(f"  {tag} rejected: non-positive rate {bad[0]}")
        return {}
    first, last = min(rates), max(rates)
    print(f"  {tag} ok: {len(rates)} months, {first} to {last} ({rates[last]} {cur} per euro)")
    return rates


def to_national(points: list, rates: dict, dp: int = 1) -> list:
    """Convert [[YYYY-MM, euro value], ...] at each month's own rate.
    Months with no rate are dropped, never filled."""
    return [[p, round(v * rates[p], dp)] for p, v in points if p in rates]
