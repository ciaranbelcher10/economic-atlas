"""
Shared guard against a series silently getting worse between runs.

Background
----------
Every fetch script writes its country's series to data-XX.json each hour.
Before this module existed, the only protection was a carry-over that fired
when a series key was ABSENT from the new run:

    if k not in out["series"]:
        out["series"][k] = previous[k]

That protects against a fetch failing outright. It does nothing when a fetch
SUCCEEDS but returns less than it did last time, because the key is present.
A 7-point CPI would then overwrite a 139-point CPI and nothing noticed.

That is not hypothetical. Poland's CPI oscillated between 7, 127, 132 and 139
points across 28 recorded states; Chile's flipped between 140 monthly points
and 55 annual ones; Brazil's dropped 139 to 127 on 2026-09-13. The underlying
cause is OECD rate-limiting: which dataflow variants answer in a given run
varies, so the winning candidate varies with it.

What counts as "worse"
----------------------
Three axes, checked against the previously committed series:

1. Frequency downgrade      months -> years, quarters -> years, etc.
2. Same frequency, less coverage    start date moved forward, or fewer points
3. Frequency upgrade that loses recency    finer detail but older last period

A frequency UPGRADE that moves the start date forward is an improvement, not
a loss, so it is allowed. That is what lets Mexico's annual 1960-2025 series
(66 points) be replaced by monthly 2015-2026 (140 points).

Exemptions
----------
* The previous series was already stale. A dead series can be replaced by
  anything. This is what distinguishes a genuine source swap (Eurozone trade
  was 400 points ending 2023-04, replaced by 12 points ending 2026-05) from
  silent truncation (Poland's CPI was current in both states).

* An explicit per-series entry in the caller's allow_shrink mapping. Use this
  when deliberately swapping a live series for a shorter better one, as with
  US PPI moving from PPIACO (all commodities, 668 points from 1971) to PPIFID
  (final demand, 190 points from 2010, the BLS headline measure). Put the
  reason in the value so the next reader knows why.

Grafting
--------
When the incoming series is shorter but carries periods the previous one
lacks, the new periods are appended to the previous series rather than the
whole thing being discarded. That surfaces this month's figure immediately
without throwing away history.

Grafting only happens when frequency AND label both match, because splicing a
point from a different measure onto a series leaves a seam that is invisible
on screen and wrong.

This module deliberately checks SHAPE only. A series with the right shape and
wrong values passes every check here.
"""

from datetime import date, datetime, timezone

__all__ = ["merge_series", "apply_guard", "describe_verdict"]

# Higher is finer grained.
_FREQ_RANK = {
    "years": 1, "year": 1, "annual": 1, "a": 1,
    "quarters": 2, "quarter": 2, "quarterly": 2, "q": 2,
    "months": 3, "month": 3, "monthly": 3, "m": 3,
}

# How old the previous series' last period must be before we treat it as dead
# and let anything replace it. Deliberately generous: the job of these numbers
# is to catch genuinely abandoned series (years stale), not to second-guess a
# provider running a few weeks late.
_STALE_DAYS = {1: 1000, 2: 550, 3: 400}
_STALE_DEFAULT = 550


def _rank(freq):
    if not freq:
        return 0
    return _FREQ_RANK.get(str(freq).strip().lower(), 0)


def _period_end(period):
    """End date of a period label, so periods of different frequencies compare.

    "2026"    -> 2026-12-31
    "2026-Q2" -> 2026-06-30
    "2026-08" -> 2026-08-31
    Returns None if unparseable.
    """
    if period is None:
        return None
    s = str(period).strip()
    try:
        if len(s) == 4 and s.isdigit():
            return date(int(s), 12, 31)
        if "-Q" in s.upper():
            y, q = s.upper().split("-Q")
            m = min(4, max(1, int(q))) * 3
            return _month_end(int(y), m)
        if "-" in s:
            parts = s.split("-")
            y, m = int(parts[0]), int(parts[1])
            if 1 <= m <= 12:
                return _month_end(y, m)
    except Exception:
        return None
    return None


