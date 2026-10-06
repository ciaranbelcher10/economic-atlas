"""Pre-launch audit of data-my.json. Nothing about Malaysia is shown to users
until this passes on a file written by the real pipeline, and Ciaran's
spot-check against DOSM's releases matches.

    python3 tools/audit_my.py                 # data-my.json, with cross-checks
    python3 tools/audit_my.py --offline FILE  # structure and plausibility only

Same three layers as tools/audit_cn.py, with cross-checks chosen for
Malaysia's sources (national first, so every check is against a DIFFERENT
publisher or a different DOSM table):
  CPI index   DOSM all-items index vs BIS long CPI index (WS_LONG_CPI, 628)
  CPI rate    DOSM YoY vs BIS long CPI YoY (WS_LONG_CPI, 771)
  CPI MoM     if derived from the index: must equal the rate DOSM
              publishes; checked by re-deriving from cpi_headline AND by
              matching cpi_headline_inflation when that table is served
  GDP         four DOSM quarters vs World Bank annual nominal GDP
  real GDP    YoY from DOSM's real levels vs DOSM's published YoY
  q/q basis   the label's "seasonally adjusted" claim tested against the
              raw levels (a q/q rate that equals the change in the raw
              level is NOT seasonally adjusted)
  trade       DOSM ringgit vs IMF ITG dollars at each month's rate
  OPR         latest BIS value vs Bank Negara's own API; series starts at
              the OPR (May 2004) with no earlier spliced measure
  labour      monthly DOSM unemployment (annual mean) vs World Bank ILO
  FX          FRED month-end mean vs World Bank annual average; latest vs
              Bank Negara's mid rate
Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None)
    "gdp_level": ("MYRm", "quarters", 2e4, 1.5e6, None),      # Q1 2000 was about RM 85bn
    "gdp_real": ("MYRm", "quarters", 5e4, 1.2e6, None),
    "gdp_growth": ("%", "quarters", -20, 20, None),
    "gdp_growth_yoy": ("%", "quarters", -25, 25, None),
    "cpi": ("%", "months", -5, 15, 3.0),
    "cpi_mom": ("%", "months", -3, 4, None),
    "policy_rate": ("%", "months", 1, 5, 0.75),                 # OPR has stayed inside 1.75..3.5
    "unemployment": ("%", "months", 1, 8, 1.5),                 # 5.3% in May 2020 was the record
    "participation": ("%", "months", 55, 80, 2.0),
    "employment": ("%", "months", 50, 80, 2.5),
    "exports": ("MYRm", "months", 1e3, 4e5, None),
    "imports": ("MYRm", "months", 1e3, 4e5, None),
    "trade_balance": ("MYRm", "months", -1e5, 1e5, None),
    "debt_gdp": ("%", "years", 10, 150, None),
    "deficit": ("%", "years", -15, 10, None),
    "current_account": ("%", "years", -15, 25, None),
    "fdi": ("%", "years", -5, 15, None),
}
# Jumps over a series' step limit that are real and explained; anything else fails.
KNOWN_JUMPS = {
    ("cpi", "2009-06"): "base effect: Malaysia raised fuel prices about 40% in June 2008",
}
NOT_SERVED = {"bond_yield_10y": "IMF S13BOND does not state its maturity",
              "business_confidence": "no OECD coverage; DOSM's survey is a different measure"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "DOSM quarterly GDP release (dosm.gov.my), GDP at current prices, RM million",
    "gdp_real": "DOSM quarterly GDP release, GDP at constant prices",
    "gdp_growth": "DOSM quarterly GDP release, q-o-q seasonally adjusted (the 'seasonally adjusted' figure, not the raw q-o-q)",
    "gdp_growth_yoy": "DOSM quarterly GDP release, y-o-y (the headline figure)",
    "cpi": "DOSM monthly CPI release, y-o-y",
    "cpi_mom": "DOSM monthly CPI release, m-o-m",
    "policy_rate": "Bank Negara Malaysia Monetary Policy Statement (OPR level)",
    "unemployment": "DOSM monthly Labour Force Statistics, unemployment rate (seasonally adjusted)",
    "participation": "DOSM monthly Labour Force Statistics, LFPR (seasonally adjusted)",
    "employment": "DOSM monthly Labour Force Statistics, employment-to-population ratio",
    "exports": "DOSM monthly Malaysia External Trade Statistics, total exports (RM)",
    "imports": "DOSM monthly Malaysia External Trade Statistics, total imports (RM)",
    "trade_balance": "DOSM monthly Malaysia External Trade Statistics, trade balance (RM)",
}
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
RESULTS = []


def res(status, name, detail=""):
    RESULTS.append((status, name, detail))
    print(f"{status:<5} {name}  {detail}")


def period_key(p):
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m: return int(m.group(1)) * 12 + int(m.group(2)) - 1
    m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
    if m: return int(m.group(1)) * 4 + int(m.group(2)) - 1
    if re.fullmatch(r"\d{4}", p): return int(p)
    return None


def period_end(p):
    k = period_key(p)
    if re.fullmatch(r"\d{4}-\d{2}", p): y, m = divmod(k + 1, 12); return datetime(y, m + 1, 1, tzinfo=timezone.utc)
    if "Q" in p: y, q = divmod(k + 1, 4); return datetime(y, q * 3 + 1, 1, tzinfo=timezone.utc)
    return datetime(int(p) + 1, 1, 1, tzinfo=timezone.utc)


def pct(points, lag, dp=1):
    return {points[i][0]: round((points[i][1] / points[i - lag][1] - 1) * 100, dp)
            for i in range(lag, len(points)) if points[i - lag][1]}


def worst(rows, i=-1):
    return max(rows, key=lambda x: abs(x[i])) if rows else None


def structure_and_plausibility(d):
    s = d.get("series", {})
    for key, why in NOT_SERVED.items():
        res("FAIL" if key in s else "PASS", f"{key} not served", why if key not in s else "served: must not be")
    for key, (unit, freq, lo, hi, step) in EXPECT.items():
        ser = s.get(key)
        if not ser:
            res("FAIL", f"{key} present"); continue
        pts = ser.get("points") or []
        problems = []
        if ser.get("unit") != unit: problems.append(f"unit {ser.get('unit')} != {unit}")
        if ser.get("freq") != freq: problems.append(f"freq {ser.get('freq')} != {freq}")
        if not ser.get("label") or re.search(r"confirmed|placeholder|inferred|probe|todo", ser["label"], re.I):
            problems.append("label missing or carries internal wording")
        if re.search("\u2014| -- ", ser.get("label", "")): problems.append("dash in label")
        keys = [period_key(str(p)) for p, _ in pts]
        if None in keys: problems.append("unparseable period")
        elif keys != sorted(set(keys)): problems.append("periods not ascending and unique")
        else:
            gaps = [pts[i][0] for i in range(1, len(keys)) if keys[i] - keys[i - 1] != 1]
            if gaps: problems.append(f"{len(gaps)} gap(s), first before {gaps[0]}")
        nulls = [p for p, v in pts if not isinstance(v, (int, float))]
        if nulls: problems.append(f"non-numeric at {nulls[0]}")
        out = [(p, v) for p, v in pts if isinstance(v, (int, float)) and not lo <= v <= hi]
        if out: problems.append(f"{len(out)} value(s) outside {lo}..{hi}, e.g. {out[-1]}")
        if step:
            jumps = [(pts[i][0], round(pts[i][1] - pts[i - 1][1], 2)) for i in range(1, len(pts))
                     if abs(pts[i][1] - pts[i - 1][1]) > step and (key, pts[i][0]) not in KNOWN_JUMPS]
            if jumps: problems.append(f"jump over {step} at {jumps[-1]}")
        if len(pts) < {"months": 24, "quarters": 12, "years": 10}[freq]:
            problems.append(f"only {len(pts)} points")
        if pts and (datetime.now(timezone.utc) - period_end(pts[-1][0])).days > MAX_AGE[freq]:
            problems.append(f"stale: ends {pts[-1][0]}")
        res("FAIL" if problems else "PASS", f"{key} structure and range",
            "; ".join(problems) or f"{len(pts)} pts {pts[0][0]}..{pts[-1][0]}, last {pts[-1][1]}")
    tb, ex, im = (dict(s.get(k, {}).get("points", [])) for k in ("trade_balance", "exports", "imports"))
    bad = [p for p, v in tb.items() if p in ex and p in im and abs(ex[p] - im[p] - v) > 0.2]
    res("FAIL" if bad else "PASS", "trade balance = exports - imports", f"{len(bad)} mismatched month(s)")
    pr = s.get("policy_rate", {}).get("points", [])
    res("PASS" if pr and pr[0][0] >= "2004-05" else "FAIL", "policy rate is the OPR only (no spliced earlier measure)",
        f"starts {pr[0][0] if pr else None}")
    # The OPR began at 2.70% (2004) and moved by 10bp steps until 2006; 25bp since.
    odd = [(p, v) for p, v in pr if p >= "2007-01" and round(v * 100) % 25]
    res("FAIL" if odd else "PASS", "OPR moves in 25bp steps since 2007", f"{odd[:2]}")
    fx = d.get("fx_to_usd") or {}
    fx_ok = fx.get("pair") == "MYR/USD" and fx.get("direction") == "divide" and 3 < (fx.get("rate") or 0) < 6
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block", f"{fx.get('rate')} as of {fx.get('as_of')}")
    # A derived CPI rate must reproduce DOSM's one-decimal rates from DOSM's index; the
    # structural check here is that both rates carry one decimal place, like DOSM's.
    for k in ("cpi", "cpi_mom"):
        many = [v for _, v in s.get(k, {}).get("points", [])[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{k} at DOSM's one decimal place", f"{len(many)} value(s) with more")


# ------------------------------------------------------------ cross-checks
def cross_checks(d):
    import requests
    s = d["series"]

    def get(url, accept=None):
        h = dict(UA)
        if accept: h["Accept"] = accept
        r = requests.get(url, timeout=90, headers=h)
        r.raise_for_status()
        return r

    def wb(code):
        j = get(f"https://api.worldbank.org/v2/country/MYS/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def bis_long_cpi(unit):
        rows = csv.DictReader(io.StringIO(get(
            "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M.MY.*?format=csv&startPeriod=2015-01",
            "text/csv").text))
        return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows
                if r.get("UNIT_MEASURE") == unit and r.get("OBS_VALUE") not in (None, "", "NaN")}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def cpi_index():
        import fetch_my
        ix = dict(fetch_my.fetch_cpi_index())
        bis = bis_long_cpi("628")
        rows = [(p, round(ix[p] - v, 2)) for p, v in sorted(bis.items())[-36:] if p in ix]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.2 else "FAIL", "CPI index: DOSM vs BIS long CPI, last 36 months",
            f"{len(rows)} months, largest gap {w} (tolerance 0.2 index points)")

    def cpi_rate():
        bis = bis_long_cpi("771")
        rows = [(p, round(v - bis[p], 2)) for p, v in s["cpi"]["points"][-36:] if p in bis]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.1 else "FAIL", "CPI YoY: site vs BIS long CPI YoY, last 36 months",
            f"{len(rows)} months, largest gap {w} pp (tolerance 0.1: BIS keeps more decimals)")

    def cpi_derivation():
        import fetch_my
        ix = fetch_my.fetch_cpi_index()
        for key, lag in (("cpi", 12), ("cpi_mom", 1)):
            der = pct(ix, lag)
            rows = [(p, round(v - der[p], 2)) for p, v in s[key]["points"][-36:] if p in der]
            w = worst(rows)
            res("PASS" if rows and abs(w[1]) <= 0.05 else "FAIL",
                f"{key}: equals the rate implied by DOSM's own index, last 36 months",
                f"{len(rows)} months, largest gap {w} pp (must be 0 at one decimal)")
        try:
            rows = fetch_my.dosm("cpi_headline_inflation")
            for key, field in (("cpi", "inflation_yoy"), ("cpi_mom", "inflation_mom")):
                pub = dict(fetch_my.pts_from(rows, field, division="overall"))
                diff = [(p, round(v - pub[p], 2)) for p, v in s[key]["points"][-36:] if p in pub]
                w = worst(diff)
                res("PASS" if diff and abs(w[1]) <= 0.05 else "FAIL", f"{key}: equals DOSM's published rate",
                    f"{len(diff)} months, largest gap {w} pp")
        except Exception as exc:
            res("INFO", "DOSM published CPI rates table", f"not served ({exc}); the spot-check sheet is the check")

    def gdp():
        ann = wb("NY.GDP.MKTP.CN")
        q = dict(s["gdp_level"]["points"])
        rows = []
        for y in sorted(ann)[-6:]:
            qs = [q.get(f"{y}-Q{i}") for i in range(1, 5)]
            if None not in qs:
                rows.append((y, round(sum(qs) / (ann[y] / 1e6) * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 2.0 else "FAIL", "GDP: four DOSM quarters vs World Bank annual",
            f"{len(rows)} years, largest gap {w} % (tolerance 2)")

    def real_yoy():
        der = pct(s["gdp_real"]["points"], 4)
        rows = [(p, round(v - der[p], 2)) for p, v in s["gdp_growth_yoy"]["points"][-16:] if p in der]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "Real GDP YoY: published vs implied by real levels",
            f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.15, rounding)")

    def qoq_derivation():
        import fetch_my
        lvl = fetch_my.pts_from(fetch_my.dosm("gdp_qtr_real_sa"), "value", fetch_my.quarter_of, series="abs")
        der = pct(lvl, 1)
        rows = [(p, round(v - der[p], 2)) for p, v in s["gdp_growth"]["points"][-16:] if p in der]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.05 else "FAIL", "GDP q/q: equals the change in DOSM's seasonally adjusted real GDP",
            f"{len(rows)} quarters, largest gap {w} pp")

    def qoq_label():
        import fetch_my
        basis = fetch_my.qoq_basis(s["gdp_growth"]["points"], s["gdp_real"]["points"])
        lab = s["gdp_growth"]["label"]
        claims_sa = "not seasonally adjusted" not in lab and "seasonally adjusted" in lab
        ok = (basis == "sa") == claims_sa and basis != "unknown"
        res("PASS" if ok else "FAIL", "GDP q/q: label's adjustment claim matches the data",
            f"data says {basis}; label: {lab}")

    def trade():
        hist = dict(d["fx_to_usd"]["history"])
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/MYS.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        if not any(re.fullmatch(r"\d{4}-\d{2}", p) for p in hist):
            res("FAIL", "Trade: DOSM ringgit vs IMF dollars at each month's rate",
                "could not run: no monthly FX history (FRED key missing, World Bank annual fallback in use)")
            return
        rows = []
        for k, ind in (("exports", "XG"), ("imports", "MG")):
            for p, v in s[k]["points"][-12:]:
                if (ind, p) in usd and p in hist:
                    rows.append((k, p, round(v / hist[p] / usd[(ind, p)] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[2]) <= 3.0 else "FAIL", "Trade: DOSM ringgit vs IMF dollars at each month's rate",
            f"{len(rows)} comparisons, largest gap {w} % (tolerance 3: month-end vs average rate)")

    def opr():
        j = get("https://api.bnm.gov.my/public/opr", "application/vnd.BNM.API.v1+json").json()
        bnm = float(j["data"]["new_opr_level"])
        last = s["policy_rate"]["points"][-1]
        same = abs(last[1] - bnm) < 1e-6
        res("PASS" if same else "FAIL", "OPR: latest BIS value equals Bank Negara API",
            f"site {last}, BNM {bnm} set {j['data']['date']}"
            + ("" if same else "; if BNM's decision is dated after the BIS month, rerun after BIS updates"))

    def labour():
        ann = wb("SL.UEM.TOTL.ZS")
        m = s["unemployment"]["points"]
        rows = []
        for y in sorted(ann)[-6:]:
            ms = [v for p, v in m if p.startswith(f"{y}-")]
            if len(ms) == 12:
                rows.append((y, round(sum(ms) / 12 - ann[y], 2)))
        w = worst(rows)
        # The World Bank figure is the ILO's MODELLED estimate, not DOSM's survey,
        # and runs 0.5 to 0.8pp above it (2025: 3.76 vs DOSM 3.0). The check is
        # for scale and unit errors (0.03 or 30 for 3%), which 1.0pp still catches.
        res("PASS" if rows and abs(w[1]) <= 1.0 else "FAIL", "Unemployment: DOSM monthly (annual mean) vs World Bank ILO",
            f"{len(rows)} years: {rows}; largest gap {w} pp (tolerance 1.0: modelled vs surveyed)")

    def fx():
        ann = wb("PA.NUS.FCRF")
        hist = d["fx_to_usd"]["history"]
        if len(hist) <= 24:
            res("FAIL", "FX: month-end mean vs World Bank annual average", "no monthly FX history (FRED key missing?)")
            return
        rows = []
        for y in sorted(ann)[-5:]:
            ms = [v for p, v in hist if p.startswith(f"{y}-")]
            if len(ms) == 12:
                rows.append((y, round(sum(ms) / 12 / ann[y] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.5 else "FAIL", "FX: month-end mean vs World Bank annual average",
            f"{len(rows)} years, largest gap {w} % (tolerance 1.5)")
        j = get("https://api.bnm.gov.my/public/exchange-rate/USD", "application/vnd.BNM.API.v1+json").json()
        r = j["data"]["rate"]
        mid = r.get("middle_rate") or (r["buying_rate"] + r["selling_rate"]) / 2
        gap = round(hist[-1][1] / mid * 100 - 100, 2)
        res("PASS" if abs(gap) <= 2.0 else "FAIL", "FX: latest vs Bank Negara mid rate",
            f"site {hist[-1]}, BNM {round(mid, 4)} on {r['date']}, gap {gap} % (tolerance 2)")

    for name, fn in (("CPI index cross-check", cpi_index), ("CPI rate cross-check", cpi_rate),
                     ("CPI derivation check", cpi_derivation), ("GDP cross-check", gdp),
                     ("real growth check", real_yoy), ("q/q derivation check", qoq_derivation), ("q/q label check", qoq_label), ("trade cross-check", trade),
                     ("OPR check", opr), ("labour cross-check", labour), ("FX cross-check", fx)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with DOSM / Bank Negara by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<16} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<16} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-my.json"
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    structure_and_plausibility(d)
    if not offline:
        sys.path.insert(0, ".")
        cross_checks(d)
    spot_sheet(d)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)} PASS/INFO, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
