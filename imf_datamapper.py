"""Annual IMF World Economic Outlook figures from the IMF DataMapper API (v1.9.27).

Chile and Colombia's deficit and Morocco's debt came only from FRED's copies of IMF Regional Economic Outlook
series, which FRED refreshes months after the IMF. The DataMapper serves the current World Economic Outlook
directly, so it is asked first and the FRED copy stays as the fallback.

The DataMapper carries actuals and projections in one series with no flag between them. The WEO is published
in April and October, so from May the current edition can hold an outturn for last year; before May only for
the year before that. Later years are projections and are dropped.

Before the DataMapper series replaces a FRED copy, the two must agree on the years both cover (largest gap at
most TOLERANCE percentage points). A larger gap means a different definition or a bad response, and the FRED
copy is kept.

overlay(series, key, indicator, iso3, label) changes series[key] in place and returns a one-line note.
"""
from __future__ import annotations

from datetime import date

try:
    import requests
except ImportError:  # the pure functions below are testable without it
    requests = None

URL = "https://www.imf.org/external/datamapper/api/v1/{indicator}/{iso3}"
TOLERANCE = 1.5

__all__ = ["last_actual_year", "parse", "max_gap", "overlay", "TOLERANCE"]


def last_actual_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year - 1 if today.month >= 5 else today.year - 2


def parse(payload: dict, indicator: str, iso3: str, today: date | None = None) -> list:
    """[[year, value], ...] up to the last actual year, sorted; [] if the payload has nothing usable."""
    cut = last_actual_year(today)
    vals = ((payload or {}).get("values") or {}).get(indicator, {}).get(iso3) or {}
    out = []
    for y, v in vals.items():
        if str(y).isdigit() and len(str(y)) == 4 and int(y) <= cut and isinstance(v, (int, float)):
            out.append([str(y), round(float(v), 3)])
    return sorted(out)


def max_gap(a: list, b: list) -> tuple[float | None, int]:
    """Largest absolute difference over shared years, and how many years are shared."""
    bm = dict(b)
    shared = [(v, bm[p]) for p, v in a if p in bm]
    if not shared:
        return None, 0
    return max(abs(x - y) for x, y in shared), len(shared)


def fetch(indicator: str, iso3: str, today: date | None = None) -> list | None:
    if requests is None:
        return None
    try:
        r = requests.get(URL.format(indicator=indicator, iso3=iso3), timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [imf-datamapper] {indicator} {iso3} status={r.status_code}")
        r.raise_for_status()
        return parse(r.json(), indicator, iso3, today) or None
    except Exception as exc:
        print(f"  [imf-datamapper] {indicator} {iso3} failed: {exc}")
        return None


def overlay(series: dict, key: str, indicator: str, iso3: str, label: str, fetcher=fetch, today: date | None = None) -> str:
    pts = fetcher(indicator, iso3, today)
    if not pts:
        return f"{key}: DataMapper unavailable, FRED copy kept"
    old = (series.get(key) or {}).get("points") or []
    if old:
        gap, n = max_gap(pts, old)
        if gap is None:
            return f"{key}: DataMapper shares no years with the FRED copy, FRED copy kept"
        if gap > TOLERANCE:
            return f"{key}: DataMapper differs from the FRED copy by {gap:.2f} points over {n} years, FRED copy kept"
        if pts[-1][0] < old[-1][0]:
            return f"{key}: DataMapper ends {pts[-1][0]}, before the FRED copy ({old[-1][0]}), FRED copy kept"
    series[key] = {"label": label, "unit": "%", "freq": "years", "points": pts}
    return f"{key}: IMF DataMapper applied, {pts[0][0]} to {pts[-1][0]}" + (f", largest gap from FRED copy {gap:.2f} points" if old else "")
