"""Offline tests for fetch_tw.py (no network). Run: python3 tools/test_fetch_tw.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_tw as t

fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += not cond


# CBC WebF1: ROC dates, a header row after a title line, the discount rate column found by name
csv_text = "央行政策利率\n日期,重貼現率,擔保放款融通利率\n113/03/22,2.000,2.375\n114/06/19,2.000,2.375\n112/03/24,1.875,2.250\n"
pts = t.parse_cbc_rates(csv_text)
d = dict(pts)
check(d["2023-03"] == 1.875 and d["2024-02"] == 1.875, "rate held from decision to next decision")
check(d["2024-03"] == 2.0, "decision month takes the new rate")
check(pts[0][0] == "2023-03", "series starts at the first decision")
check(t._cbc_date("20250919") == "2025-09-19" and t._cbc_date("114/9/19") == "2025-09-19", "Gregorian and ROC dates")
try:
    t.parse_cbc_rates("a,b\n1,2\n")
    check(False, "file without a discount-rate column must fail")
except ValueError:
    check(True, "file without a discount-rate column fails loudly")

# IMF ITG conversion: US$ to NT$ million, ends at the last month with both flows and a rate
rows = [{"INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "USD", "TIME_PERIOD": "2026-M07", "OBS_VALUE": "4e10"},
        {"INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "USD", "TIME_PERIOD": "2026-M08", "OBS_VALUE": "5e10"},
        {"INDICATOR": "MG", "VALUATION": "CIF", "UNIT": "USD", "TIME_PERIOD": "2026-M07", "OBS_VALUE": "3e10"},
        {"INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "XDC", "TIME_PERIOD": "2026-M07", "OBS_VALUE": "9e12"}]
tr = t.trade_from_usd(rows, {"2026-07": 30.0, "2026-08": 31.0}, "NT$")
check(tr["exports"] == [["2026-07", 1200000.0]], "exports converted and cut to months with both flows")
check(tr["trade_balance"] == [["2026-07", 300000.0]], "balance = exports - imports")
try:
    t.trade_from_usd([r for r in rows if r["INDICATOR"] != "MG"], {"2026-07": 30.0}, "NT$")
    check(False, "missing imports must fail")
except ValueError:
    check(True, "missing imports fails loudly")

print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
