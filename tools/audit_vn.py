"""Pre-launch audit of data-vn.json (v1.7.50, partial-coverage page, built
from tools/audit_ph.py). Vietnam's statistics office and State Bank publish
HTML only: CPI and trade are monthly via the IMF, GDP and unemployment are
World Bank annual, and there is no policy rate. Nothing about Vietnam is
shown to users until this passes on a file written by the real pipeline.

    python3 tools/audit_vn.py                 # data-vn.json, with cross-checks
    python3 tools/audit_vn.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rate    our y/y from the IMF index vs the IMF's own y/y transformation
  growth      World Bank published real growth vs the change in real GDP served
  FX          World Bank annual vs the mean of BIS monthly averages
  trade       dong / BIS monthly average rate = the IMF's own US$ figures
Ranges are first estimates; resize only with the publisher's figure in a
comment. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, os, re, sys
from datetime import datetime, timezone

DEFAULT_FILE = "data-vn.json"
EXPECT = {
    "gdp_level": ("VNDm", "years", 1e4, 2e10, None),         # about VND 12,000tn in 2025
    "gdp_real": ("VNDm", "years", 1e5, 1.5e10, None),
    "gdp_growth": ("%", "years", -2, 15, None),
    "cpi": ("%", "months", -5, 30, 3.0),                     # 2008 peak near 28%
    "cpi_mom": ("%", "months", -3, 5, None),
    "exports": ("VNDm", "months", 2e7, 2.5e9, None),         # about US$40bn a month by 2026
    "imports": ("VNDm", "months", 2e7, 2.5e9, None),
    "trade_balance": ("VNDm", "months", -3e8, 4e8, None),
    "unemployment": ("%", "years", 0.5, 6, 1.5),
    "debt_gdp": ("%", "years", 20, 80, None),
    "deficit": ("%", "years", -12, 5, None),
    "current_account": ("%", "years", -15, 15, None),
    "fdi": ("%", "years", -1, 15, None),         # 1985: -0.0006% (World Bank, run 1)
}
KNOWN_JUMPS = {
    # Run 1 (12 Oct 2026); tolerances unchanged. The two inflation surges
    # and their reversals, in the statistics office's own y/y rates (IMF CPI).
    **{("cpi", p): "2008 food and fuel inflation surge (y/y peaked at 28.3% in August 2008) and its collapse"
       for p in ("2008-03", "2008-05", "2008-12", "2009-03", "2009-05")},
    ("cpi", "2011-04"): "2011 inflation surge (y/y peaked at 23.0% in August 2011)",
    ("cpi", "2012-04"): "disinflation after the 2011 surge",
}
NOT_SERVED = {"policy_rate": "BIS has no Vietnam series; SBV publishes HTML only",
              "bond_yield_10y": "no free series", "business_confidence": "no OECD coverage",
              "ecb_rate": "not a euro member"}
OFFICIAL = {
    "cpi": "NSO monthly CPI release, y/y", "cpi_mom": "NSO monthly CPI release, m/m",
    "exports": "Vietnam customs (US$; dong here)", "imports": "Vietnam customs", "trade_balance": "Vietnam customs balance",
    "gdp_level": "NSO annual GDP (via World Bank)", "gdp_real": "NSO (via World Bank)", "gdp_growth": "NSO annual real growth",
    "unemployment": "ILO modelled estimate (World Bank)", "debt_gdp": "IMF WEO", "deficit": "IMF WEO",
    "current_account": "World Bank", "fdi": "World Bank",
}
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
MAX_AGE = {"months": 130, "years": 800}
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Philippin|PSA|OpenSTAT|peso|Malaysia|Saudi"
RESULTS = []


def res(status, name, detail=""):
    RESULTS.append((status, name, detail))
    print(f"{status:<5} {name}  {detail}")


def period_key(p):
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m: return int(m.group(1)) * 12 + int(m.group(2)) - 1
    if re.fullmatch(r"\d{4}", p): return int(p)
    return None


def period_end(p):
    if re.fullmatch(r"\d{4}-\d{2}", p):
        y, m = divmod(period_key(p) + 1, 12)
        return datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return datetime(int(p) + 1, 1, 1, tzinfo=timezone.utc)


def worst(rows, i=-1):
    return max(rows, key=lambda x: abs(x[i])) if rows else None


def get(url, accept=None):
    import requests
    h = dict(UA)
    if accept: h["Accept"] = accept
    r = requests.get(url, timeout=90, headers=h)
    r.raise_for_status()
    return r


def structure(d):
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
        if not ser.get("label") or re.search(INTERNAL, ser["label"], re.I):
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
        if step and not nulls:
            jumps = [(pts[i][0], round(pts[i][1] - pts[i - 1][1], 2)) for i in range(1, len(pts))
                     if abs(pts[i][1] - pts[i - 1][1]) > step and (key, pts[i][0]) not in KNOWN_JUMPS]
            if jumps: problems.append(f"{len(jumps)} unnamed jump(s) over {step}: {jumps}")
        if len(pts) < {"months": 24, "years": 10}[freq]:
            problems.append(f"only {len(pts)} points")
        if pts and (datetime.now(timezone.utc) - period_end(pts[-1][0])).days > MAX_AGE[freq]:
            problems.append(f"stale: ends {pts[-1][0]}")
        res("FAIL" if problems else "PASS", f"{key} structure and range",
            "; ".join(problems) or f"{len(pts)} pts {pts[0][0]}..{pts[-1][0]}, last {pts[-1][1]}")
    tb, ex, im = (dict(s.get(k, {}).get("points", [])) for k in ("trade_balance", "exports", "imports"))
    bad = [p for p, v in tb.items() if p in ex and p in im and abs(ex[p] - im[p] - v) > 0.2]
    res("FAIL" if bad else "PASS", "trade balance = exports - imports", f"{len(bad)} mismatched month(s)")
    exp, imp = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if exp and imp:
        res("PASS" if exp[-1][0] == imp[-1][0] == (s.get("trade_balance", {}).get("points") or [[None]])[-1][0] else "FAIL",
            "exports, imports and balance end in the same month", f"exports {exp[-1][0]}, imports {imp[-1][0]}")
    lr = [s[k]["points"] for k in ("gdp_level", "gdp_real") if k in s]
    if len(lr) == 2:
        res("PASS" if lr[0][-1][0] == lr[1][-1][0] else "FAIL", "nominal and real GDP end in the same year",
            f"{lr[0][-1][0]} / {lr[1][-1][0]}")


def trade_check(d, iso3, rate):
    """Local-currency trade / the conversion rate = the IMF's own US$."""
    s = d["series"]
    itg = csv.DictReader(io.StringIO(get(
        f"https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/{iso3}.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
        "text/csv").text))
    usd = {}
    for r in itg:
        if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
            usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
    rows = []
    for k, ind in (("exports", "XG"), ("imports", "MG")):
        for p, v in s[k]["points"][-6:]:
            if (ind, p) in usd and p in rate and usd[(ind, p)]:
                rows.append((k, p, round(v / rate[p] / usd[(ind, p)] * 100 - 100, 3)))
    w = worst(rows)
    res("PASS" if rows and abs(w[2]) <= 0.1 else "FAIL", "Trade: local currency / conversion rate = the IMF's own US$",
        f"{len(rows)} comparisons, largest gap {w} % (tolerance 0.1, rounding)")


