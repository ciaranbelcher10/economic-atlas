"""Keep IMF outlook projections off the site.

IMF Regional Economic Outlook series mirrored on FRED (ids ending PPPT,
GDPPT, BP6PT, GGXWDGGDP, GGXCNLGDP) carry actuals and projections in one series with no
flag between them. FRED's own note on these series says observations for the
current and future years are projections, where "current" means the year the
vintage was compiled, not the year the pipeline happens to run.

The scripts used to trim by today's year only. Singapore's CPI vintage
(SGPPCPIPCPPPT, last updated 22 January 2026) therefore still served its 2025
figure, 1.19%, which was a projection; Singapore's statistics office published
0.9% for 2025.

Rule: a vintage last updated before April of year Y+1 cannot hold an outturn
for year Y, so the last year kept is last_updated.year - 1 from April onwards
and last_updated.year - 2 before April. If the vintage date cannot be read,
the rule fails closed on today's date with the stricter of the two offsets.

The same cutoff is applied to the previously stored series before the
shrinkage guard compares them, otherwise the guard would reject the shorter,
correct series and keep the stored projection.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # the pure functions below are testable without it
    requests = None

OUTLOOK_ID = re.compile(r"(PPPT|GDPPT|BP6PT|GGXWDGGDP|GGXCNLGDP)$")
META_URL = ("https://api.stlouisfed.org/fred/series"
            "?series_id={sid}&api_key={key}&file_type=json")

# sid -> last year kept, recorded this run
CUTOFFS: dict[str, int] = {}

__all__ = ["is_outlook_series", "last_actual_year", "trim", "trim_previous", "CUTOFFS"]


def is_outlook_series(sid: str) -> bool:
    return bool(sid) and bool(OUTLOOK_ID.search(sid))


def last_actual_year(last_updated: str | None, today: datetime | None = None) -> int:
    """Last calendar year a vintage with this last_updated stamp can hold as an outturn."""
    today = today or datetime.now(timezone.utc)
    stamp = None
    if last_updated:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", last_updated)
        if m:
            stamp = (int(m.group(1)), int(m.group(2)))
    if stamp is None:
        return today.year - 2
    year, month = stamp
    return year - 1 if month >= 4 else year - 2


def _fetch_last_updated(sid: str, key: str) -> str | None:
    if not key or requests is None:
        return None
    try:
        r = requests.get(META_URL.format(sid=sid, key=key), timeout=30,
                         headers={"User-Agent": "economic-atlas/0.1"})
        r.raise_for_status()
        seriess = r.json().get("seriess") or []
        return seriess[0].get("last_updated") if seriess else None
    except Exception as exc:
        print(f"  [projection-guard] {sid} vintage date unavailable ({exc}); keeping years up to today minus two")
        return None


def trim(points: list, sid: str, key: str, fetch=_fetch_last_updated) -> list:
    """Drop projection years from an annual IMF outlook series. Other ids pass through."""
    if not is_outlook_series(sid) or not points:
        return points
    stamp = fetch(sid, key)
    cutoff = last_actual_year(stamp)
    CUTOFFS[sid] = cutoff
    kept = [p for p in points if str(p[0])[:4].isdigit() and int(str(p[0])[:4]) <= cutoff]
    dropped = len(points) - len(kept)
    if dropped:
        print(f"  [projection-guard] {sid}: vintage {stamp or 'unknown'}, "
              f"kept years to {cutoff}, dropped {dropped} projection year(s)")
    return kept


def trim_previous(prev_series: dict) -> None:
    """Apply this run's cutoffs to the stored series, in place, before the guard runs.

    A stored series is matched by the FRED id in its label. A stored series
    whose label names an IMF Regional Economic Outlook but no id takes the
    strictest cutoff recorded this run, which errs towards dropping.
    """
    if not CUTOFFS or not prev_series:
        return
    strictest = min(CUTOFFS.values())
    for key, s in prev_series.items():
        if not isinstance(s, dict) or s.get("freq") != "years":
            continue
        label = s.get("label", "")
        cutoff = None
        for sid, c in CUTOFFS.items():
            if sid in label:
                cutoff = c
                break
        if cutoff is None and "REO" in label:
            cutoff = strictest
        if cutoff is None:
            continue
        pts = s.get("points") or []
        s["points"] = [p for p in pts if str(p[0])[:4].isdigit() and int(str(p[0])[:4]) <= cutoff]
