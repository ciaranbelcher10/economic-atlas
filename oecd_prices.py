"""OECD price INDEX fetching, for the countries whose CPI comes from the OECD.

Why this is a separate module rather than an edit to each fetch script.

Fourteen countries take their ``cpi`` from the OECD live prices system, and
each script carries its own copy of ``fetch_oecd_cpi``. No two of those copies
are byte-identical (they differ in areas, logging, fallbacks and retry
behaviour), so a bulk find-and-replace across them is exactly the kind of edit
that has gone wrong on this project before. Instead every script calls into
this one implementation, the same way the EU HICP countries call into
``inflation_sources``.

What it adds. ``fetch_oecd_cpi`` requests the 12-month rate directly
(UNIT_MEASURE ``PA``, TRANSFORMATION ``GY``) and only falls back to the index
(``IX`` / ``_Z``) if that fails -- and it stops as soon as it holds a usable
candidate, so in practice the index is never fetched at all. A month-on-month
rate cannot be derived from a 12-month rate, so the index has to be requested
on its own. That is all this module does.

What it deliberately does NOT do: it never touches, wraps or replaces the
existing ``cpi`` series. If this module fails for a country, that country keeps
exactly the ``cpi`` it has today and simply serves no ``cpi_mom``.
"""
from __future__ import annotations

import csv
import io
import time

import oecd_turn
from datetime import datetime, timezone

__all__ = ["fetch_cpi_index", "mom_points", "period_back_1", "rate_from_index",
           "build_mom_series", "MIN_POINTS", "MAX_AGE_DAYS"]

OECD_PRICES_BASE_COICOP2018 = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0"
)
OECD_PRICES_BASE = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
)

# A new key has no previous version for the shrinkage guard to compare
# against, so the freshness and length bars are enforced here instead.
MIN_POINTS = 24
MAX_AGE_DAYS = {"M": 370, "Q": 460}

# Pacing. The probe run showed that firing these back to back gets the whole
# job rate-limited, and that a 429 is indistinguishable from an absent series
# at the response level -- nine countries initially looked like they had no
# index at all when they were simply being throttled. Slow and correct beats
# fast and wrong: a wrongly-absent index would permanently deny a country its
# month-on-month rate.
REQUEST_PAUSE_S = 2.0
MAX_CONSECUTIVE_429 = 2


def period_age_days(period: str) -> float:
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


def period_back_1(period: str) -> str | None:
    """The period immediately before this one, monthly or quarterly."""
    try:
        if "-Q" in period:
            y, q = period.split("-Q")
            y, q = int(y), int(q)
            return f"{y - 1:04d}-Q4" if q == 1 else f"{y:04d}-Q{q - 1}"
        y, m = period.split("-")[:2]
        y, m = int(y), int(m)
        return f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"
    except Exception:
        return None


def rate_from_index(points: list) -> list:
    """One-period rates from index levels, matched by period.

    Matched by period and not by list position: a hole in the source would
    otherwise shift every later comparison by the size of the hole, silently.
    Periods with no immediate predecessor are dropped rather than compared
    against whatever happens to be next in the list.
    """
    by_period = {p[0]: p[1] for p in points}
    out = []
    for period, value in points:
        prev = period_back_1(period)
        base = by_period.get(prev) if prev else None
        if base:
            out.append([period, round((value / base - 1) * 100, 2)])
    return out


def _parse_groups(text: str, area: str) -> dict:
    """{(methodology, adjustment): {period: value}} for one CSV response."""
    groups: dict = {}
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception:
        return groups
    for row in rows:
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


