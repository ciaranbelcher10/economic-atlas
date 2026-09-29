"""IMF World Economic Outlook, fetched directly from the IMF (SDMX 3.0 at
api.imf.org), for general government debt and net lending/borrowing.

Why this exists: the site used to take these from FRED's copies of the WEO
(GGGDTA...A188N / GGNLBA...A188N). FRED stopped refreshing that whole
family after the April 2025 WEO ("Updated: Apr 29, 2025, Next Release
Date: Not Available" on every country page, checked Sep 2026), so eleven
countries froze a year or more behind while every call still succeeded.

Confirmed by a live probe run (Sep 2026): the dataflow IMF.RES/WEO answers
for all eleven countries, series dimensions COUNTRY / INDICATOR /
FREQUENCY, one TIME_PERIOD observation dimension whose values are NOT in
date order, and a COUNTRY_UPDATE_DATE series attribute ("9/26/2025").
It does not expose LATEST_ACTUAL_ANNUAL_DATA, so actuals are separated
from projections by the site's existing rule for IMF vintages: keep only
years strictly before the year of the country's update date. A WEO
updated in September 2025 therefore contributes years up to 2024, never
its 2025-2031 projections.

An edition whose update date is more than MAX_AGE_DAYS old is rejected
(returns None), so the fetch script carries the previous data over and the
freshness light turns amber rather than a dead feed passing silently.

Every value is a percentage of GDP, as published (SCALE 0).
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.RES/WEO/~/"
       "{iso3}.{indicator}.A?attributes=all&measures=all")
DEBT = "GGXWDG_NGDP"
DEFICIT = "GGXCNL_NGDP"
MAX_AGE_DAYS = 400
UA = {"User-Agent": "economic-atlas/0.1", "Accept": "application/json"}


def _update_date(text):
    """'9/26/2025' -> datetime, or None."""
    try:
        m, d, y = (int(x) for x in str(text).strip().split("/"))
        return datetime(y, m, d, tzinfo=timezone.utc)
    except Exception:
        return None


def parse(payload: dict, iso3: str, indicator: str, now: datetime | None = None):
    """Return (points, info) from one SDMX 3.0 JSON reply.

    points: [[year, value], ...] sorted, actual years only, or None.
    info:   dict with 'updated', 'kept_to', 'dropped' for the log.
    """
    now = now or datetime.now(timezone.utc)
    st = payload["data"]["structures"][0]
    sdims = st["dimensions"]["series"]
    tvals = [str(v.get("value") or v.get("id"))
             for v in st["dimensions"]["observation"][0]["values"]]
    sattr = st.get("attributes", {}).get("series", [])
    for key, s in payload["data"]["dataSets"][0].get("series", {}).items():
        idx = [int(i) for i in key.split(":")]
        ids = {sdims[n]["id"]: sdims[n]["values"][i].get("id")
               for n, i in enumerate(idx)}
        if ids.get("COUNTRY") != iso3 or ids.get("INDICATOR") != indicator:
            continue
        upd = None
        for n, v in enumerate(s.get("attributes") or []):
            if n < len(sattr) and sattr[n]["id"] == "COUNTRY_UPDATE_DATE" \
                    and isinstance(v, int):
                vals = sattr[n].get("values") or []
                if v < len(vals):
                    upd = _update_date(vals[v].get("value", vals[v].get("id")))
        if upd is None:
            return None, {"reason": "no COUNTRY_UPDATE_DATE"}
        if (now - upd).days > MAX_AGE_DAYS:
            return None, {"reason": f"edition updated {upd:%Y-%m-%d}, over "
                                    f"{MAX_AGE_DAYS} days old"}
        pts, dropped = [], 0
        for k, v in s.get("observations", {}).items():
            year = tvals[int(k)]
            try:
                val = float(v[0])
            except (TypeError, ValueError, IndexError):
                continue
            if int(year[:4]) >= upd.year:
                dropped += 1
                continue
            pts.append([year[:4], round(val, 3)])
        pts.sort(key=lambda p: p[0])
        return (pts or None), {"updated": f"{upd:%Y-%m-%d}",
                               "kept_to": pts[-1][0] if pts else None,
                               "dropped": dropped}
    return None, {"reason": "series not in reply"}


def fetch(iso3: str, indicator: str):
    """Fetch one country's indicator; returns points or None (logged)."""
    try:
        r = requests.get(URL.format(iso3=iso3, indicator=indicator),
                         timeout=90, headers=UA)
        print(f"  [imf-weo] {iso3} {indicator} status={r.status_code}")
        r.raise_for_status()
        pts, info = parse(r.json(), iso3, indicator)
    except Exception as exc:
        print(f"  [imf-weo] {iso3} {indicator} failed: {exc}")
        return None
    if pts is None:
        print(f"  [imf-weo] {iso3} {indicator} rejected: {info.get('reason')}")
    else:
        print(f"  [imf-weo] {iso3} {indicator} edition updated "
              f"{info['updated']}, kept years to {info['kept_to']}, "
              f"dropped {info['dropped']} projection year(s)")
    return pts
