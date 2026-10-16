"""Offline tests for fetch_is.py (no network). Run: python3 tools/test_fetch_is.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_is as i
import imf_weo
import bis_daily
import oecd_prices
import oecd_turn
from fake_net import FakeNet, Checker, csv_rows, imf_csv_rows, bis_rows, months, wb, run_main

check = Checker()
i.OECD_PAUSE = 0
oecd_turn.check = lambda *a, **k: None

check(i.pct_change([["2025-08", 100.0], ["2026-08", 105.6]], 12) == [["2026-08", 5.6]], "12-month CPI change")
check(i.usd_to_isk([["2026-05", 1038.0], ["2026-06", 780.0]], {"2026-05": 125.0}) == [["2026-05", 129750.0]],
      "a month with no BIS rate is left out, never converted at another month's rate")
mir = i.drop_mirrored({"exports": [["2026-01", 600.0], ["2026-02", 640.0]], "imports": [["2026-01", 600.0], ["2026-02", 720.0]]})
check(mir["exports"] == [["2026-02", 640.0]] and mir["imports"] == [["2026-02", 720.0]],
      "a month where imports equal exports exactly (a copied IMF figure) is left out of both")

QH = ["FREQ", "ADJUSTMENT", "TRANSACTION", "TABLE_IDENTIFIER", "PRICE_BASE", "TRANSFORMATION", "UNIT_MEASURE",
      "TIME_PERIOD", "OBS_VALUE"]
qs = [f"{y}-Q{q}" for y in range(2015, 2027) for q in (1, 2, 3, 4)][:-2]           # to 2026-Q2
qna = []
for n, q in enumerate(qs):
    qna += [["Q", "Y", "B1GQ", "T0102", "V", "N", "XDC", q, 1000000 + n * 7000],
            ["Q", "N", "B1GQ", "T0102", "V", "N", "XDC", q, 990000 + n * 7000],          # unadjusted: not used
            ["Q", "Y", "B1GQ", "T0102", "L", "N", "XDC", q, 800000 + n * 2500],
            ["Q", "Y", "B1GQ", "T0102", "LR", "LA", "XDC", q, 3600000],                    # annualised: not used
            ["Q", "Y", "B1GQ", "T0102", "L", "G1", "PC", q, -2.97961622],
            ["Q", "Y", "B1GQ", "T0102", "L", "GY", "PC", q, 0.30386348]]
LH = ["MEASURE", "ADJUSTMENT", "SEX", "AGE", "FREQ", "TIME_PERIOD", "OBS_VALUE"]
lms = months(2003, 1, 2026, 8)
lfs = [["UNE_LF_M", "Y", "_T", "Y_GE15", "M", p, 5.8] for p in lms] + \
      [["UNE_LF_M", "N", "_T", "Y_GE15", "M", p, 6.0] for p in lms] + \
      [["UNE_LF_M", "Y", "_T", "Y15T24", "M", p, 11.0] for p in lms]
ms = months(2023, 1, 2026, 9)
net = FakeNet([
    ("DF_QNA", csv_rows(QH, qna)),
    ("DF_IALFS_UNE_M", csv_rows(LH, lfs)),
    ("WS_CBPOL/1.0/M.IS", bis_rows([(p, 8.0 if p > "2026-03" else 8.5) for p in months(2010, 1, 2026, 9)])),
    ("WS_XRU/1.0/M.IS.ISK.A", bis_rows([(p, 120.8636) for p in ms])),
    ("ITG/~/ISL.", imf_csv_rows([(p, 780000000.0) for p in ms[:-3]], INDICATOR="XG", VALUATION="FOB", UNIT="USD")
     + imf_csv_rows([(p, 1038000000.0) for p in ms[:-4]], INDICATOR="MG", VALUATION="CIF", UNIT="USD").split("\n", 1)[1]),
    ("BN.CAB.XOKA.GD.ZS", wb([("2025", -3.88297059863846)])),
    ("BX.KLT.DINV.WD.GD.ZS", wb([("2025", -2.16405360031405)])),
    ("PA.NUS.FCRF", wb([("2024", 137.9), ("2025", 128.44148705495)])),
])
i.requests.get = net.get
bis_daily.extend = lambda pts, area, label="": pts
idx = {p: 100 * (1.0045 ** n) for n, p in enumerate(months(2000, 1, 2026, 8))}
oecd_prices.fetch_cpi_index = lambda areas, freq, http_get=None, label="": \
    sorted([[p, v] for p, v in idx.items()]) if (areas, freq) == (("ISL",), "M") else None
imf_weo.fetch = lambda iso3, ind: [["2025", 56.68 if ind == imf_weo.DEBT else -2.648]]
rc, d = run_main(i)
s = (d or {}).get("series", {})
last = lambda k: s.get(k, {}).get("points", [[None, None]])[-1]
check(rc == 0 and d is not None, "main() writes data-is.json")
check(last("gdp_level") == ["2026-Q2", float(1000000 + 45 * 7000)], "nominal GDP: T0102 current prices, SA, ISK million")
check(last("gdp_real") == ["2026-Q2", float(800000 + 45 * 2500)], "real GDP: T0102 chain-linked (L), SA, not the annualised LR")
check(last("gdp_growth") == ["2026-Q2", -3.0] and last("gdp_growth_yoy") == ["2026-Q2", 0.3], "growth G1 and GY as published")
check(s.get("cpi", {}).get("freq") == "months" and last("cpi") == ["2026-08", 5.5], "CPI monthly, 12-month change from the index")
check(last("cpi_mom") == ["2026-08", 0.4] and "cpi_qoq" not in s, "CPI m/m monthly (no quarterly key)")
check(last("unemployment") == ["2026-08", 5.8] and s["unemployment"]["freq"] == "months", "unemployment 15+ SA monthly 5.8%")
check(last("policy_rate") == ["2026-09", 8.0] and s["policy_rate"]["points"][0][0] == "2014-06", "key rate 8.0%, from June 2014")
check(last("exports") == ["2026-05", round(780.0 * 120.8636, 1)], "exports converted at BIS ISK per US$, ending where imports end")
check(last("trade_balance") == ["2026-05", round(round(780.0 * 120.8636, 1) - round(1038.0 * 120.8636, 1), 1)], "balance")
check(d and d["fx_to_usd"]["rate"] == 128.4415 and d["fx_to_usd"]["floor"] == "1981", "FX World Bank annual, ISK per US$, floor 1981")
check("bond_yield_10y" not in s and "business_confidence" not in s, "no bond yield (IRLT ended 2022) or BCI")
check(any("DF_QNA" in u for u in net.calls) and any("DF_IALFS" in u for u in net.calls), "OECD QNA and LFS called")
check.done()