def growth_identity(d, tol):
    """Published annual growth vs the change in the real GDP level we serve."""
    s = d["series"]
    real = s["gdp_real"]["points"]
    der = {real[i][0]: (real[i][1] / real[i - 1][1] - 1) * 100 for i in range(1, len(real)) if real[i - 1][1]}
    rows = [(p, round(v - der[p], 2)) for p, v in s["gdp_growth"]["points"][-10:] if p in der]
    w = worst(rows)
    res("PASS" if rows and abs(w[1]) <= tol else "FAIL", "gdp_growth vs change in served real GDP",
        f"{len(rows)} years, largest gap {w} pp (tolerance {tol})")


def run(name, fn):
    try:
        fn()
    except Exception as exc:
        res("FAIL", name, f"cross-check could not run: {exc}")


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with the publisher by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<16} {p:>8}  {v:<14} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")



def country_checks(d):
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    ok = bool(fx.get("pair") == "VND/USD" and fx.get("direction") == "divide" and 10000 < (fx.get("rate") or 0) < 35000
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (dong per US$, annual, divide: fx_config.ANNUAL)",
        f"{fx.get('rate')} as of {fx.get('as_of')}")
    cpi = d["series"].get("cpi", {}).get("points", [])
    many = [v for _, v in cpi[-36:] if round(v, 1) != v]
    res("FAIL" if many else "PASS", "cpi at one decimal place", f"{len(many)} value(s) with more")


def bis_avg():
    rows = csv.DictReader(io.StringIO(get(
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.VN.VND.A?format=csv", "text/csv").text))
    return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows
            if r.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", r["TIME_PERIOD"])}


def cross_checks(d):
    s = d["series"]

    def cpi_rate():
        rows = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/VNM.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01",
            "text/csv").text))
        imf = {}
        for r in rows:
            if (r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("_T", "YOY_PCH_PA_PT") and r.get("OBS_VALUE"):
                imf[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
        got = [(p, round(v - imf[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in imf]
        w = worst(got)
        res("PASS" if got and abs(w[1]) <= 0.15 else "FAIL", "CPI y/y: from the IMF index vs the IMF's own y/y",
            f"{len(got)} months, largest gap {w} pp (tolerance 0.15)")

    def growth():
        j = get("https://api.worldbank.org/v2/country/VNM/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=200").json()
        wb = {x["date"]: x["value"] for x in j[1] if x["value"] is not None}
        got = [(p, round(v - wb[p], 2)) for p, v in s["gdp_growth"]["points"][-10:] if p in wb]
        w = worst(got)
        res("PASS" if got and abs(w[1]) <= 0.15 else "FAIL", "gdp_growth vs World Bank published real growth",
            f"{len(got)} years, largest gap {w} pp (tolerance 0.15)")

    def fx():
        by = {}
        for p, v in bis_avg().items():
            by.setdefault(p[:4], []).append(v)
        wbx = dict(d["fx_to_usd"]["history"])
        got = [(y, round(wbx[y] / (sum(v) / len(v)) * 100 - 100, 2)) for y, v in by.items()
               if len(v) == 12 and y in wbx and y >= "2018"]
        w = worst(got)
        res("PASS" if got and abs(w[1]) <= 1.0 else "FAIL", "FX: World Bank annual vs mean of BIS monthly averages",
            f"{got} (tolerance 1%)")

    for name, fn in (("CPI cross-check", cpi_rate), ("growth check", growth), ("FX cross-check", fx),
                     ("trade check", lambda: trade_check(d, "VNM", bis_avg()))):
        run(name, fn)


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else DEFAULT_FILE
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    structure(d)
    country_checks(d)
    if not offline:
        cross_checks(d)
    spot_sheet(d)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)} PASS/INFO, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
