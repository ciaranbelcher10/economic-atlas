"""Pre-launch audit of data-hk.json (v1.7.56, full page). GDP from the
Census and Statistics Department's own table 310-31001, CPI and goods trade
from the IMF, the base rate from BIS, FX from FRED (the linked rate).
Nothing about Hong Kong is shown to users until this passes on a file
written by the real pipeline.

    python3 tools/audit_hk.py                 # data-hk.json, with cross-checks
    python3 tools/audit_hk.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rates   the IMF's published rates vs the change in its own index
  GDP         C&SD's published y/y vs the change in the chained level served;
              World Bank annual growth vs four served quarters
  FX          FRED month end inside the link band; vs the BIS monthly average
  trade       HK$ / BIS rate = the IMF's own US$
Ranges are first estimates from the 13 Oct 2026 probe; resize only with the
publisher's figure in a comment. Exit 1 on any FAIL.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_kit as K
from audit_kit import res

DEFAULT_FILE = "data-hk.json"
EXPECT = {
    "gdp_level": ("HKDm", "quarters", 5e3, 1.2e6, None),       # probe: HK$842bn in Q2 2026; from 1973
    "gdp_real": ("HKDm", "quarters", 5e4, 1.2e6, None),        # probe: HK$824bn (chained 2024 dollars) in Q2 2026
    "gdp_growth": ("%", "quarters", -12, 12, None),            # SA q/q; probe Q2 2026 -0.6%
    "gdp_growth_yoy": ("%", "quarters", -15, 25, None),
    # Step 3.5, not 2.0 (run 1, 13 Oct 2026: 22 moves over 2.0): the headline
    # Composite CPI swings with the government's one-off relief measures (rates
    # waivers, public housing rent waivers, electricity subsidies) as they start
    # and lapse, which is why C&SD also publishes an underlying rate netting
    # them out. Largest move in run 1: +3.5 (January 2021).
    "cpi": ("%", "months", -7, 15, 3.5),
    "cpi_mom": ("%", "months", -5, 5, None),                   # one-off government relief measures move single months
    "policy_rate": ("%", "months", 0, 10, 1.0),                # base rate, from Oct 1998
    "exports": ("HKDm", "months", 5e4, 1.5e6, None),           # probe: US$94bn (about HK$740bn) in June 2026
    "imports": ("HKDm", "months", 5e4, 1.5e6, None),
    "trade_balance": ("HKDm", "months", -3e5, 1.5e5, None),
    "unemployment": ("%", "years", 0.5, 10, 1.5),              # probe: 2.8% (ILO modelled) in 2025
    "debt_gdp": ("%", "years", 0, 40, None),                   # probe: 12.1% in 2025
    "deficit": ("%", "years", -15, 12, None),
    "current_account": ("%", "years", -5, 25, None),
    "fdi": ("%", "years", -20, 80, None),                      # a regional hub: inflows are a large share of GDP
}
KNOWN_JUMPS = {
    ("policy_rate", "2008-01"): "the US Federal Reserve cut its target by 1.25 points in January 2008; the base rate follows it",
    ("policy_rate", "2008-10"): "Fed cuts in October 2008, and the HKMA narrowed the base-rate spread over the Fed target on 9 October 2008",
    ("unemployment", "1998"): "the 1997-98 Asian financial crisis",
    ("unemployment", "1999"): "the 1997-98 Asian financial crisis",
    ("unemployment", "2002"): "the 2001-02 downturn",
    ("unemployment", "2009"): "the 2008-09 global financial crisis",
    ("unemployment", "2020"): "the 2020 pandemic",
}
NOT_SERVED = {"bond_yield_10y": "not wired", "business_confidence": "no OECD coverage", "ecb_rate": "not a euro member"}
OFFICIAL = {
    "gdp_level": "C&SD GDP release (table 310-31001)", "gdp_real": "C&SD, chained (2024) dollars",
    "gdp_growth": "C&SD, seasonally adjusted q/q", "gdp_growth_yoy": "C&SD advance or revised estimate, y/y",
    "cpi": "C&SD Composite CPI, y/y", "cpi_mom": "C&SD Composite CPI, m/m", "policy_rate": "HKMA base rate",
    "exports": "C&SD external trade (HK$; IMF US$ converted here)", "imports": "C&SD external trade",
    "trade_balance": "C&SD balance", "unemployment": "ILO modelled estimate (World Bank)",
    "debt_gdp": "IMF WEO", "deficit": "IMF WEO", "current_account": "World Bank", "fdi": "World Bank",
}
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Egypt|Nigeria|Vietnam|Peru|\bsoles\b"


def country_checks(d):
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    linked = [p for p in hist if p[0] >= "1984"]
    out = [p for p in linked if not 7.7 <= p[1] <= 7.9]
    monthly = bool(hist) and all(len(str(p)) == 7 for p, _ in hist)
    res("PASS" if monthly else "FAIL", "fx_to_usd history is monthly (FRED DEXHKUS, not the World Bank fallback)",
        f"history {hist[0][0] if hist else None}..{hist[-1][0] if hist else None}: run fetch_hk.py with FRED_API_KEY set")
    ok = bool(fx.get("pair") == "HKD/USD" and fx.get("direction") == "divide" and hist
              and fx.get("rate") == hist[-1][1] and linked and not out and "floor" not in fx)
    res("PASS" if ok else "FAIL", "fx_to_usd block (HK$ per US$, monthly, divide, inside 7.7-7.9 since 1984, no floor)",
        f"{fx.get('rate')} as of {fx.get('as_of')}; {len(out)} month(s) outside the band {out[:3]}")
    K.one_decimal(d, ("cpi", "cpi_mom", "gdp_growth", "gdp_growth_yoy"))
    s = d["series"]
    lv, rl = s.get("gdp_level", {}).get("points", []), s.get("gdp_real", {}).get("points", [])
    if lv and rl:
        res("PASS" if lv[-1][0] == rl[-1][0] else "FAIL", "nominal and real GDP end in the same quarter",
            f"{lv[-1][0]} / {rl[-1][0]}")
        ratio = rl[-1][1] / lv[-1][1]
        res("PASS" if 0.85 < ratio < 1.1 else "FAIL", "real (chained 2024) and nominal GDP within 15% of each other lately",
            f"real/nominal {ratio:.3f} at {lv[-1][0]} (the reference year is 2024, so they should be close)")


def fx_bis_check(d):
    bis = K.bis_avg("HK", "HKD")
    fred = dict(d["fx_to_usd"]["history"])
    got = [(p, round(fred[p] / v * 100 - 100, 3)) for p, v in bis.items() if p in fred and p >= "2020"]
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= 0.5 else "FAIL", "FX: FRED month end vs BIS monthly average",
        f"{len(got)} months, largest gap {w} % (tolerance 0.5)")


def cross_checks(d):
    K.run("CPI index check", lambda: K.cpi_index_check(d, "HKG"))
    K.run("y/y identity", lambda: K.yoy_identity(d, 0.15))
    K.run("quarters vs World Bank", lambda: K.wb_growth_vs_quarters(d, "HKG", 0.3))
    K.run("FX cross-check", lambda: fx_bis_check(d))
    K.run("trade check", lambda: K.trade_vs_usd(d, K.itg_usd("HKG"), K.bis_avg("HK", "HKD"), 0.1))


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
    K.fx_history_sheet(d, 1, "HK$")
    return K.finish()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
