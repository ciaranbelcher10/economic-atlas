"""Pre-launch audit of data-eg.json (v1.7.53, partial-coverage page, built
from tools/audit_vn.py). The Central Bank of Egypt's site rejects automated
requests and CAPMAS serves a JavaScript application only: CPI and goods
trade are monthly via the IMF, GDP and unemployment are World Bank annual,
and there is no policy rate (the IMF's latest CBE rate was 14 months old at
the probe). Nothing about Egypt is shown to users until this passes on a
file written by the real pipeline.

    python3 tools/audit_eg.py                 # data-eg.json, with cross-checks
    python3 tools/audit_eg.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rates   the IMF's published y/y and m/m vs the change in its own index
  growth      World Bank published real growth vs the change in real GDP served
  FX          World Bank annual vs the mean of BIS monthly averages
  trade       pounds / BIS monthly average rate = the IMF's own US$ figures
Ranges are first estimates from the 12 Oct 2026 probe; resize only with the
publisher's figure in a comment. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, os, re, sys
from datetime import datetime, timezone

DEFAULT_FILE = "data-eg.json"
EXPECT = {
    "gdp_level": ("EGPm", "years", 5e2, 5e7, None),          # probe: EGP 18.1tn (1.8e7 m) in 2025
    "gdp_real": ("EGPm", "years", 1e4, 3e7, None),           # probe: EGP 8.7tn in 2025
    "gdp_growth": ("%", "years", -5, 15, None),
    "cpi": ("%", "months", -5, 45, 3.0),                      # September 2023 peak near 38%
    "cpi_mom": ("%", "months", -5, 15, None),                 # February 2024 near 11%
    "exports": ("EGPm", "months", 5e2, 1e6, None),            # probe: US$4.6bn in May 2026
    "imports": ("EGPm", "months", 5e2, 2e6, None),            # probe: US$9.9bn in April 2026
    "trade_balance": ("EGPm", "months", -1.5e6, 2e5, None),
    "unemployment": ("%", "years", 3, 20, 1.5),              # probe: 6.8% (ILO modelled) in 2025
    "debt_gdp": ("%", "years", 50, 130, None),               # probe: 90.9% in 2024
    "deficit": ("%", "years", -20, 3, None),                 # run 1: WEO shows a 2.1% surplus in 1999
    "current_account": ("%", "years", -12, 10, None),
    "fdi": ("%", "years", -1, 15, None),
}
KNOWN_JUMPS = {
    # Run 1 (12 Oct 2026); tolerances unchanged. All in CAPMAS' own y/y rates (IMF CPI).
    **{("cpi", p): "pass-through of the 3 November 2016 float" for p in ("2016-12", "2017-01")},
    ("cpi", "2017-07"): "fuel price rises and the VAT increase of July 2017",
    **{("cpi", p): "base effect: the post-float surge dropping out of the twelve-month comparison" for p in ("2017-11", "2017-12", "2018-01")},
    ("cpi", "2018-12"): "fall in food prices (m/m -3.4% in December 2018)",
    ("cpi", "2019-06"): "base effect: June 2018's fuel price rises dropped out",
    ("cpi", "2019-12"): "base effect: December 2018's food price fall dropped out",
    ("cpi", "2023-06"): "2023 inflation surge after the 2022-23 devaluations",
    ("cpi", "2024-01"): "base effect: January 2023's surge dropped out",
    ("cpi", "2024-05"): "base effect: the spring 2023 surge dropped out",
    **{("unemployment", p): "swings in the ILO modelled estimate" for p in ("1993", "1996", "2007", "2018", "2019")},
    ("unemployment", "2011"): "the 2011 revolution and its aftermath",
    ("cpi", "2016-11"): "the pound was floated on 3 November 2016 and roughly halved in value",
    ("cpi", "2023-01"): "2023 inflation surge after the 2022-23 devaluations (y/y peaked near 38% in September 2023)",
    ("cpi", "2023-02"): "2023 inflation surge after the 2022-23 devaluations",
    ("cpi", "2024-02"): "price rises ahead of the 6 March 2024 float",
    ("cpi", "2025-02"): "base effect: February 2024's surge dropped out of the twelve-month comparison",
}
NOT_SERVED = {"policy_rate": "the IMF's latest CBE rate was August 2025 at the probe; CBE rejects automated requests",
              "bond_yield_10y": "no free series", "business_confidence": "no OECD coverage", "ecb_rate": "not a euro member"}
OFFICIAL = {
    "cpi": "CAPMAS monthly urban CPI release, y/y", "cpi_mom": "CAPMAS monthly release, m/m",
    "exports": "CAPMAS / customs (US$; pounds here)", "imports": "CAPMAS / customs", "trade_balance": "CAPMAS balance",
    "gdp_level": "Ministry of Planning annual GDP (via World Bank)", "gdp_real": "via World Bank", "gdp_growth": "annual real growth",
    "unemployment": "ILO modelled estimate (World Bank)", "debt_gdp": "IMF WEO", "deficit": "IMF WEO",
    "current_account": "World Bank", "fdi": "World Bank",
}
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
MAX_AGE = {"months": 210, "years": 800}   # 210: ITG lags (fetch_eg.TRADE_MAX_AGE)
INTERNAL = r"confirmed|placeholder|inferred|probe|todo|Vietnam|\bdong\b|Nigeria"
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
    lr = [s[k]["points"] for k in ("gdp_level", "gdp_real") if k in s]
    if len(lr) == 2:
        res("PASS" if lr[0][-1][0] == lr[1][-1][0] else "FAIL", "nominal and real GDP end in the same year",
            f"{lr[0][-1][0]} / {lr[1][-1][0]}")
    if "exports" not in EXPECT:
        return
    tb, ex, im = (dict(s.get(k, {}).get("points", [])) for k in ("trade_balance", "exports", "imports"))
    bad = [p for p, v in tb.items() if p in ex and p in im and abs(ex[p] - im[p] - v) > 0.2]
    res("FAIL" if bad else "PASS", "trade balance = exports - imports", f"{len(bad)} mismatched month(s)")
    exp, imp = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if exp and imp:
        res("PASS" if exp[-1][0] == imp[-1][0] == (s.get("trade_balance", {}).get("points") or [[None]])[-1][0] else "FAIL",
            "exports, imports and balance end in the same month", f"exports {exp[-1][0]}, imports {imp[-1][0]}")


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
    ok = bool(fx.get("pair") == "EGP/USD" and fx.get("direction") == "divide" and 10 < (fx.get("rate") or 0) < 200
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (pounds per US$, annual, divide: fx_config.ANNUAL)",
        f"{fx.get('rate')} as of {fx.get('as_of')}")
    for key in ("cpi", "cpi_mom"):
        pts = d["series"].get(key, {}).get("points", [])
        many = [v for _, v in pts[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{key} at one decimal place", f"{len(many)} value(s) with more")
    tb = d["series"].get("trade_balance", {}).get("points", [])
    surplus = [p for p, v in tb if v > 0]
    res("FAIL" if surplus else "PASS", "no surplus months (Egypt runs a goods deficit every month; a surplus means a swapped ITG month)",
        f"{surplus or 'none'} (fetch_eg.SWAPPED_MONTHS corrects 2016-02)")


def bis_avg():
    rows = csv.DictReader(io.StringIO(get(
        "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.EG.EGP.A?format=csv", "text/csv").text))
    return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows
            if r.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", r["TIME_PERIOD"])}

def imf_rows(url):
    return list(csv.DictReader(io.StringIO(get(url, "text/csv").text)))


def cpi_index_check(d, iso3):
    """Our y/y and m/m are the IMF's published rates; check them against the
    change in the IMF's own all-items index (an identity, and a test that the
    rebased index joins cleanly)."""
    s = d["series"]
    ix = {}
    for r in imf_rows(f"https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/{iso3}.CPI._T.IX.M?c[TIME_PERIOD]=ge:2000-M01"):
        if r.get("OBS_VALUE"):
            ix[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])

    def back(p, n):
        k = period_key(p) - n
        return f"{k // 12}-{k % 12 + 1:02d}"
    for key, lag, tol in (("cpi", 12, 0.15), ("cpi_mom", 1, 0.15)):
        got = [(p, round(v - (ix[p] / ix[back(p, lag)] - 1) * 100, 2)) for p, v in s[key]["points"]
               if p in ix and back(p, lag) in ix]
        recent = got[-24:]
        w = worst(recent)
        res("PASS" if recent and abs(w[1]) <= tol else "FAIL", f"{key}: IMF published rate vs change in the IMF index (last 24 months)",
            f"{len(recent)} months, largest gap {w} pp (tolerance {tol})")
        old = [g for g in got[:-24] if abs(g[1]) > tol]
        res("INFO", f"{key}: earlier months where the published rate and the index disagree", f"{len(old)}: {old[:6]}")


def wb_growth_check(d, iso3):
    s = d["series"]
    j = get(f"https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=200").json()
    wb = {x["date"]: x["value"] for x in j[1] if x["value"] is not None}
    got = [(p, round(v - wb[p], 2)) for p, v in s["gdp_growth"]["points"][-10:] if p in wb]
    w = worst(got)
    res("PASS" if got and abs(w[1]) <= 0.15 else "FAIL", "gdp_growth vs World Bank published real growth",
        f"{len(got)} years, largest gap {w} pp (tolerance 0.15)")


def fx_history_sheet(d, scale, glyph):
    """Prints the whole annual FX history in the page's own terms (US$ per
    `scale` units) so the start year can be chosen from evidence, as Vietnam's
    1989 floor was (fx_config.SERIES_START)."""
    hist = (d.get("fx_to_usd") or {}).get("history") or []
    print(f"\n== FX HISTORY (US$ per {glyph}{scale:,}, World Bank annual): pick the first market-rate year")
    for i in range(0, len(hist), 6):
        print("  " + "   ".join(f"{p} {scale / v:,.4g}" for p, v in hist[i:i + 6] if v))


def cross_checks(d):
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

    for name, fn in (("CPI index check", lambda: cpi_index_check(d, "EGY")),
                     ("growth check", lambda: wb_growth_check(d, "EGY")), ("FX cross-check", fx),
                     ("trade check", lambda: trade_check(d, "EGY", bis_avg()))):
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
    fx_history_sheet(d, 100, "E\u00a3")
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)} PASS/INFO, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
