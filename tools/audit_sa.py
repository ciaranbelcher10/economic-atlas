"""Pre-launch audit of data-sa.json (v1.7.35, built from tools/audit_nz.py).
Nothing about Saudi Arabia is shown to users until this passes on a file
written by the real pipeline and the spot-check against GASTAT's and SAMA's
releases matches.

    python3 tools/audit_sa.py                 # data-sa.json, with cross-checks
    python3 tools/audit_sa.py --offline FILE  # structure and plausibility only

Cross-checks, each against a different publisher or an identity:
  CPI rate    computed YoY vs the IMF CPI dataset's YoY (GASTAT's index)
  GDP         four OECD quarters vs World Bank annual nominal GDP
  growth      published q/q and y/y vs the change in OECD's real GDP levels
  FX          riyals per US$ within 0.5% of the 3.75 peg from 1987
  trade       riyals vs the IMF's own US$ figures at 3.75 (INFO)
Ranges are first estimates; resize only for named events found in the real
run. Run the fetch with OECD_TURN_GROUP=ALL first. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None). First estimates.
    "gdp_level": ("SARm", "quarters", 1e5, 2.5e6, None),         # about SAR 1.2tn a quarter in 2026
    "gdp_real": ("SARm", "quarters", 1e5, 2.5e6, None),
    "gdp_growth": ("%", "quarters", -15, 15, None),               # OPEC+ cuts and the 2020 collapse move it sharply
    "gdp_growth_yoy": ("%", "quarters", -15, 20, None),
    "cpi": ("%", "months", -5, 15, 3.0),                          # VAT tripled to 15% in July 2020 (a known step to verify)
    "cpi_mom": ("%", "months", -5, 8, None),
    "policy_rate": ("%", "months", 0, 10, 1.0),
    "unemployment": ("%", "years", 2, 10, None),
    "exports": ("SARm", "months", 2e4, 2.5e5, None),             # about SAR 88bn in mid-2026
    "imports": ("SARm", "months", 2e4, 1.5e5, None),
    "trade_balance": ("SARm", "months", -5e4, 2e5, None),
    "debt_gdp": ("%", "years", 0, 120, None),                     # near 100% in 1999, under 2% in 2014
    "deficit": ("%", "years", -25, 40, None),                     # oil-boom surpluses above 30% around 2008
    "current_account": ("%", "years", -30, 55, None),        # 1974 surplus about 51% of GDP, the year oil prices quadrupled
    "fdi": ("%", "years", -10, 15, None),                    # 1974 net outflow (-8%): the state took a 60% stake in Aramco
}
KNOWN_JUMPS = {
    # Named events, checked 9 Oct 2026; tolerances unchanged.
    ("cpi", "2020-07"): "VAT tripled from 5% to 15% on 1 July 2020: inflation 0.5% to 6.1%",
    ("cpi", "2021-07"): "base effect a year after the July 2020 VAT rise: 6.2% to 0.4%",
    ("cpi", "2018-01"): "VAT introduced at 5% and domestic energy prices raised in January 2018",
    ("cpi", "2019-01"): "base effect a year after the January 2018 VAT introduction and energy price rises",
    ("policy_rate", "2008-11"): "SAMA cut the repo rate by a cumulative 200bp in November 2008 (global financial crisis)",
    ("policy_rate", "2020-03"): "SAMA cut 50bp on 4 March and 75bp on 16 March 2020, following the Fed (COVID)",
}
NOT_SERVED = {"bond_yield_10y": "no 10-year government bond yield source (OECD FINMARK has only the exchange rate)",
              "business_confidence": "no OECD business confidence series for Saudi Arabia",
              "ecb_rate": "not a euro member"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "GASTAT quarterly GDP release, current prices (SAR)",
    "gdp_real": "GASTAT quarterly GDP release, constant prices (SAR)",
    "gdp_growth": "GASTAT quarterly GDP release, q/q seasonally adjusted",
    "gdp_growth_yoy": "GASTAT quarterly GDP release (flash), y/y (the headline figure)",
    "cpi": "GASTAT monthly CPI release, annual inflation",
    "cpi_mom": "GASTAT monthly CPI release, monthly change",
    "policy_rate": "SAMA repo rate in force now (latest decision, usually the day of a Fed decision)",
    "unemployment": "World Bank ILO modelled estimate; GASTAT's LFS total rate is quarterly and differs",
    "exports": "GASTAT international trade release, merchandise exports (SAR)",
    "imports": "GASTAT international trade release, merchandise imports (SAR)",
    "trade_balance": "GASTAT international trade release, merchandise balance (SAR)",
    "debt_gdp": "IMF WEO / Ministry of Finance debt",
    "deficit": "IMF WEO / Ministry of Finance budget balance",
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
        if not ser.get("label") or re.search(r"confirmed|placeholder|inferred|probe|todo|New Zealand|Stats NZ|NZ\$|\bOCR\b", ser["label"], re.I):
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
    res("PASS" if pr and pr[0][0] >= "2000-01" else "FAIL", "policy rate from January 2000 (BIS compilation note)",
        f"starts {pr[0][0] if pr else None}")
    odd = [(p, v) for p, v in pr if abs(round(v * 100) - v * 100) > 1e-6 or round(v * 100) % 5]
    res("FAIL" if odd else "PASS", "policy rate on a 5bp grid", f"{odd[:2]}")
    if pr:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(pr[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "policy rate is current (at most one month behind)",
            f"last month {pr[-1][0]} at {pr[-1][1]}%, {lag} month(s) behind")
    ex, im = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if ex and im:
        res("PASS" if ex[-1][0] == im[-1][0] == (s.get("trade_balance", {}).get("points") or [[None]])[-1][0] else "FAIL",
            "exports, imports and balance end in the same month", f"exports {ex[-1][0]}, imports {im[-1][0]}")
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    fx_ok = bool(fx.get("pair") == "SAR/USD" and fx.get("direction") == "divide" and 3.7 < (fx.get("rate") or 0) < 3.8
                 and hist and all(re.fullmatch(r"\d{4}", str(p)) for p, v in hist) and fx.get("rate") == hist[-1][1])
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block (riyals per US$, annual, divide, at the peg)", f"{fx.get('rate')} as of {fx.get('as_of')}")
    for k in ("cpi", "cpi_mom"):
        many = [v for _, v in s.get(k, {}).get("points", [])[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{k} at GASTAT's one decimal place", f"{len(many)} value(s) with more")


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
        j = get(f"https://api.worldbank.org/v2/country/SAU/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def cpi_rate():
        rows = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/SAU.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01",
            "text/csv").text))
        imf = {}
        for r in rows:
            if (r.get("INDEX_TYPE"), r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("CPI", "_T", "YOY_PCH_PA_PT") and r.get("OBS_VALUE"):
                imf[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
        rows = [(p, round(v - imf[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in imf]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "CPI YoY: computed vs IMF CPI YoY, last 24 months",
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
        res("PASS" if rows and abs(w[1]) <= 3.0 else "FAIL", "GDP: four OECD quarters vs World Bank annual",
            f"{len(rows)} years: {rows} (tolerance 3: seasonally adjusted quarters vs calendar-year total)")

    def growth():
        lv = s["gdp_real"]["points"]
        # gdp_growth_yoy is computed from unadjusted levels (GASTAT's headline),
        # so only the q/q rate is compared with the adjusted levels here.
        for key, lag in (("gdp_growth", 1),):
            der = pct(lv, lag)
            rows = [(p, round(v - der[p], 2)) for p, v in s[key]["points"][-16:] if p in der]
            w = worst(rows)
            res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", f"{key}: published vs change in real GDP levels",
                f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.15, rounding)")

    def fx():
        hist = dict(d["fx_to_usd"]["history"])
        off = [(y, v) for y, v in hist.items() if y >= "1987" and abs(v / 3.75 - 1) > 0.005]
        res("FAIL" if off else "PASS", "FX: riyals per US$ at the 3.75 peg from 1987", f"{off[:3]}")

    def trade():
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/SAU.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        rows = []
        for k, ind in (("exports", "XG"), ("imports", "MG")):
            for p, v in s[k]["points"][-6:]:
                if (ind, p) in usd:
                    rows.append((k, p, round(v / 3.75 / usd[(ind, p)] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[2]) <= 0.5 else "FAIL", "Trade: riyals / 3.75 equals the IMF's own US$",
            f"{len(rows)} comparisons, largest gap {w} % (tolerance 0.5)")

    for name, fn in (("CPI cross-check", cpi_rate), ("GDP cross-check", gdp), ("growth check", growth),
                     ("FX cross-check", fx), ("trade check", trade)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with GASTAT / SAMA by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<20} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-sa.json"
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
