"""Pre-launch audit of data-pk.json (v1.7.56, partial-coverage page, the
Egypt pattern). CPI and goods trade are monthly via the IMF, GDP and
unemployment are World Bank annual, and there is no policy rate (no
machine-readable source answered the 13 Oct 2026 probes). Nothing about
Pakistan is shown to users until this passes on a file written by the real
pipeline.

    python3 tools/audit_pk.py                 # data-pk.json, with cross-checks
    python3 tools/audit_pk.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rates   the IMF's published y/y and m/m vs the change in its own index
  growth      World Bank published real growth vs the change in real GDP served
  FX          World Bank annual vs the mean of BIS monthly averages
  trade       the IMF's own published y/y change vs the change in the rupee
              levels served (Pakistan's ITG has no US$ series to divide by)
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

DEFAULT_FILE = "data-pk.json"
EXPECT = {
    "gdp_level": ("PKRm", "years", 1e3, 3e8, None),            # probe: PKR 113.8tn (1.14e8 m) in 2025
    "gdp_real": ("PKRm", "years", 1e5, 1e8, None),             # probe: PKR 43.6tn in 2025
    "gdp_growth": ("%", "years", -5, 15, None),
    "cpi": ("%", "months", -5, 45, 3.0),                        # May 2023 peak near 38%
    "cpi_mom": ("%", "months", -5, 12, None),
    "exports": ("PKRm", "months", 1e3, 2e6, None),              # probe: PKR 624bn in June 2026
    "imports": ("PKRm", "months", 1e3, 4e6, None),              # probe: PKR 1.92tn in June 2026
    "trade_balance": ("PKRm", "months", -3e6, 2e5, None),
    "unemployment": ("%", "years", 1.5, 12, 1.5),               # from 2012; 1.8% in 2014 (run 4); 5.4% in 2025
    "debt_gdp": ("%", "years", 40, 110, None),                  # probe: 72.8% in 2025
    "deficit": ("%", "years", -12, 3, None),                    # probe: -5.4% in 2025
    "current_account": ("%", "years", -12, 8, None),
    "fdi": ("%", "years", -1, 6, None),
}
KNOWN_JUMPS = {
    # Run 1 (13 Oct 2026). All in PBS's national y/y rate (IMF CPI).
    **{("cpi", p): "fuel price rises after the fuel subsidy ended (May-June 2022)" for p in ("2022-06", "2022-07")},
    ("cpi", "2022-09"): "the government waived the fuel-cost adjustment on September 2022 electricity bills",
    ("cpi", "2022-10"): "rebound after the September 2022 electricity waiver",
    **{("cpi", p): "rupee devaluation of January 2023 and price rises under the 2023 IMF programme" for p in ("2023-01", "2023-02", "2023-03")},
    ("cpi", "2023-06"): "base effect: June 2022's fuel price rises dropped out (y/y peaked near 38% in May 2023)",
    ("cpi", "2023-09"): "petrol and electricity price rises in August-September 2023",
    ("cpi", "2023-10"): "petrol price cuts in October 2023, and base effects",
    **{("cpi", p): "base effect: the early-2023 surge dropping out of the twelve-month comparison" for p in ("2024-02", "2024-04", "2024-05")},
    ("cpi", "2025-05"): "base effect after the 0.3% low of April 2025",
    ("cpi", "2026-04"): "PBS: 7.3% in March to 10.9% in April 2026, mainly higher domestic petroleum prices after crude oil rose",
    ("unemployment", "2015"): "swings in the ILO modelled estimate",
}
NOT_SERVED = {"policy_rate": "SBP EasyData answers 525; no BIS or IMF copy (13 Oct 2026 probes)",
              "bond_yield_10y": "no free series", "business_confidence": "no OECD coverage", "ecb_rate": "not a euro member"}
OFFICIAL = {
    "cpi": "PBS monthly CPI release, national y/y", "cpi_mom": "PBS monthly release, m/m",
    "exports": "PBS external trade release (rupees)", "imports": "PBS external trade release", "trade_balance": "PBS balance",
    "gdp_level": "PBS national accounts (via World Bank, fiscal years)", "gdp_real": "via World Bank", "gdp_growth": "annual real growth",
    "unemployment": "ILO modelled estimate (World Bank)", "debt_gdp": "IMF WEO", "deficit": "IMF WEO",
    "current_account": "World Bank", "fdi": "World Bank",
}
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Egypt|Nigeria|Vietnam|\bpounds?\b|naira"


def country_checks(d):
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    ok = bool(fx.get("pair") == "PKR/USD" and fx.get("direction") == "divide" and 50 < (fx.get("rate") or 0) < 600
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (rupees per US$, annual, divide: fx_config.ANNUAL)",
        f"{fx.get('rate')} as of {fx.get('as_of')}, floor {fx.get('floor')}")
    K.one_decimal(d, ("cpi", "cpi_mom"))
    tb = d["series"].get("trade_balance", {}).get("points", [])
    surplus = [p for p, v in tb if v > 0]
    res("INFO", "goods surplus months (Pakistan has run a goods deficit in almost every month since 2003)",
        f"{surplus[-6:] or 'none'}")


def trade_yoy_check(d):
    """The IMF's published y/y change in rupee exports and imports vs the
    change in the levels served: catches a scaling or unit slip."""
    pub = {}
    for r in K.csv_rows(K.IMF + "ITG/~/PAK.*.*.M?c[TIME_PERIOD]=ge:2024-M01"):
        if r.get("TYPE_OF_TRANSFORMATION") in ("FOB_YOY_PCH_PT", "CIF_YOY_PCH_PT") and r.get("OBS_VALUE"):
            pub[(r["INDICATOR"], r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"])
    rows = []
    for k, ind in (("exports", "XG"), ("imports", "MG")):
        lv = dict(d["series"][k]["points"])
        for p in list(lv)[-6:]:
            b = K.back(p, 12)
            if (ind, p) in pub and b in lv:
                rows.append((k, p, round((lv[p] / lv[b] - 1) * 100 - pub[(ind, p)], 2)))
    w = K.worst(rows)
    res("PASS" if rows and abs(w[2]) <= 0.2 else "FAIL", "Trade: IMF published y/y vs change in the rupee levels served",
        f"{len(rows)} comparisons, largest gap {w} pp (tolerance 0.2)")


def cross_checks(d):
    K.run("CPI index check", lambda: K.cpi_index_check(d, "PAK"))
    K.run("growth check", lambda: K.wb_growth_check(d, "PAK"))
    K.run("FX cross-check", lambda: K.fx_vs_bis(d, K.bis_avg("PK", "PKR")))
    K.run("trade check", lambda: trade_yoy_check(d))


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else DEFAULT_FILE
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    K.structure(d, EXPECT, KNOWN_JUMPS, NOT_SERVED, INTERNAL)
    country_checks(d)
    if not offline:
        cross_checks(d)
    K.spot_sheet(d, EXPECT, OFFICIAL)
    K.fx_history_sheet(d, 100, "Rs")
    return K.finish()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
