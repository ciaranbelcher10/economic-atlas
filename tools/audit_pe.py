"""Pre-launch audit of data-pe.json (v1.7.56, full page). Quarterly real GDP
and goods trade come from the Central Reserve Bank of Peru (BCRP) itself,
CPI from the IMF, the reference rate from BIS, nominal GDP and unemployment
from the World Bank (annual). Nothing about Peru is shown to users until
this passes on a file written by the real pipeline.

    python3 tools/audit_pe.py                 # data-pe.json, with cross-checks
    python3 tools/audit_pe.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rates     BCRP's twelve-month rate vs twelve chained monthly rates
                (an identity), and vs BIS's independent long-run CPI;
                the IMF's rates reported for comparison only
  policy rate   BIS vs BCRP's own reference rate (PD04722MM)
  GDP           BCRP's published y/y vs the change in the real level served;
                World Bank annual growth vs four served quarters
  FX            World Bank annual vs the mean of BIS monthly averages
  trade         soles / BIS rate = BCRP's own US$, and exports vs the IMF's
                US$ ITG figure (imports differ by design: BCRP FOB, IMF CIF)
Ranges are first estimates from the 13 Oct 2026 probe; resize only with the
publisher's figure in a comment. Exit 1 on any FAIL.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_kit as K
from audit_kit import res

DEFAULT_FILE = "data-pe.json"
BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}"
EXPECT = {
    # World Bank reports every year in today's soles (1 sol = 1 million of the
    # 1985 intis = 1 billion of the old soles), so the 1960s are tiny.
    "gdp_level": ("PENm", "years", 1e3, 3e6, None),            # probe: PEN 1.19tn (1.19e6 m) in 2025; from 1991
    "gdp_real": ("PENm", "quarters", 2e4, 3e5, None),          # probe: PEN 133bn (2007 prices) in Q1 2023
    "gdp_growth_yoy": ("%", "quarters", -35, 45, None),        # Q2 2020 near -30%, Q2 2021 near +42%
    "gdp_growth": ("%", "years", -15, 15, None),               # 1989 and 2020 near -11%
    "cpi": ("%", "months", -2, 15, 1.5),                       # BCRP from 1995 (about 11% then); June 2022 peak near 8.8%
    "cpi_mom": ("%", "months", -2, 3, None),
    "policy_rate": ("%", "months", 0, 9, 1.0),                 # from Sep 2003; 2023 peak 7.75%
    "exports": ("PENm", "months", 1e2, 6e4, None),             # probe: US$9.6bn (about PEN 32bn) in July 2026
    "imports": ("PENm", "months", 1e2, 5e4, None),
    "trade_balance": ("PENm", "months", -1.5e4, 3e4, None),
    "unemployment": ("%", "years", 2, 12, 1.5),                # probe: 5.1% (ILO modelled) in 2025
    "debt_gdp": ("%", "years", 15, 60, None),                  # probe: 30.1% in 2025
    "deficit": ("%", "years", -10, 5, None),
    "current_account": ("%", "years", -12, 8, None),
    "fdi": ("%", "years", -1, 10, None),
}
KNOWN_JUMPS = {
    # Run 1 (13 Oct 2026), ILO modelled estimate (World Bank).
    ("unemployment", "2020"): "the 2020 pandemic lockdown (one of the strictest in Latin America)",
    ("unemployment", "2021"): "recovery from the 2020 lockdown",
    # Run 3 (13 Oct 2026), BCRP Lima CPI y/y.
    ("cpi", "1997-02"): "base effect: Lima prices rose 1.5% in February 1996 (INEI, 117.31 to 119.11) and barely moved in February 1997",
    ("cpi", "2026-03"): "INEI: Lima prices rose 2.38% in March 2026, the largest monthly rise in 32 years, on fuel shortages and higher international fuel prices",
}
NOT_SERVED = {"bond_yield_10y": "no free 10-year series", "business_confidence": "no OECD coverage",
              "ecb_rate": "not a euro member"}
OFFICIAL = {
    "cpi": "INEI monthly CPI release, Metropolitan Lima, y/y (BCRP PN01273PM)", "cpi_mom": "INEI release, m/m (BCRP PN01271PM)",
    "policy_rate": "BCRP monetary policy statement", "gdp_real": "BCRP quarterly GDP (soles of 2007)",
    "gdp_growth_yoy": "INEI / BCRP quarterly GDP release", "gdp_level": "World Bank (INEI national accounts)",
    "gdp_growth": "World Bank annual growth", "exports": "BCRP trade balance (US$; soles here)",
    "imports": "BCRP trade balance", "trade_balance": "BCRP trade balance", "unemployment": "ILO modelled estimate (World Bank)",
    "debt_gdp": "IMF WEO", "deficit": "IMF WEO", "current_account": "World Bank", "fdi": "World Bank",
}
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Egypt|Nigeria|Vietnam|Pakistan|\bpounds?\b"


def bcrp(code, start, end):
    """{period: value} for one BCRP series (monthly only here)."""
    import fetch_pe
    return dict(fetch_pe.bcrp(code, start, end, ""))


def country_checks(d):
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    ok = bool(fx.get("pair") == "PEN/USD" and fx.get("direction") == "divide" and 2 < (fx.get("rate") or 0) < 6
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (soles per US$, annual, divide: fx_config.ANNUAL)",
        f"{fx.get('rate')} as of {fx.get('as_of')}, floor {fx.get('floor')}")
    K.one_decimal(d, ("cpi", "cpi_mom", "gdp_growth_yoy"))
    pr = d["series"].get("policy_rate", {}).get("points", [])
    res("PASS" if pr and pr[0][0] == "2003-09" else "FAIL", "policy_rate starts September 2003 (one measure throughout)",
        pr[0][0] if pr else "missing")


def bcrp_checks(d):
    s = d["series"]
    ref = bcrp("PD04722MM", "2024-1", "2030-12")
    got = [(p, round(v - ref[p], 3)) for p, v in s["policy_rate"]["points"][-24:] if p in ref]
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= 0.001 else "FAIL", "policy_rate (BIS) vs BCRP's own reference rate (PD04722MM)",
        f"{len(got)} months, largest gap {w} pp")
    rate = K.bis_avg("PE", "PEN")
    usd = {}
    for k, code, ind in (("exports", "PN38714BM", "XG"), ("imports", "PN38718BM", "MG")):
        for p, v in bcrp(code, "2025-1", "2030-12").items():
            usd[(ind, p)] = v
    K.trade_vs_usd(d, usd, rate, 0.1, what="BCRP's own US$ (rounding only)")
    # Run 1 (13 Oct 2026): the IMF's ITG exports for Peru ran up to 29% above
    # BCRP's in 2026, so they are reported, not used as a gate. BCRP is the
    # publisher; the binding check is the one against BCRP's own US$ above.
    itg = K.itg_usd("PER")
    rows = [(p, round(v / rate[p] / itg[("XG", p)] * 100 - 100, 1)) for p, v in s["exports"]["points"][-6:]
            if ("XG", p) in itg and p in rate]
    res("INFO", "exports vs the IMF's US$ ITG figure (different compiler; % gap)", f"{rows}")


def cpi_checks(d):
    """BCRP's y/y vs twelve of its own m/m chained (both rounded, so 0.3), and
    vs BIS's long-run CPI; the IMF's y/y is printed for comparison."""
    s = d["series"]
    mom, yoy = dict(s["cpi_mom"]["points"]), s["cpi"]["points"]
    got = []
    for p, v in yoy[-24:]:
        months = [K.back(p, i) for i in range(12)]
        if all(m in mom for m in months):
            chain = 1.0
            for m in months:
                chain *= 1 + mom[m] / 100
            got.append((p, round(v - (chain - 1) * 100, 2)))
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= 0.3 else "FAIL", "cpi vs twelve chained cpi_mom (BCRP, both rounded)",
        f"{len(got)} months, largest gap {w} pp (tolerance 0.3)")
    rows = K.csv_rows("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M.PE.771?format=csv&startPeriod=2023-01")
    bis = {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows if r.get("OBS_VALUE") not in (None, "", "NaN")}
    got = [(p, round(v - bis[p], 2)) for p, v in yoy[-24:] if p in bis]
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= 0.15 else "FAIL", "cpi (BCRP) vs BIS long-run CPI (independent copy)",
        f"{len(got)} months, largest gap {w} pp (tolerance 0.15)")
    imf = {r["TIME_PERIOD"].replace("-M", "-"): float(r["OBS_VALUE"])
           for r in K.csv_rows(K.IMF + "CPI/~/PER.CPI._T.YOY_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2025-M01") if r.get("OBS_VALUE")}
    res("INFO", "cpi (BCRP Lima) minus the IMF's PER CPI y/y, last 6 months (the IMF's is not served)",
        f"{[(p, round(v - imf[p], 2)) for p, v in yoy[-6:] if p in imf]}")


def cross_checks(d):
    K.run("CPI checks", lambda: cpi_checks(d))
    K.run("BCRP checks", lambda: bcrp_checks(d))
    K.run("y/y identity", lambda: K.yoy_identity(d, 0.15))
    K.run("growth vs World Bank", lambda: K.wb_growth_check(d, "PER"))
    K.run("quarters vs World Bank", lambda: K.wb_growth_vs_quarters(d, "PER", 0.3))
    K.run("FX cross-check", lambda: K.fx_vs_bis(d, K.bis_avg("PE", "PEN")))


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else DEFAULT_FILE
    sys.path.insert(0, os.getcwd())
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    K.structure(d, EXPECT, KNOWN_JUMPS, NOT_SERVED, INTERNAL)
    country_checks(d)
    if not offline:
        cross_checks(d)
    K.spot_sheet(d, EXPECT, OFFICIAL)
    K.fx_history_sheet(d, 1, "S/")
    return K.finish()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
