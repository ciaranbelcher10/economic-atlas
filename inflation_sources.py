"""One definition of each inflation measure, shared by the EU country scripts.

Why this exists. Sweden and Poland each asked the OECD for "CPI" first and
used Eurostat's HICP only as a fallback. The OECD query sometimes failed,
sometimes answered with the national measure and, when its wildcard variant
ran, sometimes answered with HICP. The served `cpi` series therefore
switched measure between runs (Sweden's July reading alternated between
0.18%, national, and 0.27%, HICP), and once the shrinkage guard pinned the
longer HICP copy, nothing refreshed it, because the fallback only ran when the
OECD request failed.

The rule now:
  cpi           Eurostat HICP, all items, 12-month rate. EU members only.
                If it cannot be fetched, the key is left out and the guard
                carries the previous HICP forward. It is never replaced by a
                different measure under the same key.
  cpi_national  The national statistics office's own CPI, national
                methodology only, via the OECD prices database. A new key
                has no stored version for the shrinkage guard to compare, so
                this function applies its own freshness gate.
"""
from __future__ import annotations

import csv
import io
import re
import time
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    requests = None

OECD_BASES = (
    ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0", "C2018"),
    ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0", "C1999"),
)
NATIONAL_MAX_AGE_DAYS = 100   # a monthly series more than about three releases behind is not current
MIN_POINTS = 24

__all__ = ["hicp_label", "hicp_yoy", "fetch_hicp", "national_label", "fetch_national_cpi",
           "NATIONAL_MAX_AGE_DAYS"]


def _back_12(period: str) -> str | None:
    try:
        y, m = int(period[:4]), int(period[5:7])
    except (ValueError, IndexError):
        return None
    return f"{y - 1:04d}-{m:02d}"


def _age_days(period: str, today: datetime | None = None) -> float:
    today = today or datetime.now(timezone.utc)
    y, m = int(period[:4]), int(period[5:7])
    # end of the month the period covers
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    end = datetime(ny, nm, 1, tzinfo=timezone.utc)
    return (today - end).total_seconds() / 86400


def hicp_label(sid: str) -> str:
    return f"HICP, all items, YoY (Eurostat, {sid})"


def national_label() -> str:
    return "CPI, national definition, all items, YoY (OECD live prices system)"


def hicp_yoy(levels: list) -> list:
    """12-month rates from an index, matched by period so a gap never shifts the comparison."""
    by = {p[0]: p[1] for p in levels}
    out = []
    for per, val in levels:
        base = by.get(_back_12(per))
        if base:
            out.append([per, round((val / base - 1) * 100, 2)])
    return out


def fetch_hicp(fetch_fred, sid: str, key: str) -> dict | None:
    """The cpi series for an EU member, or None. Never substitutes another measure.

    The caller passes the literal FRED id (CP0000xxM086NEST) so the id stays
    greppable in each country script, where tools/citation_ids.py looks for it.
    """
    if not key:
        return None
    if not re.fullmatch(r"CP0000[A-Z0-9]{2,4}M086NEST", sid or ""):
        raise ValueError(f"not an all-items HICP id: {sid!r}")
    try:
        pts = hicp_yoy(fetch_fred(sid, "m", key))
    except Exception as exc:
        print(f"FAIL  cpi              HICP {sid}: {exc}; the stored cpi series will be carried forward unchanged")
        return None
    if len(pts) < MIN_POINTS:
        print(f"FAIL  cpi              HICP {sid}: only {len(pts)} points; the stored cpi series will be carried forward unchanged")
        return None
    print(f"  ok  cpi              {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, months, HICP {sid})")
    return {"label": hicp_label(sid), "unit": "%", "freq": "months", "points": pts}


def _parse_national(text: str, area: str) -> list:
    rows = list(csv.DictReader(io.StringIO(text)))
    pts = {}
    for row in rows:
        r = {k.upper(): (v or "") for k, v in row.items() if k}
        if r.get("REF_AREA", area) != area or r.get("METHODOLOGY") != "N":
            continue
        if r.get("ADJUSTMENT", "N") != "N":
            continue
        per, val = r.get("TIME_PERIOD", ""), r.get("OBS_VALUE", "")
        if len(per) == 7 and val:
            try:
                pts[per] = float(val)
            except ValueError:
                continue
    return sorted([[p, v] for p, v in pts.items()])


def fetch_national_cpi(area: str, get=None, today: datetime | None = None, pause: float = 0.4) -> dict | None:
    """National-methodology CPI 12-month rate, or None. Rejects any other methodology and any stale series."""
    get = get or (requests.get if requests else None)
    if get is None:
        return None
    best = None
    for base, tag in OECD_BASES:
        url = f"{base}/{area}.M.N.CPI.PA._T.N.GY?format=csvfile&startPeriod=2015"
        try:
            if pause:
                time.sleep(pause)
            r = get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
            r.raise_for_status()
            pts = _parse_national(r.text, area)
        except Exception as exc:
            print(f"  [cpi-national] {tag}.{area} request failed: {exc}")
            continue
        if not pts:
            print(f"  [cpi-national] {tag}.{area} no national-methodology rows")
            continue
        age = _age_days(pts[-1][0], today)
        if age > NATIONAL_MAX_AGE_DAYS:
            print(f"  [cpi-national] {tag}.{area} REJECTED stale: {len(pts)} points ending {pts[-1][0]}")
            continue
        if len(pts) < MIN_POINTS:
            print(f"  [cpi-national] {tag}.{area} REJECTED short: {len(pts)} points")
            continue
        if best is None or (pts[-1][0], len(pts)) > (best[-1][0], len(best)):
            best = pts
    if not best:
        print(f"FAIL  cpi_national     no current national-methodology series for {area}")
        return None
    print(f"  ok  cpi_national     {len(best):>5} observations ({best[0][0]} to {best[-1][0]}, months)")
    return {"label": national_label(), "unit": "%", "freq": "months", "points": best}
