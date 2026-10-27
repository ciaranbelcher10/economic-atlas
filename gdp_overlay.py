"""Overlay the OECD's newer quarterly national accounts onto an IMF IFS (via FRED) GDP series.

Why (v1.9.9). South Africa's and Argentina's GDP come from IMF IFS through FRED, which trails the
national statistics offices by a quarter or more: Stats SA published Q2 2026 on 8 September and INDEC
on 17 September, while FRED still ended at 2026-Q1 on 24 October. The OECD's quarterly national
accounts carry the same national figures sooner. A probe on 25 October 2026 showed that, for the four
series used here, the OECD values reproduce the IFS values we store to 0.00% for every quarter except
the latest one or two, which the statistics offices had revised (largest: 0.21%).

What this does NOT do. It never appends a bare quarter to old values. The offices revise the previous
quarter when they publish a new one, so appending Q2 to an old-vintage Q1 would put a wrong
quarter-on-quarter rate into the page (South Africa: -0.36% instead of the published -0.24%). Instead
the OECD figures replace the IFS ones from the start of a validated window onward.

The checks, all of which must pass or the IFS series is left exactly as fetched:
  1. at least MIN_OVERLAP overlapping quarters, and the last WINDOW of them agree within TOLERANCE
     (1%: ordinary revisions are an order of magnitude smaller; a different basis or a rebased level
     is much larger);
  2. the OECD series is contiguous from the window start to its last quarter (no gap);
  3. the OECD series does not end before the IFS one (it would make the series less current).

The OECD request only happens in the country's OECD turn (oecd_turn); off-turn runs raise
NotThisHour, the IFS series is left as fetched, and series_guard keeps the previous, newer series.
"""
from __future__ import annotations

import csv
import io
import re
import time

import requests

import oecd_turn

QNA_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
           "Q..{iso}..........?format=csvfile&startPeriod=1990-Q1")
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
OECD_PAUSE = 2
WINDOW = 8          # overlapping quarters that must agree
MIN_OVERLAP = 6     # fewer than this and there is nothing to validate against
TOLERANCE = 0.01    # 1%
DUP_TOLERANCE = 1e-5  # relative: the same figure published in two OECD tables, rounded differently
RELABEL = "latest quarters from OECD QNA"
_QPAT = re.compile(r"^(\d{4})-Q([1-4])$")


def qna_rows(iso: str) -> list:
    """Rows of the OECD quarterly national accounts for one country. Only in this script's OECD turn."""
    oecd_turn.check()
    time.sleep(OECD_PAUSE)
    r = requests.get(QNA_URL.format(iso=iso), timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [oecd] DF_QNA {iso} status={r.status_code}")
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def select(rows: list, **want) -> dict:
    """{quarter: value} for the rows matching every column=value in `want`.

    The OECD publishes some series in more than one table (South Africa: TABLE_IDENTIFIER T0101 and
    T0102), and the two copies differ only by rounding in the last decimal, e.g. 1048271.7 against
    1048271.6. Values within DUP_TOLERANCE of each other are the same figure, and the LOWER one is
    kept so the result does not depend on row order. Values further apart than that mean the
    selector does not pin down one series, and picking either would be a guess, so this raises."""
    seen: dict = {}
    for row in rows:
        if not all((row.get(k) or "") == v for k, v in want.items()):
            continue
        try:
            v = float(row.get("OBS_VALUE") or "")
        except ValueError:
            continue
        per = (row.get("TIME_PERIOD") or "").strip()
        if not _QPAT.match(per):
            continue
        seen.setdefault(per, []).append(v)
    out: dict = {}
    for per, vs in seen.items():
        lo, hi = min(vs), max(vs)
        if hi - lo > DUP_TOLERANCE * max(1.0, abs(hi)):
            raise ValueError(f"OECD selector is ambiguous: {per} has values {lo} and {hi}, "
                             f"further apart than rounding")
        out[per] = lo
    return out


def _next(p: str) -> str:
    y, q = int(p[:4]), int(p[6])
    return f"{y + (q == 4)}-Q{q % 4 + 1}"


def _seq(a: str, b: str) -> list:
    out, p = [a], a
    while p < b:
        p = _next(p)
        out.append(p)
    return out


def overlay(base: list, cand: dict, window: int = WINDOW, tol: float = TOLERANCE,
            min_overlap: int = MIN_OVERLAP) -> tuple:
    """Return (points, report). `base` is [[quarter, value], ...] ascending; `cand` is {quarter: value}.
    report["applied"] is False, with a reason, whenever any check fails, and points is then `base`."""
    def no(reason):
        return list(base), {"applied": False, "reason": reason}

    if not base or not cand:
        return no("no base series" if not base else "no OECD series")
    if not all(_QPAT.match(p[0]) for p in base):
        return no("base series is not quarterly")
    by = {p: v for p, v in base}
    overlap = [p for p, _ in base if p in cand and by[p]]
    if len(overlap) < min_overlap:
        return no(f"only {len(overlap)} overlapping quarters, need {min_overlap}")
    win = overlap[-window:]
    devs = [(abs(cand[p] / by[p] - 1), p) for p in win]
    worst, where = max(devs)
    if worst > tol:
        return no(f"OECD differs from IFS by {worst * 100:.2f}% at {where} "
                  f"(limit {tol * 100:.0f}%): different basis or level")
    start, last_c, last_b = win[0], max(cand), base[-1][0]
    if last_c < last_b:
        return no(f"OECD ends {last_c}, before IFS {last_b}")
    seq = _seq(start, last_c)
    missing = [p for p in seq if p not in cand]
    if missing:
        return no(f"OECD has a gap at {missing[0]}")
    merged = [[p, v] for p, v in base if p < start] + [[p, round(cand[p], 1)] for p in seq]
    replaced = sum(1 for p, _ in base if p >= start)
    return merged, {"applied": True, "from": start, "replaced": replaced,
                    "added": sum(1 for p in seq if p > last_b),
                    "max_dev": worst, "checked": len(win), "last": last_c}


def relabel(label: str) -> str:
    """Add the overlay note to a series label. The series is still mostly IMF IFS, so the note names that too
    unless the label already does: a label that says only "OECD" misstates where most of the history comes from
    (citation_provider.py flagged exactly that once South Africa's overlay reached the data)."""
    if RELABEL in label:
        return label
    note = RELABEL if "IMF" in label else "IMF IFS, " + RELABEL
    return label[:-1] + ", " + note + ")" if label.endswith(")") else label + " (" + note + ")"


def apply_overlay(series: dict, key: str, rows: list, sel: dict, log=print):
    """Overlay one series in `series` (the run's output map) in place. Returns the report or None."""
    s = series.get(key)
    if not s or s.get("freq") != "quarters" or not s.get("points"):
        log(f"SKIP  {key:<16} OECD overlay: no quarterly IFS series this run")
        return None
    merged, rep = overlay(s["points"], select(rows, **sel))
    if not rep["applied"]:
        log(f"WARN  {key:<16} OECD overlay not applied: {rep['reason']} (IFS series kept)")
        return rep
    s["points"] = merged
    s["label"] = relabel(s["label"])
    log(f"  ok  {key:<16} OECD overlay from {rep['from']}: {rep['replaced']} quarters replaced, "
        f"{rep['added']} added, max deviation {rep['max_dev'] * 100:.2f}% over {rep['checked']} quarters "
        f"(now to {rep['last']})")
    return rep
