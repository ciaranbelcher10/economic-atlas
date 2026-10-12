"""Offline tests for fetch_ng.py (no network). Run: python3 tools/test_fetch_ng.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fetch_ng as n

fails = 0


def check(cond, msg):
    global fails
    print(("  ok    " if cond else "  FAIL  ") + msg)
    fails += not cond


check(n.pct_change([["2024", 100.0], ["2025", 103.4]], 1) == [["2025", 3.4]], "annual growth")
rows = [{"TIME_PERIOD": "2026-M07", "OBS_VALUE": "15.43"}, {"TIME_PERIOD": "2026-M08", "OBS_VALUE": "15.39084"},
        {"TIME_PERIOD": "2026-M09", "OBS_VALUE": ""}]
check(n.monthly(rows, {}) == [["2026-07", 15.43], ["2026-08", 15.39084]], "monthly() reads IMF periods and skips blanks")
try:
    n.require_current([["2025-01", 27.5]], n.POLICY_MAX_AGE, "old")
    check(False, "a policy rate older than POLICY_MAX_AGE must fail")
except ValueError:
    check(True, "a policy rate older than POLICY_MAX_AGE fails loudly")
check(n.POLICY_MAX_AGE > n.MONTHLY_MAX_AGE, "the policy rate is allowed the IMF's longer lag, CPI is not")
check("NGA.CPI._T.YOY_PCH_PA_PT.M" in n.CPI_YOY_URL and "NGA.CPI._T.POP_PCH_PA_PT.M" in n.CPI_MOM_URL,
      "CPI uses the IMF's published y/y and m/m rates")
check("NGA.MFS166_RT_PT_A_PT.M" in n.POLICY_URL, "policy rate is MFS166, the monetary policy-related rate")
keys = [s[0] for s in n.SERIES]
check("trade" not in keys and "exports" not in keys, "no trade series: the IMF has no ITG series for Nigeria")
check(all(s[3] == "NGNm" for s in n.SERIES if s[0] in ("gdp_level", "gdp_real")), "GDP in naira million")
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
