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
from fake_net import FakeNet, Checker, Reply, csv_rows, imf_csv_rows, bis_rows, months, wb, run_main

check = Checker()
i.OECD_PAUSE = 0
oecd_turn.check = lambda *a, **k: None

check(i.pct_change([["2025-08", 100.0], ["2026-08", 105.6]], 12) == [["2026-08", 5.6]], "12-month CPI change")
check(i.usd_to_isk([["2026-05", 1038.0], ["2026-06", 780.0]], {"2026-05": 125.0}) == [["2026-05", 129750.0]],
      "a month with no BIS rate is left out, never converted at another month's rate")
check(not hasattr(i, "drop_mirrored"), "the copied-figure rule is gone: its premise was disproved by the issuer")

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
IMF_M = months(2006, 1, 2026, 6)           # the IMF mirror: exports to June, imports to May 2026
EX_USD, IM_USD, RATE = 780.0, 1038.0, 120.8636
SI_M = months(2011, 1, 2026, 9)            # the issuer is fresher: to September 2026
ROWS = {"XFRETTVx0": "Exports fob, total", "MNFLKM0": "Imports cif, total", "M_X_00": "Balance of trade"}


def si_values(scale=1.0):
    ex = {p: round(EX_USD * RATE * 1.003 * scale, 1) for p in SI_M}
    im = {p: round(IM_USD * RATE * 1.001 * scale, 1) for p in SI_M}
    ex["2013-03"], im["2013-03"] = 50918.6, 50873.3          # real months the old rule dropped: a few krónur apart
    return ex, im


def px_meta(texts=None, first="2011-01"):
    mm = [p for p in SI_M if p >= first]
    return {"title": "The value of exports and imports by month (FOB/CIF) 2011-2026", "variables": [
        {"code": "Vara", "text": "Product", "values": list(ROWS), "valueTexts": list((texts or ROWS).values())},
        {"code": "Manudur", "text": "Month", "time": True,
         "values": [p.replace("-", "M") for p in mm], "valueTexts": [p.replace("-", "M") for p in mm]}]}


PX = {"scale": 1.0, "break_balance": False, "fail": False, "texts": None, "first": "2011-01", "end": "2026-09"}


def px_post(url, json=None, **kw):
    if PX["fail"]:
        raise RuntimeError("Statistics Iceland unreachable")
    ex, im = si_values(PX["scale"])
    mm = [p for p in SI_M if PX["first"] <= p <= PX["end"]]
    vals = []
    for code in ROWS:
        for p in mm:
            v = {"XFRETTVx0": ex[p], "MNFLKM0": im[p], "M_X_00": round(ex[p] - im[p], 1)}[code]
            vals.append(v + 50.0 if PX["break_balance"] and code == "M_X_00" and p == "2020-05" else v)
    codes = [p.replace("-", "M") for p in mm]
    return Reply({"id": ["Vara", "Manudur"], "size": [3, len(codes)], "value": vals, "dimension": {
        "Vara": {"category": {"index": {c: n for n, c in enumerate(ROWS)}, "label": dict(ROWS)}},
        "Manudur": {"category": {"index": codes, "label": {c: c for c in codes}}}}})


net = FakeNet([
    ("DF_QNA", csv_rows(QH, qna)),
    ("DF_IALFS_UNE_M", csv_rows(LH, lfs)),
    ("WS_CBPOL/1.0/M.IS", bis_rows([(p, 8.0 if p > "2026-03" else 8.5) for p in months(2010, 1, 2026, 9)])),
    ("WS_XRU/1.0/M.IS.ISK.A", bis_rows([(p, RATE) for p in months(2006, 1, 2026, 9)])),
    ("UTA06001.px", lambda url: px_meta(PX["texts"], PX["first"])),
    ("ITG/~/ISL.", lambda url: imf_csv_rows([(p, EX_USD * 1e6) for p in IMF_M], INDICATOR="XG", VALUATION="FOB", UNIT="USD")
     + imf_csv_rows([(p, IM_USD * 1e6) for p in IMF_M[:-1]], INDICATOR="MG", VALUATION="CIF", UNIT="USD").split("\n", 1)[1]),
    ("BN.CAB.XOKA.GD.ZS", wb([("2025", -3.88297059863846)])),
    ("BX.KLT.DINV.WD.GD.ZS", wb([("2025", -2.16405360031405)])),
    ("PA.NUS.FCRF", wb([("2024", 137.9), ("2025", 128.44148705495)])),
])
i.requests.get = net.get
i.requests.post = px_post
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
ex_pts, im_pts = dict(s["exports"]["points"]), dict(s["imports"]["points"])
exp_ex, exp_im = si_values()
check(s["exports"]["points"][0] == ["2006-01", round(EX_USD * RATE, 1)], "history before 2011 stays on the IMF: US$ at the BIS rate, from 2006-01")
check(ex_pts["2010-12"] == round(EX_USD * RATE, 1) and ex_pts["2011-01"] == exp_ex["2011-01"], "the join: IMF-derived to 2010-12, the issuer's krónur from 2011-01, unconverted")
check(last("exports") == ["2026-09", exp_ex["2026-09"]] and last("imports") == ["2026-09", exp_im["2026-09"]],
      "trade now ends at the issuer's last month (2026-09), four months past where the IMF mirror ended")
check(last("trade_balance") == ["2026-09", round(exp_ex["2026-09"] - exp_im["2026-09"], 1)], "balance = exports less imports")
check("2013-03" in ex_pts and ex_pts["2013-03"] != im_pts["2013-03"] and "2013-03" in dict(s["trade_balance"]["points"]),
      "2013-03 (imports and exports a few krona apart at the issuer) is served, not dropped as a 'copy'")
