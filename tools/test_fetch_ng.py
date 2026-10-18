"""Offline tests for fetch_ng.py (no network). Run: python3 tools/test_fetch_ng.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
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

# v1.8.7: policy rate from the CBN decisions page, merged with the IMF mirror.
import json as _json
from unittest import mock
FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
page = open(os.path.join(FX, "cbn_decisions.html"), encoding="utf-8").read()
imf = _json.load(open(os.path.join(FX, "ng_policy_imf.json")))   # IMF MFS166 as served 18 Oct 2026, ends 2026-04
dec = dict(n.parse_cbn_decisions(page))
check(dec.get("2026-09") == 23.0 and dec.get("2026-02") == 26.5 and dec.get("2025-09") == 27.0,
      "CBN page: 23% (Sep 2026), 26.5% (Feb 2026), 27% (Sep 2025)")
check(dec.get("2024-02") == 22.75 and dec.get("2016-07") == 14.0 and dec.get("2011-10") == 12.0,
      "CBN page: year from the body, 'from A to B', and 'raised by ... to' forms")
check(dec.get("2008-06") == 10.25 and dec.get("2014-05") == 12.0,
      "CBN page: 'per cent' split across lines and a bare '%' both read")
check(dec.get("2020-01") == 13.5, "CBN page: an earlier CRR item does not stand in for the MPR")
m = dict(n.merge_policy(sorted(dec.items()), imf, "2026-10"))
check(m["2026-02"] == 26.5 and m["2026-04"] == 26.5, "merge: the CBN's 24 Feb 2026 cut overrides the IMF's 27.0")
check(m["2026-09"] == 23.0 and m["2026-10"] == 23.0, "merge: extends past the IMF's last month to the 22 Sep 2026 cut")
check(m["2024-11"] == 27.5, "merge: keeps the IMF's Nov 2024 rise, which the CBN page omits")
check(m["2009-07"] == 6.0 and m["2011-05"] == 8.0, "merge: keeps IMF changes in years the CBN page skips")
check(min(m) == imf[0][0], "merge: history kept, starts where the IMF series starts")
bad = re.sub(r"to (\d+(?:\.\d+)?) per cent", lambda x: f"to {float(x.group(1)) + 1} per cent", page)
try:
    n.merge_policy(n.parse_cbn_decisions(bad), imf, "2026-10")
    check(False, "a garbled CBN parse must be refused")
except ValueError:
    check(True, "a garbled CBN parse is refused")
with mock.patch.object(n, "fetch_policy_rate_imf", return_value=imf), \
        mock.patch.object(n, "require_current", side_effect=lambda pts, *a: pts), \
        mock.patch.object(n.requests, "get", side_effect=n.requests.ConnectionError("down")):
    got = n.fetch_policy_rate()
    check(got == imf, "CBN down: falls back to the IMF series unchanged (no partial merge)")
print(f"\n{fails} failures")
sys.exit(1 if fails else 0)
