"""Offline tests for fetch_pe.py (no network). Run: python3 tools/test_fetch_pe.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_pe as e
import imf_weo
import bis_daily
from fake_net import FakeNet, Checker, bis_rows, months, wb, run_main

check = Checker()
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# ---- pure functions
check(e.bcrp_period("Ene.2025") == "2025-01" and e.bcrp_period("Dic.1999") == "1999-12", "BCRP month names")
check(e.bcrp_period("Set.2025") == "2025-09", "BCRP's alternative 'Set' for September")
check(e.bcrp_period("T1.23") == "2023-Q1" and e.bcrp_period("T4.98") == "1998-Q4", "BCRP quarters, two-digit years")
check(e.bcrp_period("2025") is None, "an unrecognised period is skipped, not guessed")
check(e._back("2026-Q1", 1) == "2025-Q4" and e._back("2026-Q2", 4) == "2025-Q2", "quarter arithmetic")
f = e.fill_single_gaps({"2025-07": 3.5, "2025-09": 3.6, "2025-12": 3.7})
check(f.get("2025-08") == 3.55 and "2025-10" not in f, "single BIS gap filled, longer gap left")


def bcrp_reply(title, periods):
    return {"config": {"title": title, "series": [{"name": title, "dec": "1"}]},
            "periods": [{"name": n, "values": [str(v)]} for n, v in periods]}


def mname(p):
    return f"{MES[int(p[5:]) - 1]}.{p[:4]}"


ms = months(2023, 1, 2026, 9)
qs = [f"T{q}.{y % 100:02d}" for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)][:-2]   # to T2.26
TITLES = {
    "PN02538AQ": "Producto bruto interno por tipo de gasto (millones S/ 2007)",
    "PN02507AQ": "Producto bruto interno (variación porcentual interanual)",
    "PN38714BM": "Balanza comercial - valores FOB (millones US$)",
    "PN38718BM": "Balanza comercial - valores FOB (millones US$)",
    "PN01273PM": "Índice de precios Lima Metropolitana (var% 12 meses)",
    "PN01271PM": "Índice de precios Lima Metropolitana (var% mensual)",
}


def bcrp_route(url):
    code = url.split("/api/")[1].split("/")[0]
    if code == "PN02538AQ":
        return bcrp_reply(TITLES[code], [(q, 133188.255831495 + i * 1000) for i, q in enumerate(qs)] + [("T3.26", "n.d.")])
    if code == "PN02507AQ":
        return bcrp_reply(TITLES[code], [(q, 3.04) for q in qs])
    if code == "PN38714BM":
        return bcrp_reply(TITLES[code], [(mname(p), 7150.88190269197) for p in ms[:-2]])     # to Jul 2026
    if code == "PN01273PM":
        return bcrp_reply(TITLES[code], [(mname(p), 4.43780929) for p in ms[:-1]])         # to Aug 2026
    if code == "PN01271PM":
        return bcrp_reply(TITLES[code], [(mname(p), 0.1876) for p in ms[:-1]])
    if code == "PN38718BM":
        return bcrp_reply(TITLES[code], [(mname(p), 4983.40895481319) for p in ms[:-3]])     # to Jun 2026
    raise RuntimeError(code)


fx_ms = [p for p in ms if p != "2025-08"]        # BIS skips a month, as it did for Vietnam
net = FakeNet([
    ("estadisticas.bcrp.gob.pe", bcrp_route),
    ("WS_CBPOL/1.0/M.PE", bis_rows([(p, 4.25) for p in months(2002, 1, 2026, 9)])),
    ("WS_XRU/1.0/M.PE.PEN.A", bis_rows([(p, 3.3809210526316) for p in fx_ms])),
    ("NY.GDP.MKTP.CN", wb([("2024", 1.13e12), ("2025", 1194448000000)])),
    ("NY.GDP.MKTP.KN", wb([("2024", 5.85e11), ("2025", 605708000000)])),
    ("SL.UEM.TOTL.ZS", wb([("2025", 5.117)])),
    ("BN.CAB.XOKA.GD.ZS", wb([("2025", 3.58499497152416)])),
    ("BX.KLT.DINV.WD.GD.ZS", wb([("2025", 3.09176833503603)])),
    ("PA.NUS.FCRF", wb([("1990", 0.19), ("1991", 0.77), ("2025", 3.56706380329909)])),
])
e.requests.get = net.get
bis_daily.extend = lambda pts, area, label="": pts
imf_weo.fetch = lambda iso3, ind: [["2025", 30.145 if ind == imf_weo.DEBT else -2.354]]
rc, d = run_main(e)
s = (d or {}).get("series", {})
last = lambda k: s.get(k, {}).get("points", [[None, None]])[-1]
check(rc == 0 and d is not None, "main() writes data-pe.json")
check(last("cpi") == ["2026-08", 4.4] and last("cpi_mom") == ["2026-08", 0.2], "CPI from BCRP Lima: 4.4% y/y, 0.2% m/m (Aug 2026)")
check("BCRP" in s.get("cpi", {}).get("label", "") and not any("CPI/~/PER" in u for u in net.calls), "CPI is BCRP's, no IMF CPI call")
check(last("policy_rate") == ["2026-09", 4.25] and s["policy_rate"]["points"][0][0] == "2003-09",
      "reference rate 4.25%, starting September 2003")
check(last("gdp_real") == ["2026-Q2", round(133188.255831495 + 13000, 1)] and s["gdp_real"]["freq"] == "quarters",
      "real GDP quarterly to Q2 2026 in PEN million at 2007 prices ('n.d.' Q3 skipped)")
check(last("gdp_growth_yoy") == ["2026-Q2", 3.0], "y/y growth as published, one decimal place")
check(last("gdp_level") == ["2025", 1194448.0] and s["gdp_level"]["freq"] == "years", "nominal GDP annual (World Bank)")
check(last("exports") == ["2026-06", round(7150.88190269197 * 3.3809210526316, 1)],
      "exports in soles at the month's BIS rate, ending where imports end")
check(last("trade_balance") == ["2026-06", round(round(7150.88190269197 * 3.3809210526316, 1)
                                              - round(4983.40895481319 * 3.3809210526316, 1), 1)], "balance = exports - imports")
check("2025-08" in dict(s.get("exports", {}).get("points", [])), "trade kept for the month BIS skipped (gap filled)")
check(d and d["fx_to_usd"]["floor"] == "1991" and d["fx_to_usd"]["rate"] == 3.5671, "FX floor 1991, 3.5671 soles per US$")
check(not any("oecd" in u for u in net.calls), "no OECD calls")

# a reassigned BCRP code fails loudly instead of feeding the page wrong numbers
TITLES["PN02538AQ"] = "Producto bruto interno (índice 2007 = 100)"
orig = bcrp_route
e.requests.get = FakeNet([("estadisticas.bcrp.gob.pe", lambda u: bcrp_reply(TITLES["PN02538AQ"], [(q, 166.6) for q in qs]))]).get
try:
    e.fetch_gdp_real()
    check(False, "a wrong-title BCRP reply must fail")
except ValueError as exc:
    check("title" in str(exc), "a BCRP reply with the wrong title fails, naming the title")
check.done()
