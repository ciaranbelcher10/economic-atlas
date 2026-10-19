"""Pre-launch audit of data-is.json (v1.7.56, full page, an OECD member).
GDP, CPI and unemployment are Statistics Iceland's figures as the OECD
republishes them, the key rate is from BIS, goods trade from Statistics
Iceland's own table UTA06001 from 2011 (the IMF, converted at the BIS rate,
before it), FX from the World Bank (annual). Nothing about Iceland is shown to users until
this passes on a file written by the real pipeline.

    python3 tools/audit_is.py                 # data-is.json, with cross-checks
    python3 tools/audit_is.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI         our rates (from the OECD index) vs the OECD's own published
              rates, and vs BIS's independent long-run CPI
  GDP         the OECD's q/q and y/y vs the change in the real level served
  FX          World Bank annual vs the mean of BIS monthly averages
  trade       2011 on: every served month equals Statistics Iceland's UTA06001
              (an independent pull, not fetch_is); before 2011: krónur / BIS rate
              = the IMF's own US$
Ranges are first estimates from the 13 Oct 2026 probe; resize only with the
publisher's figure in a comment. Exit 1 on any FAIL. Note the OECD answers
only in fetch_is.py's oecd_turn hour; the audit itself calls the OECD once.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_kit as K
from audit_kit import res

DEFAULT_FILE = "data-is.json"
OECD_CPI = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/"
            "ISL.M..CPI.._T..?format=csvfile&startPeriod=2024-01")
EXPECT = {
    "gdp_level": ("ISKm", "quarters", 5e4, 2e6, None),         # probe: ISK 1.29tn (SA) in Q2 2026; from 1995
    "gdp_real": ("ISKm", "quarters", 2e5, 1.5e6, None),        # probe: ISK 903bn (chain-linked) in Q2 2026
    "gdp_growth": ("%", "quarters", -15, 15, None),            # probe: Q2 2026 -3.0% (SA q/q)
    "gdp_growth_yoy": ("%", "quarters", -15, 15, None),
    "cpi": ("%", "months", -3, 100, None),                     # the OECD index may reach back to the 1980s (over 80%)
    "cpi_mom": ("%", "months", -3, 20, None),
    "unemployment": ("%", "months", 1, 12, 1.5),               # SA, from 2003; 2009-10 near 9%
    "policy_rate": ("%", "months", 0, 12, 1.0),                # from June 2014; probe 8.0% (Sep 2026)
    "exports": ("ISKm", "months", 5e3, 2.5e5, None),           # probe: US$780m (about ISK 94bn) in June 2026
    "imports": ("ISKm", "months", 5e3, 3e5, None),
    "trade_balance": ("ISKm", "months", -1.5e5, 8e4, None),
    "debt_gdp": ("%", "years", 15, 140, None),                 # WEO: 121.1% in 2013 after the 2008 bank collapse
    "deficit": ("%", "years", -20, 15, None),                  # WEO: +12.7% in 2016 (stability contributions from the failed banks' estates)
    "current_account": ("%", "years", -30, 15, None),          # 2006-08 near -20%
    "fdi": ("%", "years", -150, 150, None),                    # holding-company flows swing wildly
}
# v1.8.19: no known gaps. 2013-03, 2013-04 and 2026-01 were once left out as "copied IMF figures";
# Statistics Iceland shows real, unequal exports and imports in all three, and they are served.
KNOWN_GAPS = {}
PX_URL = ("https://px.hagstofa.is/pxen/api/v1/en/Efnahagur/utanrikisverslun/"
          "1_voruvidskipti/01_voruskipti/UTA06001.px")
SI_START = "2011-01"
KNOWN_JUMPS = {
    # Run 2 (13 Oct 2026): 2.9 (Jun) -> 4.5 (Jul), then 4.7, 4.9, 5.1, 5.5 to
    # November: a level shift that held, not a one-month survey blip.
    ("unemployment", "2008-07"): "the 2008 downturn: unemployment rose every month from July to the October banking collapse and after",
    ("policy_rate", "2023-05"): "the Central Bank of Iceland raised its key rate by 1.25 points on 24 May 2023",
}
NOT_SERVED = {"bond_yield_10y": "the OECD's IRLT for Iceland stops in August 2022",
              "business_confidence": "no OECD BCICP for Iceland", "ecb_rate": "not a euro member",
              "cpi_qoq": "Iceland's CPI is monthly"}
OFFICIAL = {
    "gdp_level": "Statistics Iceland quarterly national accounts", "gdp_real": "Statistics Iceland, volume",
    "gdp_growth": "Statistics Iceland, SA q/q", "gdp_growth_yoy": "Statistics Iceland, y/y",
    "cpi": "Statistics Iceland monthly CPI release, y/y", "cpi_mom": "Statistics Iceland CPI, m/m",
    "unemployment": "Statistics Iceland labour force survey, SA", "policy_rate": "Central Bank of Iceland key rate",
    "exports": "Statistics Iceland external trade UTA06001 (ISK, from 2011; IMF US$ converted before)", "imports": "Statistics Iceland external trade UTA06001",
    "trade_balance": "Statistics Iceland balance", "debt_gdp": "IMF WEO", "deficit": "IMF WEO",
    "current_account": "World Bank", "fdi": "World Bank",
}
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Zealand|Stats NZ|Peru|\bOCR\b"


def country_checks(d):
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    ok = bool(fx.get("pair") == "ISK/USD" and fx.get("direction") == "divide" and 40 < (fx.get("rate") or 0) < 250
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (krónur per US$, annual, divide: fx_config.ANNUAL)",
        f"{fx.get('rate')} as of {fx.get('as_of')}, floor {fx.get('floor')}")
    K.one_decimal(d, ("cpi", "cpi_mom", "gdp_growth", "gdp_growth_yoy", "unemployment"))
    pr = d["series"].get("policy_rate", {}).get("points", [])
    res("PASS" if pr and pr[0][0] == "2014-06" else "FAIL", "policy_rate starts June 2014 (one measure throughout)",
        pr[0][0] if pr else "missing")


def oecd_cpi_check(d):
    pub = {}
    for r in K.csv_rows(OECD_CPI):
        if r.get("METHODOLOGY") == "N" and r.get("OBS_VALUE"):
            key = {"GY": "cpi", "G1": "cpi_mom"}.get(r.get("TRANSFORMATION"))
            if key:
                pub[(key, r["TIME_PERIOD"])] = float(r["OBS_VALUE"])
    for key in ("cpi", "cpi_mom"):
        got = [(p, round(v - pub[(key, p)], 2)) for p, v in d["series"][key]["points"][-24:] if (key, p) in pub]
        w = K.worst(got)
        res("PASS" if got and abs(w[1]) <= 0.1 else "FAIL", f"{key} vs the OECD's own published national CPI rate",
            f"{len(got)} months, largest gap {w} pp (tolerance 0.1)")


def bis_cpi_check(d):
    rows = K.csv_rows("https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M.IS.771?format=csv&startPeriod=2020-01")
    bis = {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows if r.get("OBS_VALUE") not in (None, "", "NaN")}
    got = [(p, round(v - bis[p], 2)) for p, v in d["series"]["cpi"]["points"][-24:] if p in bis]
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= 0.15 else "FAIL", "cpi vs BIS long-run CPI (independent copy)",
        f"{len(got)} months, largest gap {w} pp (tolerance 0.15)")


def qoq_identity(d, tol):
    s = d["series"]
    real = dict(s["gdp_real"]["points"])
    got = [(p, round(v - (real[p] / real[K.back(p, 1)] - 1) * 100, 2)) for p, v in s["gdp_growth"]["points"]
           if p in real and K.back(p, 1) in real][-20:]
    w = K.worst(got)
    res("PASS" if got and abs(w[1]) <= tol else "FAIL", "gdp_growth (q/q) vs change in served real GDP",
        f"{len(got)} quarters, largest gap {w} pp (tolerance {tol})")


def issuer_trade():
    """Statistics Iceland UTA06001 pulled independently of fetch_is: rows chosen by their text."""
    import requests
    meta = requests.get(PX_URL, timeout=60, headers=K.UA).json()
    tv = next(v for v in meta["variables"] if v.get("time"))
    pv = next(v for v in meta["variables"] if not v.get("time"))
    want = {"exports": "exports fob, total", "imports": "imports cif, total"}
    codes = {k: next(c for c, t in zip(pv["values"], pv["valueTexts"]) if t.strip().lower() == txt) for k, txt in want.items()}
    q = {"query": [{"code": pv["code"], "selection": {"filter": "item", "values": list(codes.values())}},
                   {"code": tv["code"], "selection": {"filter": "item", "values": tv["values"]}}],
         "response": {"format": "json-stat2"}}
    js = requests.post(PX_URL, json=q, timeout=120, headers=K.UA).json()
    n = len(tv["values"])
    out = {}
    for row, key in enumerate(codes):
        out[key] = {tv["values"][j].replace("M", "-"): js["value"][row * n + j] for j in range(n)
                    if js["value"][row * n + j] is not None}
    return out


def tail_vs_issuer(d):
    src, rows, missing = issuer_trade(), [], []
    for key in ("exports", "imports"):
        for p, v in d["series"][key]["points"]:
            if p >= SI_START:
                if p in src[key]:
                    rows.append((key, p, round(v - src[key][p], 2)))
                else:
                    missing.append((key, p))
    bad = [r for r in rows if abs(r[2]) > 0.05]
    last = max(src["exports"])
    served = d["series"]["exports"]["points"][-1][0]
    res("PASS" if rows and not bad and not missing else "FAIL",
        "Trade 2011 on: every served month equals Statistics Iceland's UTA06001 (krónur million)",
        f"{len(rows)} months compared, {len(bad)} differ (largest {K.worst(rows)}), {len(missing)} not at the issuer")
    res("PASS" if served >= last or K.back(last, 1) == served else "FAIL",
        "Trade ends at the issuer's last month (or one before it)", f"served to {served}, issuer to {last}")


def head_vs_imf(d):
    """Before 2011 the series is the IMF's US$ at BIS's monthly average rate."""
    rate = K.bis_avg("IS", "ISK")
    usd = {}
    for r in K.csv_rows(K.IMF + f"ITG/~/ISL.*.*.M?c[TIME_PERIOD]=ge:2006-M01"):
        if r.get("UNIT") == "USD" and r.get("OBS_VALUE") and (r.get("INDICATOR"), r.get("VALUATION")) in (("XG", "FOB"), ("MG", "CIF")):
            usd[(r["INDICATOR"], r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
    rows = []
    for key, ind in (("exports", "XG"), ("imports", "MG")):
        for p, v in d["series"][key]["points"]:
            if p < SI_START and (ind, p) in usd and p in rate:
                rows.append((key, p, round(v / rate[p] / usd[(ind, p)] * 100 - 100, 4)))
    w = K.worst(rows)
    res("PASS" if rows and abs(w[2]) <= 0.01 else "FAIL", "Trade before 2011: krónur / BIS rate = the IMF's own US$",
        f"{len(rows)} comparisons, largest gap {w} % (tolerance 0.01)")


def cross_checks(d):
    K.run("OECD CPI check", lambda: oecd_cpi_check(d))
    K.run("BIS CPI check", lambda: bis_cpi_check(d))
    K.run("q/q identity", lambda: qoq_identity(d, 0.15))
    K.run("y/y identity", lambda: K.yoy_identity(d, 0.15))
    K.run("FX cross-check", lambda: K.fx_vs_bis(d, K.bis_avg("IS", "ISK")))
    K.run("trade 2011 on vs the issuer", lambda: tail_vs_issuer(d))
    K.run("trade before 2011 vs the IMF", lambda: head_vs_imf(d))


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else DEFAULT_FILE
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    K.structure(d, EXPECT, KNOWN_JUMPS, NOT_SERVED, INTERNAL, KNOWN_GAPS)
    country_checks(d)
    if not offline:
        cross_checks(d)
    K.spot_sheet(d, EXPECT, OFFICIAL)
    K.fx_history_sheet(d, 100, "kr")
    return K.finish()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
