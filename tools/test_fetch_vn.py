"""Offline tests for fetch_vn.py (no network). Run: python3 tools/test_fetch_vn.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_vn as v

fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += not cond


ix = [[f"2025-{m:02d}", 100 + m] for m in range(1, 13)] + [["2026-01", 115.0]]
check(v.pct_change(ix, 12) == [["2026-01", round((115 / 101 - 1) * 100, 1)]], "y/y over twelve months")
check(v.pct_change([["2024", 100.0], ["2025", 107.0]], 1) == [["2025", 7.0]], "annual growth")
rows = [{"TIME_PERIOD": "2026-M01", "OBS_VALUE": "1.5"}, {"TIME_PERIOD": "2026-M02", "OBS_VALUE": ""},
        {"TIME_PERIOD": "2026", "OBS_VALUE": "9"}]
check(v.monthly(rows, {}) == [["2026-01", 1.5]], "monthly() skips blanks and non-monthly periods")
try:
    v.require_current([["2020-01", 1.0]], 120, "old")
    check(False, "stale series must fail")
except ValueError:
    check(True, "stale series fails loudly")

f = v.fill_single_gaps({"2025-07": 100.0, "2025-09": 102.0, "2025-12": 110.0})
check(f.get("2025-08") == 101.0, "a single missing month takes the mean of its neighbours")
check("2025-10" not in f and "2025-11" not in f, "a two-month hole is left for the audit")
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
