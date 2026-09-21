#!/usr/bin/env python3
"""Branch tests for the confirmed_at stamp written by series_guard.apply_guard.

The freshness lights now say whether a series matches its source's latest
release, so the stamp has to be right in exactly the cases where it is easy
to get wrong: a rejected fallback, a carried-over series, a brand-new key.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import series_guard as sg

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


def months(start_year, n, label="CPI, all items", value=lambda i: 100 + i):
    pts = []
    for i in range(n):
        y, m = start_year + i // 12, i % 12 + 1
        pts.append([f"{y}-{m:02d}", value(i)])
    return {"label": label, "unit": "%", "freq": "months", "points": pts}


def years(start, n, label="CPI, annual"):
    return {"label": label, "unit": "%", "freq": "years",
            "points": [[str(start + i), 2.0 + i] for i in range(n)]}


OLD = "2026-01-01T00:00Z"


def with_stamp(series):
    return dict(series, confirmed_at=OLD)


def run(out, prev):
    sg.apply_guard(out, prev, log=None)
    return out


# A current monthly series, ending near today, so none of these count as
# "stale previous" in the guard's own sense.
cur = months(2015, 140)            # 2015-01 .. 2026-08
cur_prev = with_stamp(months(2015, 140))

# --- accepted fresh data is stamped --------------------------------------
out = run({"cpi": months(2015, 140)}, {"cpi": cur_prev})
check("fresh series accepted: stamped now", out["cpi"].get("confirmed_at", OLD) != OLD)

# --- a brand-new key (no previous version) is stamped --------------------
out = run({"cpi_mom": months(2015, 140)}, {})
check("brand-new key is stamped", "confirmed_at" in out["cpi_mom"])

# --- carried over: stamp untouched ---------------------------------------
out = run({}, {"cpi": cur_prev})
check("carried-over series keeps its old stamp", out["cpi"].get("confirmed_at") == OLD)

# --- kept, but the source confirmed the same latest period ---------------
# Brazil's case: the OECD answered with the current series but less
# history, so the guard kept the longer one. Our latest is still confirmed.
shorter = months(2016, 128)         # 2016-01 .. 2026-08, same end
out = run({"cpi": shorter}, {"cpi": cur_prev})
check("kept, same end, same cadence: still stamped (source confirmed our latest)",
      out["cpi"].get("confirmed_at", OLD) != OLD)
check("... and the longer history is what was kept", len(out["cpi"]["points"]) == 140)

# --- kept, fallback to a coarser source: NOT stamped ----------------------
# Chile's case: the OECD failed and the World Bank annual series arrived in
# its place. The guard rightly kept the monthly series, but nothing confirmed
# it is current, so the old stamp must stand.
annual = years(1971, 55)            # ends 2025
out = run({"cpi": annual}, {"cpi": cur_prev})
check("annual fallback rejected: stamp NOT refreshed", out["cpi"].get("confirmed_at") == OLD)
check("... and the monthly series was kept", out["cpi"]["freq"] == "months")

# --- kept, incoming ends earlier: NOT stamped -----------------------------
behind = months(2015, 130)          # ends 2025-10, behind what we hold
out = run({"cpi": behind}, {"cpi": cur_prev})
check("incoming ends earlier than what we hold: not stamped",
      out["cpi"].get("confirmed_at") == OLD)

# --- the previous object is never mutated in place ------------------------
prev_obj = with_stamp(months(2015, 140))
run({"cpi": months(2016, 128)}, {"cpi": prev_obj})
check("stamping a kept series copies it rather than editing the previous run's data",
      prev_obj.get("confirmed_at") == OLD)

# --- the stamp's shape -----------------------------------------------------
stamp = sg._confirm_stamp()
check("stamp is ISO UTC to the minute", len(stamp) == 17 and stamp.endswith("Z") and stamp[10] == "T")

total = PASS + FAIL
print(f"{PASS}/{total} confirmed-at stamp branches pass")
sys.exit(1 if FAIL else 0)