def fetch_cpi_index(areas, freq: str, http_get=None, label: str = "") -> list | None:
    """The OECD all-items price INDEX for the first area that has one, or None.

    Every candidate across both dataflows is collected before choosing, rather
    than returning on the first that answers: a newly migrated dataflow can
    reply with a handful of recent points while the legacy one holds a decade
    of history, and answering first is not the same as being better. The
    longest series that is also fresh enough wins.

    Returns ``[[period, level], ...]`` sorted by period, or None. None always
    means "no index available", never "a shorter series will do".
    """
    # Outside this script's OECD hour, return None: the series is left
    # absent and the guard keeps the previous one. Checked before any
    # request is made, so a skipped hour costs the OECD nothing.
    try:
        oecd_turn.check()
    except oecd_turn.NotThisHour as skip:
        print(f"  [oecd-index] {label or areas} {skip}")
        return None
    if http_get is None:  # pragma: no cover - exercised in production only
        import requests
        http_get = requests.get

    max_age = MAX_AGE_DAYS.get(freq, 370)
    viable = []
    consecutive_429s = 0

    for area in areas:
        combos = [
            (OECD_PRICES_BASE_COICOP2018, "C2018", "N", "N"),
            (OECD_PRICES_BASE_COICOP2018, "C2018", "", ""),
            (OECD_PRICES_BASE, "C1999", "N", "N"),
            (OECD_PRICES_BASE, "C1999", "", ""),
        ]
        for base_url, base_tag, meth, adj in combos:
            if consecutive_429s >= MAX_CONSECUTIVE_429:
                print(f"  [oecd-index] {area} bailing out after "
                      f"{consecutive_429s} consecutive 429s, host is rate-limiting")
                break
            time.sleep(REQUEST_PAUSE_S)
            tag = f"{base_tag}.{area}.{meth or '*'}"
            url = (f"{base_url}/{area}.{freq}.{meth}.CPI.IX._T.{adj}._Z"
                   f"?format=csvfile&startPeriod=2000")
            try:
                resp = http_get(url, timeout=60,
                                headers={"User-Agent": "economic-atlas/1.0"})
            except Exception as exc:
                print(f"  [oecd-index] {tag} request failed: {exc}")
                continue
            status = getattr(resp, "status_code", 0)
            if status == 429:
                consecutive_429s += 1
                print(f"  [oecd-index] {tag} HTTP 429 (rate-limited, not absent)")
                continue
            consecutive_429s = 0
            if status != 200:
                print(f"  [oecd-index] {tag} HTTP {status}")
                continue
            for gkey, by_period in _parse_groups(getattr(resp, "text", "") or "", area).items():
                periods = sorted(by_period)
                if not periods:
                    continue
                pts = [[p, by_period[p]] for p in periods]
                age = period_age_days(periods[-1])
                print(f"  [oecd-index] {tag} {gkey} {len(pts)} points "
                      f"{periods[0]} to {periods[-1]} (age {age:.0f}d)")
                if age > max_age:
                    # The same trap that once served Japan 2021 data as
                    # current: a discontinued base-year series is complete,
                    # plausible and wrong.
                    print(f"  [oecd-index] {tag} rejected: last point is "
                          f"{age:.0f} days old, over the {max_age}-day bar")
                    continue
                viable.append((len(pts), periods[-1], pts))

    if not viable:
        print(f"  [oecd-index] {label or areas} no usable index found")
        return None
    viable.sort(key=lambda c: (c[0], c[1]))
    best = viable[-1]
    if best[0] < MIN_POINTS:
        print(f"  [oecd-index] {label or areas} best candidate has only "
              f"{best[0]} points, under the {MIN_POINTS} bar; leaving the key out")
        return None
    return best[2]


def build_mom_series(points: list, freq: str, source_note: str) -> dict | None:
    """The served cpi_mom (or cpi_qoq) series built from index levels.

    Australia's CPI is genuinely quarterly, so it gets a quarter-on-quarter
    rate; nobody quotes a quarter-on-quarter rate off a monthly index, and
    nothing here synthesises one.
    """
    if not points:
        return None
    rates = rate_from_index(points)
    if len(rates) < MIN_POINTS:
        print(f"  [oecd-index] only {len(rates)} derived points, "
              f"under the {MIN_POINTS} bar; leaving the key out")
        return None
    if freq == "Q":
        label = f"CPI, all items, quarter on quarter ({source_note})"
        unit_freq = "quarters"
    else:
        label = f"CPI, all items, month on month ({source_note})"
        unit_freq = "months"
    print(f"  ok  cpi_mom          {len(rates):>5} observations "
          f"({rates[0][0]} to {rates[-1][0]}, {unit_freq}, {source_note})")
    return {"label": label, "unit": "%", "freq": unit_freq, "points": rates}


def mom_points(areas, freq: str, http_get=None, label: str = "") -> list | None:
    """The one-period rate points for a country, or None. The whole job in one call.

    This is what the fetch scripts use: it fetches the index, derives the
    rate, and applies the length bar. None means the country keeps year on
    year only -- never a short or synthesised series. A failure here can
    never affect that country's existing cpi, which is fetched separately.
    """
    idx = fetch_cpi_index(areas, freq, http_get=http_get, label=label)
    if not idx:
        return None
    rates = rate_from_index(idx)
    if len(rates) < MIN_POINTS:
        print(f"  [oecd-index] {label or areas} only {len(rates)} derived points, "
              f"under the {MIN_POINTS} bar; leaving cpi_mom out")
        return None
    print(f"  [oecd-index] {label or areas} derived {len(rates)} points "
          f"({rates[0][0]} to {rates[-1][0]})")
    return rates