def _month_end(y, m):
    if m == 12:
        return date(y, 12, 31)
    nxt = date(y, m + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def _age_days(period):
    end = _period_end(period)
    if end is None:
        return None
    return (datetime.now(timezone.utc).date() - end).days


def _shape(series):
    """(n, first, last, freq, label) from a series dict, or None."""
    if not isinstance(series, dict):
        return None
    pts = series.get("points")
    if not isinstance(pts, list) or not pts:
        return None
    try:
        first = pts[0][0]
        last = pts[-1][0]
    except Exception:
        return None
    return (len(pts), first, last, series.get("freq"), series.get("label"))


def _is_stale(shape):
    n, first, last, freq, label = shape
    age = _age_days(last)
    if age is None:
        return False
    return age > _STALE_DAYS.get(_rank(freq), _STALE_DEFAULT)


def merge_series(key, new, prev, allow_shrink=None):
    """Decide what to store for one series.

    Returns (chosen_series, verdict, detail) where verdict is one of:
      "new"        incoming accepted as is
      "grafted"    previous kept, newer points from incoming appended
      "kept"       previous kept, incoming rejected as a downgrade
      "new-stale"  incoming accepted because previous was dead
      "new-allowed" incoming accepted via allow_shrink
    """
    allow_shrink = allow_shrink or {}
    ns, ps = _shape(new), _shape(prev)

    if ns is None:
        return (prev, "kept", "incoming empty or unparseable") if ps else (new, "new", "no usable previous")
    if ps is None:
        return new, "new", "no usable previous"

    n_new, first_new, last_new, freq_new, label_new = ns
    n_prev, first_prev, last_prev, freq_prev, label_prev = ps

    r_new, r_prev = _rank(freq_new), _rank(freq_prev)
    end_new, end_prev = _period_end(last_new), _period_end(last_prev)

    worse = []
    if r_new and r_prev and r_new < r_prev:
        worse.append(f"frequency {freq_prev} -> {freq_new}")
    elif r_new == r_prev:
        if _period_end(first_new) and _period_end(first_prev) \
           and _period_end(first_new) > _period_end(first_prev):
            worse.append(f"start {first_prev} -> {first_new}")
        if n_new < n_prev:
            worse.append(f"points {n_prev} -> {n_new}")
    elif r_new and r_prev and r_new > r_prev:
        if end_new and end_prev and end_new < end_prev:
            worse.append(f"finer frequency but last period {last_prev} -> {last_new}")

    if not worse:
        return new, "new", f"{n_prev} -> {n_new} points, no downgrade"

    if key in allow_shrink:
        return new, "new-allowed", f"{'; '.join(worse)} (allowed: {allow_shrink[key]})"

    if _is_stale(ps):
        return new, "new-stale", (
            f"{'; '.join(worse)} but previous ended {last_prev}, "
            f"{_age_days(last_prev)} days old")

    # Downgrade against a live previous series. Keep the old one, but take any
    # genuinely newer points if they are the same measure at the same cadence.
    if end_new and end_prev and end_new > end_prev \
       and freq_new == freq_prev and label_new == label_prev:
        graft = [p for p in new["points"] if (_period_end(p[0]) or date.min) > end_prev]
        if graft:
            merged = dict(prev)
            merged["points"] = list(prev["points"]) + list(graft)
            return merged, "grafted", (
                f"{'; '.join(worse)}; kept {n_prev} points and appended "
                f"{len(graft)} newer ({graft[0][0]} to {graft[-1][0]})")

    return prev, "kept", f"{'; '.join(worse)}; previous last period {last_prev}"


def apply_guard(out_series, prev_series, allow_shrink=None, log=print):
    """Run merge_series across every series, in place on out_series.

    Also performs the absence carry-over the scripts used to do inline, so a
    caller replaces both behaviours with one call.

    Returns a dict of key -> (verdict, detail).
    """
    verdicts = {}
    for k, prev in (prev_series or {}).items():
        if k not in out_series:
            out_series[k] = prev
            verdicts[k] = ("carried-over", "absent this run, kept prior data")
            continue
        chosen, verdict, detail = merge_series(k, out_series[k], prev, allow_shrink)
        out_series[k] = chosen
        verdicts[k] = (verdict, detail)

    if log:
        for k, (verdict, detail) in sorted(verdicts.items()):
            if verdict in ("kept", "grafted", "new-stale", "new-allowed"):
                log(f"  [guard] {k}: {verdict.upper()} ({detail})")
        carried = [k for k, (v, _) in verdicts.items() if v == "carried-over"]
        if carried:
            log("CARRIED OVER from previous run (failed this run, kept prior "
                "data rather than deleting it): " + ", ".join(sorted(carried)))
    return verdicts


def describe_verdict(verdicts):
    """One-line summary for the pipeline log."""
    counts = {}
    for v, _ in verdicts.values():
        counts[v] = counts.get(v, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
