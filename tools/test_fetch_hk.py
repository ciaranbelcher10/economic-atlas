"""Offline tests for fetch_hk.py (no network). Run: python3 tools/test_fetch_hk.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_hk as h
import imf_weo
import bis_daily
from fake_net import FakeNet, Checker, imf_csv_rows, bis_rows, months, wb, run_main

check = Checker()

check(h.csd_period("202606") == "2026-Q2" and h.csd_period("197303") == "1973-Q1", "C&SD quarter labels (last month)")
check(h.csd_period("2025") is None and h.csd_period("202605") is None, "annual and non-quarter-end periods skipped")

# C&SD 310-31001 rows, shaped as the 13 Oct 2026 read: each code carries a
# level row AND a percentage row for the same period; Q2 2026 per-capita
# rows are blank with sd_value "-,r".
Q = [f"{y}{m}" for y in range(2023, 2027) for m in ("03", "06", "09", "12")][:-2]   # to 202606


def row(freq, period, sv, desc, fig, sd=""):
    return {"freq": freq, "period": period, "sv": sv, "svDesc": desc, "figure": fig, "sd_value": sd}


rows = [row("Y", "2025", "CUR", "HK$ million", 3329843, "r"), row("Y", "2025", "CON", "HK$ million", 3301474, "r")]
for i, p in enumerate(Q):
    rows += [row("Q", p, "CUR", "HK$ million", 800000 + i * 2000), row("Q", p, "CUR", "Year-on-year % change", 6.9),
             row("Q", p, "CON", "HK$ million", 790000 + i * 2000), row("Q", p, "CON", "Year-on-year % change", 4.3),
             row("Q", p, "SA1", "Quarter-to-quarter % change", -0.6),
             row("Q", p, "CONPGDP", "HK$", "" if p == "202606" else 110000, "-,r" if p == "202606" else "")]
rows[-6]["figure"], rows[-4]["figure"] = 842406, 824319        # the probe's Q2 2026 levels
ms = months(2023, 1, 2026, 9)
# C&SD 410-50001 (v1.8.3): codes are undocumented, so the test uses
# made-up codes plus a decoy series near the export level; the fetcher must
# pick each flow by its published March 2026 value, not by code.
TR = []
for i, p in enumerate(ms[:-1]):                       # to 2026-08
    ym = p.replace("-", "")
    ex = {"2026-03": 618401, "2026-02": 408795, "2025-03": 455534}.get(p, 500000 + i * 1000)
    im = 707484 if p == "2026-03" else 560000 + i * 1000
    TR += [row("M", ym, "TX", "HK$ million", ex), row("M", ym, "IM", "HK$ million", im),
           row("M", ym, "RX", "HK$ million", round(ex * 0.985)), row("M", ym, "TX", "Year-on-year % change", 35.8)]
TR += [row("Y", "2025", "TX", "HK$ million", 5000000)]
net = FakeNet([
    ("id=410-50001", {"header": {"status": {"code": 0}}, "dataSet": TR}),
    ("id=310-31001", {"header": {"status": {"code": 0}}, "dataSet": rows}),
    ("CPI/~/HKG.CPI._T.YOY", imf_csv_rows([(p, 1.651376146788991) for p in ms[:-1]])),
    ("CPI/~/HKG.CPI._T.POP", imf_csv_rows([(p, 0.09033423667570009) for p in ms[:-1]])),
    ("WS_CBPOL/1.0/M.HK", bis_rows([(p, 4.0) for p in months(1992, 1, 2026, 8)])),
    ("api.stlouisfed.org", {"observations": [{"date": "1983-10-17", "value": "7.80"}, {"date": "2026-10-09", "value": "7.7712"},
                                             {"date": "2026-10-12", "value": "."}]}),
    ("SL.UEM.TOTL.ZS", wb([("2025", 2.799)])),
    ("BN.CAB.XOKA.GD.ZS", wb([("2025", 12.2452523936474)])),
    ("BX.KLT.DINV.WD.GD.ZS", wb([("2025", 28.3131144979725)])),
])
h.requests.get = net.get
bis_daily.extend = lambda pts, area, label="": pts
imf_weo.fetch = lambda iso3, ind: [["2025", 12.069 if ind == imf_weo.DEBT else -4.546]]
os.environ["FRED_API_KEY"] = "test"
rc, d = run_main(h)
s = (d or {}).get("series", {})
last = lambda k: s.get(k, {}).get("points", [[None, None]])[-1]
check(rc == 0 and d is not None, "main() writes data-hk.json")
check(last("gdp_level") == ["2026-Q2", 842406.0] and last("gdp_real") == ["2026-Q2", 824319.0],
      "nominal HK$842,406mn and real HK$824,319mn (Q2 2026), levels not the % rows")
check(last("gdp_growth") == ["2026-Q2", -0.6], "q/q SA growth -0.6% (sv SA1)")
check(last("gdp_growth_yoy") == ["2026-Q2", 4.3], "y/y growth 4.3% (sv CON, percentage row)")
check(len(s.get("gdp_level", {}).get("points", [])) == len(Q), "annual rows ignored for the quarterly series")
check(last("cpi") == ["2026-08", 1.7] and last("cpi_mom") == ["2026-08", 0.1], "Composite CPI 1.7% y/y, 0.1% m/m")
check(last("policy_rate") == ["2026-08", 4.0] and s["policy_rate"]["points"][0][0] == "1998-10", "base rate from Oct 1998")
ex = dict(s.get("exports", {}).get("points", []))
check(ex.get("2026-03") == 618401.0 and last("exports")[0] == "2026-08", "exports = the series matching C&SD's March 2026 release, to Aug 2026")
check(dict(s.get("trade_balance", {}).get("points", [])).get("2026-03") == -89083.0, "balance = exports less imports (C&SD -89,084, rounding)")
check(not any("ITG" in u or "WS_XRU" in u for u in net.calls), "no IMF ITG or BIS rate calls for trade")
check(d and d["fx_to_usd"]["rate"] == 7.7712 and d["fx_to_usd"]["as_of"] == "2026-10", "FX month end from FRED DEXHKUS")
# v1.7.57: floor at the first H.10 month, so 1973-80 GDP is not converted at the 1981 rate
check(d and d["fx_to_usd"].get("floor") == "1981", "FX floor 1981, the first H.10 month")
check(not any("oecd" in u for u in net.calls), "no OECD calls")

# no series matching the release fails loudly, listing what was there
bad = FakeNet([("id=410-50001", {"dataSet": [row("M", ym, "TX", "HK$ million", v) for ym, v in
                                             (("202603", 731920.7), ("202602", 501460.3), ("202503", 496141.9))]})])
h.requests.get = bad.get
try:
    h.fetch_trade()
    check(False, "an export level 18% above C&SD's release must fail")
except ValueError as exc:
    check("618401" in str(exc) and "TX" in str(exc), "no anchor match fails, naming the values and the codes seen")
check.done()
