"""Pre-launch audit of data-ph.json (v1.7.49, built from tools/audit_sa.py
and tools/audit_my.py). Run 1: 12 Oct 2026, 26 PASS / 12 FAIL, each cleared
by a fetch fix or a named, sourced entry below. Nothing about the Philippines is shown to users until
this passes on a file written by the real pipeline and the spot-check
against PSA's and BSP's releases matches.

    python3 tools/audit_ph.py                 # data-ph.json, with cross-checks
    python3 tools/audit_ph.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rate    PSA's published YoY vs the IMF CPI dataset's YoY
  GDP         four PSA quarters vs World Bank annual nominal GDP
  growth      PSA's SA q/q vs the change in PSA's SA real GDP levels
  labour      PSA monthly unemployment (annual mean) vs World Bank ILO
  FX          World Bank annual vs the mean of BIS monthly averages
  trade       pesos / BIS monthly average rate = the IMF's own US$ figures
Ranges are first estimates; resize only for named events found in the real
run (with the publisher's figure in a comment). Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None). First estimates.
    "gdp_level": ("PHPm", "quarters", 5e5, 1.5e7, None),        # about PHP 7tn a quarter in 2026
    "gdp_real": ("PHPm", "quarters", 5e5, 1.2e7, None),
    "gdp_growth": ("%", "quarters", -20, 15, None),              # 2020-Q2 lockdown collapse
    "gdp_growth_yoy": ("%", "quarters", -20, 15, None),
    "cpi": ("%", "months", -3, 25, 3.0),                         # 1980s inflation; 1984 peak to verify
    "cpi_mom": ("%", "months", -3, 6, None),
    "policy_rate": ("%", "months", 0, 25, 1.0),
    "unemployment": ("%", "months", 2, 20, 3.0),                 # April 2020 lockdown spike to verify
    "participation": ("%", "months", 50, 75, 4.0),
    "employment": ("%", "months", 40, 75, 4.0),
    "exports": ("PHPm", "months", 2e4, 6e5, None),               # about US$6-7bn a month
    "imports": ("PHPm", "months", 3e4, 1.2e6, None),             # PHP 880,621m in Jun 2026 (run 1), above the first guess
    "trade_balance": ("PHPm", "months", -6e5, 5e4, None),        # a deficit almost every month; PHP -418,681m in May 2026 (run 1)
    "debt_gdp": ("%", "years", 20, 110, None),
    "deficit": ("%", "years", -15, 5, None),
    "current_account": ("%", "years", -15, 10, None),
    "fdi": ("%", "years", -2, 8, None),
}
KNOWN_JUMPS = {
    # From run 1 (12 Oct 2026); tolerances unchanged.
    ("cpi", "2026-04"): "PSA: 4.1% in March to 7.2% in April 2026; transport 9.9% to 21.4%, food 2.9% to 6.0%",
    ("policy_rate", "2007-07"): "BSP removed the tiering on placements and set the RRP rate at 6.0% (7.5% in April 2007)",
    # PSA's unadjusted labour force survey dips every July and January and
    # recovers the next month, in every year of the monthly survey: values
    # are PSA's own table (1B/LFS 0021B3FKEI2), not a fetch artefact.
    **{(k, p): "seasonal swing in PSA's unadjusted labour force survey (July and January rounds)"
       for k, ps in (("participation", ("2021-07", "2021-08", "2022-01", "2023-07", "2023-08", "2024-01", "2025-07", "2025-08")),
                     ("employment", ("2021-07", "2022-01", "2023-07", "2023-08", "2024-01", "2024-02", "2025-07", "2025-08")))
       for p in ps},
}
NOT_SERVED = {"bond_yield_10y": "no source in the probe states a 10-year maturity",
              "business_confidence": "BSP's business expectations survey is quarterly and a different measure",
              "ecb_rate": "not a euro member"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "PSA quarterly national accounts release, current prices (PHP)",
    "gdp_real": "PSA seasonally adjusted national accounts, constant 2018 prices (PHP)",
    "gdp_growth": "PSA GDP release, seasonally adjusted q/q",
    "gdp_growth_yoy": "PSA GDP release, y/y (the headline figure)",
    "cpi": "PSA monthly CPI release, headline inflation (2018=100)",
    "cpi_mom": "PSA monthly CPI release, month-on-month (unadjusted index)",
    "policy_rate": "BSP target RRP rate in force now (latest Monetary Board decision)",
    "unemployment": "PSA labour force survey release, unemployment rate",
    "participation": "PSA labour force survey release, LFPR",
    "employment": "participation x PSA employment rate (PSA does not publish this ratio)",
    "exports": "PSA international merchandise trade release (US$; pesos here via IMF)",
    "imports": "PSA international merchandise trade release (US$; pesos here via IMF)",
    "trade_balance": "PSA international merchandise trade release, balance",
    "debt_gdp": "IMF WEO / Bureau of the Treasury debt",
    "deficit": "IMF WEO / DBM fiscal balance",
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
        if not ser.get("label") or re.search(r"confirmed|placeholder|inferred|probe|todo|Malaysia|DOSM|OpenDOSM|Saudi|GASTAT|SAMA|ringgit|riyal", ser["label"], re.I):
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
            if jumps: problems.append(f"{len(jumps)} unnamed jump(s) over {step}: {jumps}")
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
    odd = [(p, v) for p, v in pr if p >= "2016-06" and (abs(round(v * 100) - v * 100) > 1e-6 or round(v * 100) % 25)]
    res("FAIL" if odd else "PASS", "policy rate on a 25bp grid since the June 2016 corridor", f"{odd[:2]}")
    if pr:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(pr[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "policy rate is current (at most one month behind)",
            f"last month {pr[-1][0]} at {pr[-1][1]}%, {lag} month(s) behind")
    ex, im = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if ex and im:
        res("PASS" if ex[-1][0] == im[-1][0] == (s.get("trade_balance", {}).get("points") or [[None]])[-1][0] else "FAIL",
            "exports, imports and balance end in the same month", f"exports {ex[-1][0]}, imports {im[-1][0]}")
    lab = [s.get(k, {}).get("points", []) for k in ("unemployment", "participation", "employment")]
    res("PASS" if all(lab) and len({x[-1][0] for x in lab}) == 1 else "FAIL", "labour series end in the same month",
        f"{[x[-1][0] if x else None for x in lab]}")
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    fx_ok = bool(fx.get("pair") == "PHP/USD" and fx.get("direction") == "divide" and 35 < (fx.get("rate") or 0) < 80
                 and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}", str(p)) for p, v in hist))
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block (pesos per US$, annual, divide: fx_config.ANNUAL)", f"{fx.get('rate')} as of {fx.get('as_of')}")
    for k in ("cpi", "cpi_mom", "unemployment", "participation", "employment", "gdp_growth"):
        many = [v for _, v in s.get(k, {}).get("points", [])[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{k} at PSA's one decimal place", f"{len(many)} value(s) with more")


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
        j = get(f"https://api.worldbank.org/v2/country/PHL/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def cpi_rate():
        rows = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/PHL.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01",
            "text/csv").text))
        imf = {}
        for r in rows:
            if (r.get("INDEX_TYPE"), r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("CPI", "_T", "YOY_PCH_PA_PT") and r.get("OBS_VALUE"):
                imf[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
        rows = [(p, round(v - imf[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in imf]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "CPI YoY: PSA vs IMF CPI YoY, last 24 months",
            f"{len(rows)} months, largest gap {w} pp (tolerance 0.15)")

    def gdp():
        ann = wb("NY.GDP.MKTP.CN")
        q = dict(s["gdp_level"]["points"])
        rows = []
        for y in sorted(ann)[-6:]:
            qs = [q.get(f"{y}-Q{i}") for i in range(1, 5)]
            if None not in qs:
                rows.append((y, round(sum(qs) / (ann[y] / 1e6) * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 2.0 else "FAIL", "GDP: four PSA quarters vs World Bank annual",
            f"{len(rows)} years: {rows} (tolerance 2)")

    def growth():
        der = pct(s["gdp_real"]["points"], 1)
        rows = [(p, round(v - der[p], 2)) for p, v in s["gdp_growth"]["points"][-16:] if p in der]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "gdp_growth: PSA SA q/q vs change in PSA SA real GDP",
            f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.15, rounding)")

    def labour():
        ilo = wb("SL.UEM.TOTL.ZS")
        by = {}
        for p, v in s["unemployment"]["points"]:
            by.setdefault(p[:4], []).append(v)
        rows = [(y, round(sum(v) / len(v) - ilo[y], 2)) for y, v in by.items() if len(v) == 12 and y in ilo]
        w = worst(rows)
        # Definitional difference (XCHECK_EXCEPT): the World Bank series is the
        # ILO's modelled estimate, not PSA's survey; run 1 gaps 1.6 to 4.4pp,
        # shrinking since 2021. Shown for the record; the spot-check is PSA's release.
        res("INFO" if rows else "FAIL", "Unemployment: PSA monthly (annual mean) vs World Bank ILO (definitional difference)",
            f"{rows[-5:]}")

    def bis_avg():
        rows = csv.DictReader(io.StringIO(get(
            "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.PH.PHP.A?format=csv", "text/csv").text))
        return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows
                if r.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", r["TIME_PERIOD"])}

    def fx():
        bis = bis_avg()
        by = {}
        for p, v in bis.items():
            by.setdefault(p[:4], []).append(v)
        wbx = dict(d["fx_to_usd"]["history"])
        rows = [(y, round(wbx[y] / (sum(v) / len(v)) * 100 - 100, 2)) for y, v in by.items() if len(v) == 12 and y in wbx and y >= "2018"]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.0 else "FAIL", "FX: World Bank annual vs mean of BIS monthly averages",
            f"{rows} (tolerance 1%)")

    def trade():
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/PHL.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        rate = bis_avg()
        rows = []
        for k, ind in (("exports", "XG"), ("imports", "MG")):
            for p, v in s[k]["points"][-6:]:
                if (ind, p) in usd and p in rate:
                    rows.append((k, p, round(v / rate[p] / usd[(ind, p)] * 100 - 100, 3)))
        w = worst(rows)
        res("PASS" if rows and abs(w[2]) <= 0.1 else "FAIL", "Trade: pesos / BIS monthly average = the IMF's own US$",
            f"{len(rows)} comparisons, largest gap {w} % (tolerance 0.1, rounding)")

    for name, fn in (("CPI cross-check", cpi_rate), ("GDP cross-check", gdp), ("growth check", growth),
                     ("labour cross-check", labour), ("FX cross-check", fx), ("trade check", trade)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with PSA / BSP by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<20} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-ph.json"
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
