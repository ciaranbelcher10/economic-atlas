"""Offline tests for fetch_eg.py (no network). Run: python3 tools/test_fetch_eg.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_eg as e

fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += not cond


check(e.pct_change([["2024", 100.0], ["2025", 104.4]], 1) == [["2025", 4.4]], "annual growth")
f = e.fill_single_gaps({"2025-07": 48.0, "2025-09": 50.0, "2025-12": 51.0})
check(f.get("2025-08") == 49.0, "a single missing BIS month takes the mean of its neighbours")
check("2025-10" not in f, "a two-month hole is left for the audit")
rows = []
for per, x, m in (("2026-M03", 4.0e9, 9.0e9), ("2026-M04", 4.2e9, 9.885e9), ("2026-M05", 4.579e9, None)):
    rows.append({"TIME_PERIOD": per, "OBS_VALUE": str(x), "INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "USD"})
    if m:
        rows.append({"TIME_PERIOD": per, "OBS_VALUE": str(m), "INDICATOR": "MG", "VALUATION": "CIF", "UNIT": "USD"})
saved = e.TRADE_MAX_AGE
e.TRADE_MAX_AGE = 10 ** 6   # the fixture dates are fixed; ageing is tested above
t = e.trade_from_usd(rows, {"2026-03": 50.0, "2026-04": 50.0, "2026-05": 50.0}, "pounds")
e.TRADE_MAX_AGE = saved
check(t["exports"][-1] == ["2026-04", 210000.0], "exports end where imports end (May dropped), converted to EGP million")
check(t["trade_balance"][-1] == ["2026-04", round(210000.0 - 494250.0, 1)], "balance = exports - imports")
sw = [{"TIME_PERIOD": "2016-M02", "OBS_VALUE": "5.24e9", "INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "USD"},
      {"TIME_PERIOD": "2016-M02", "OBS_VALUE": "1.64e9", "INDICATOR": "MG", "VALUATION": "CIF", "UNIT": "USD"},
      {"TIME_PERIOD": "2016-M03", "OBS_VALUE": "1.7e9", "INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "USD"},
      {"TIME_PERIOD": "2016-M03", "OBS_VALUE": "5.3e9", "INDICATOR": "MG", "VALUATION": "CIF", "UNIT": "USD"}]
e.unswap(sw)
check(sw[0]["OBS_VALUE"] == "1.64e9" and sw[1]["OBS_VALUE"] == "5.24e9", "February 2016 exports and imports swapped back")
check(sw[2]["OBS_VALUE"] == "1.7e9", "other months untouched")
e.unswap(sw)
check(sw[0]["OBS_VALUE"] == "1.64e9", "idempotent: a corrected month (exports below imports) is left alone")
keys = [s[0] for s in e.SERIES]
check("policy_rate" not in keys, "no policy rate: the IMF's latest CBE rate is too stale to show as current")
check(e.TRADE_MAX_AGE > e.MONTHLY_MAX_AGE, "trade is allowed the ITG lag, CPI is not")
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