check(len(s["exports"]["points"]) == len(months(2006, 1, 2026, 9)) and len(s["imports"]["points"]) == len(s["exports"]["points"]),
      "no gap anywhere from 2006-01 to 2026-09")
check(all("Statistics Iceland" in s[k]["label"] and "2006 to 2010" in s[k]["label"] and "\u2014" not in s[k]["label"] for k in ("exports", "imports", "trade_balance")),
      "labels name the issuer and the 2006 to 2010 IMF history")
check(d and d["fx_to_usd"]["rate"] == 128.4415 and d["fx_to_usd"]["floor"] == "1981", "FX World Bank annual, ISK per US$, floor 1981")
check("bond_yield_10y" not in s and "business_confidence" not in s, "no bond yield (IRLT ended 2022) or BCI")
check(any("DF_QNA" in u for u in net.calls) and any("DF_IALFS" in u for u in net.calls), "OECD QNA and LFS called")

# ---- failure paths: nothing is half-replaced
def raises(fn, text):
    try:
        fn()
    except Exception as exc:
        return text in str(exc)
    return False


PX.update(scale=1.0, break_balance=False, fail=False, texts=None, first="2011-01", end="2026-09")
usd = i.fetch_trade_usd()
rate = i.fetch_bis_fx_avg()
si_ok = i.fetch_trade_si()
st = i.overlap_check(usd, rate, si_ok)
check(0 < st["exports"][1] < 2 and 0 < st["imports"][1] < 2, "overlap check passes on realistic ~0.3% gaps and reports them")
PX["scale"] = 1000.0
check(raises(i.fetch_trade_si, "unit change"), "an issuer unit slip (x1000) is refused at the source")
si_big = {k: [[p, v * 1000] for p, v in pts] for k, pts in si_ok.items()}
check(raises(lambda: i.overlap_check(usd, rate, si_big), "refusing to join"), "the join is refused when the issuer sits far from the IMF history")
PX["scale"] = 1.0
PX["break_balance"] = True
check(raises(i.fetch_trade_si, "own balance"), "exports less imports must reconcile with the table's own balance row")
PX["break_balance"] = False
PX["texts"] = {"XFRETTVx0": "Exports fob, total", "MNFLKM0": "Imports fob, total", "M_X_00": "Balance of trade"}
check(raises(i.fetch_trade_si, "expected"), "a row whose text changed (cif to fob) is refused, not served")
PX["texts"] = None
PX["first"] = "2012-01"
check(raises(i.fetch_trade_si, "gap"), "a table that no longer starts by 2011-01 is refused (the join would leave a gap)")
PX["first"] = "2011-01"
PX["end"] = "2025-01"
check(raises(i.fetch_trade_si, "too old"), "a stale issuer table is refused")
PX["end"] = "2026-09"

prev = {"series": {k: {"points": [[p, 1.0] for p in months(2006, 1, 2010, 12)] + [["2011-01", 9.0]]} for k in ("exports", "imports")}}
real_get = i.requests.get
i.requests.get = lambda url, *a, **k: (_ for _ in ()).throw(RuntimeError("IMF down")) if "ITG" in url else real_get(url, *a, **k)
built = i.build_trade(si_ok, prev)
i.requests.get = real_get
check(built["exports"][0] == ["2006-01", 1.0] and built["exports"][59] == ["2010-12", 1.0] and built["exports"][60][0] == "2011-01" and built["exports"][60][1] == dict(si_ok["exports"])["2011-01"],
      "IMF down: the pre-2011 months come from the previous run, 2011 on from the issuer")
i.requests.get = lambda url, *a, **k: (_ for _ in ()).throw(RuntimeError("IMF down")) if "ITG" in url else real_get(url, *a, **k)
check(raises(lambda: i.build_trade(si_ok, {}), "no trade history before"), "IMF down and no previous run: no trade, rather than a series that starts in 2011")
i.requests.get = real_get


def seed(d):
    import json as _j
    _j.dump({"updated": "2026-10-01T00:00:00Z", "sample": False, "series": {
        "exports": {"label": "old", "unit": "ISKm", "freq": "months", "points": [["2026-04", 111.0], ["2026-05", 222.0]]},
        "imports": {"label": "old", "unit": "ISKm", "freq": "months", "points": [["2026-04", 333.0], ["2026-05", 444.0]]},
        "trade_balance": {"label": "old", "unit": "ISKm", "freq": "months", "points": [["2026-04", -222.0], ["2026-05", -222.0]]}}},
        open(os.path.join(d, i.OUT_FILE), "w"))


PX["fail"] = True
rc2, d2 = run_main(i, seed)
s2 = (d2 or {}).get("series", {})
check(rc2 == 0 and s2["exports"]["points"][-1] == ["2026-05", 222.0] and s2["exports"]["label"] == "old",
      "issuer unreachable: the previous trade series is carried over untouched, not replaced by the IMF")
PX["fail"] = False
PX["scale"] = 1000.0
rc3, d3 = run_main(i, seed)
check(rc3 == 0 and d3["series"]["exports"]["points"][-1] == ["2026-05", 222.0],
      "issuer unit slip in a full run: trade is carried over, nothing half-replaced")
PX["scale"] = 2.5     # plausible monthly size, but 150% off the IMF history: only the overlap guard can stop this
rc4, d4 = run_main(i, seed)
check(rc4 == 0 and d4["series"]["exports"]["points"][-1] == ["2026-05", 222.0],
      "issuer plausible but far from the IMF history in a full run: the join is refused, trade carried over")
PX["scale"] = 1.0

check.done()
