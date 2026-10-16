"""Offline tests for fetch_pk.py (no network). Run: python3 tools/test_fetch_pk.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_pk as k
import imf_weo
from fake_net import FakeNet, Checker, imf_csv_rows, months, wb, run_main

check = Checker()

# ---- pure functions
check(k.pct_change([["2024", 100.0], ["2025", 102.5]], 1) == [["2025", 2.5]], "annual growth")
rows = []
for per, x, m in (("2026-04", 6.0e11, 1.8e12), ("2026-05", 6.24e11, 1.92e12), ("2026-06", 6.3e11, None)):
    rows.append({"TIME_PERIOD": per.replace("-", "-M"), "OBS_VALUE": str(x), "INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "XDC"})
    rows.append({"TIME_PERIOD": per.replace("-", "-M"), "OBS_VALUE": "12.5", "INDICATOR": "XG", "VALUATION": "FOB", "UNIT": "PT"})
    if m:
        rows.append({"TIME_PERIOD": per.replace("-", "-M"), "OBS_VALUE": str(m), "INDICATOR": "MG", "VALUATION": "CIF", "UNIT": "XDC"})
saved = k.TRADE_MAX_AGE
k.TRADE_MAX_AGE = 10 ** 6
t = k.trade_from_xdc(rows)
k.TRADE_MAX_AGE = saved
check(t["exports"][-1] == ["2026-05", 624000.0], "exports in PKR million, ending where imports end (June dropped)")
check(t["trade_balance"][-1] == ["2026-05", round(624000.0 - 1920000.0, 1)], "balance = exports - imports")
check(all(p[1] > 1000 for p in t["exports"]), "percentage-change rows (UNIT PT) are not read as levels")
try:
    k.trade_from_xdc([r for r in rows if r["UNIT"] != "XDC"])
    check(False, "no XDC rows must fail")
except ValueError as exc:
    check("XDC" in str(exc), "no rupee rows fails loudly, naming the unit")

keys = [s[0] for s in k.SERIES]
check("policy_rate" not in keys, "no policy rate: SBP's API is unreachable and no international copy exists")
check(all(s[3] == "PKRm" for s in k.SERIES if s[0] in ("gdp_level", "gdp_real", "trade")), "GDP and trade in rupee million")
check("PAK.CPI._T.YOY_PCH_PA_PT.M" in k.CPI_YOY_URL, "CPI uses the IMF's published y/y rate")
old = [{"TIME_PERIOD": "2021-M10", "OBS_VALUE": "5e11", "INDICATOR": i, "VALUATION": v, "UNIT": "XDC"} for i, v in (("XG", "FOB"), ("MG", "CIF"))]
k.TRADE_MAX_AGE = 10 ** 6
t2 = k.trade_from_xdc(old + rows)
k.TRADE_MAX_AGE = saved
check(t2["exports"][0][0] == "2026-04" and "2021-10" not in dict(t2["exports"]), "trade before July 2022 (before the IMF's gap) is left out")

# ---- end to end on fake replies shaped like the 13 Oct 2026 probe
ms = months(2023, 1, 2026, 9)
ms6 = months(2023, 1, 2026, 6)
net = FakeNet([
    ("CPI/~/PAK.CPI._T.YOY", imf_csv_rows([(p, 10.25914833217503) for p in ms])),
    ("CPI/~/PAK.CPI._T.POP", imf_csv_rows([(p, 1.274608318182397) for p in ms])),
    ("ITG/~/PAK.", imf_csv_rows([(p, 6.24158601682e11) for p in ms6], INDICATOR="XG", VALUATION="FOB", UNIT="XDC")
     + imf_csv_rows([(p, 1.922981738528e12) for p in ms6], INDICATOR="MG", VALUATION="CIF", UNIT="XDC").split("\n", 1)[1]),
    ("NY.GDP.MKTP.CN", wb([("2024", 1.05e14), ("2025", 113807399205117)])),
    ("NY.GDP.MKTP.KN", wb([("2024", 4.25e13), ("2025", 43612749335699.5)])),
    ("SL.UEM.TOTL.ZS", wb([("2024", 5.5), ("2025", 5.42)])),
    ("BN.CAB.XOKA.GD.ZS", wb([("2025", -0.109990047825719)])),
    ("BX.KLT.DINV.WD.GD.ZS", wb([("2025", 0.454693640126553)])),
    ("PA.NUS.FCRF", wb([("1981", 9.9), ("1982", 11.8), ("2025", 281.143001173202)])),
])
k.requests.get = net.get
imf_weo.fetch = lambda iso3, ind: [["2024", 70.0], ["2025", 72.767 if ind == imf_weo.DEBT else -5.366]]
rc, d = run_main(k)
s = (d or {}).get("series", {})
check(rc == 0 and d is not None, "main() writes data-pk.json")
check(s.get("cpi", {}).get("points", [[0, 0]])[-1] == ["2026-09", 10.3], "CPI 10.3% (Sep 2026), one decimal place")
check(s.get("cpi_mom", {}).get("points", [[0, 0]])[-1] == ["2026-09", 1.3], "CPI m/m 1.3%")
check(s.get("exports", {}).get("points", [[0, 0]])[-1] == ["2026-06", 624158.6], "exports PKR 624,158.6mn (Jun 2026)")
check(s.get("imports", {}).get("points", [[0, 0]])[-1] == ["2026-06", 1922981.7], "imports PKR 1,922,981.7mn")
check(s.get("trade_balance", {}).get("points", [[0, 0]])[-1] == ["2026-06", round(624158.6 - 1922981.7, 1)], "balance")
check(s.get("gdp_level", {}).get("points", [[0, 0]])[-1] == ["2025", 113807399.2], "GDP in PKR million")
check(s.get("gdp_growth", {}).get("points", [[0, 0]])[-1] == ["2025", 2.6], "growth from real GDP")
check(d and d["fx_to_usd"]["floor"] == "1982" and d["fx_to_usd"]["direction"] == "divide", "FX floor 1982, rupees per US$")
check(d and d["fx_to_usd"]["history"][-1] == ["2025", 281.143], "FX history ends 2025 at 281.143")
check(s.get("debt_gdp", {}).get("points", [[0, 0]])[-1] == ["2025", 72.767], "debt from WEO")
check("policy_rate" not in s, "no policy_rate in the file")
check(not any("oecd" in u for u in net.calls), "no OECD calls")
check.done()
