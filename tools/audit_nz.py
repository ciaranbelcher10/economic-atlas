"""Pre-launch audit of data-nz.json. Nothing about New Zealand is shown to
users until this passes on a file written by the real pipeline, and
Ciaran's spot-check against Stats NZ's and the Reserve Bank's releases
matches.

    python3 tools/audit_nz.py                 # data-nz.json, with cross-checks
    python3 tools/audit_nz.py --offline FILE  # structure and plausibility only

Built from tools/audit_my.py. Cross-checks, each against a different
publisher or an identity:
  CPI rate    computed YoY vs BIS long CPI YoY (WS_LONG_CPI, 771) at quarter ends
  GDP         four OECD quarters vs World Bank annual nominal GDP
  growth      published q/q and y/y vs the change in OECD's real GDP levels
  unemployment quarterly OECD (annual mean) vs World Bank ILO
  OCR         from April 1999 only, 25bp steps
  FX          US$ per NZ$ month-end mean vs the inverse of the World Bank
              annual average NZ$ per US$; direction checked structurally
  trade       NZ$ x month's rate = IMF US$ (the conversion is exact)
OECD replies only in this script's oecd_turn group, so run the fetch with
OECD_TURN_GROUP=ALL before auditing. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None)
    "gdp_level": ("NZDm", "quarters", 1e4, 3e5, None),
    "gdp_real": ("NZDm", "quarters", 1e4, 2e5, None),
    "gdp_growth": ("%", "quarters", -15, 20, None),          # 2020: -10% then +14%
    "gdp_growth_yoy": ("%", "quarters", -15, 20, None),
    "cpi": ("%", "quarters", -3, 25, 4.0),
    "cpi_qoq": ("%", "quarters", -3, 10, None),
    "policy_rate": ("%", "months", 0, 10, 1.0),               # moves over 1.0pp must be named in KNOWN_JUMPS
    "bond_yield_10y": ("%", "months", -1, 20, 2.5),
    "business_confidence": ("index", "months", 85, 115, 4.0),
    "unemployment": ("%", "quarters", 2, 12, 1.5),
    "exports": ("NZDm", "months", 300, 2e4, None),
    "imports": ("NZDm", "months", 300, 2e4, None),
    "trade_balance": ("NZDm", "months", -6e3, 6e3, None),
    "debt_gdp": ("%", "years", 5, 150, None),
    "deficit": ("%", "years", -15, 10, None),
    "current_account": ("%", "years", -15, 10, None),
    "fdi": ("%", "years", -10, 15, None),
}
KNOWN_JUMPS = {
    # The Reserve Bank cut the OCR by 150 basis points at each of these
    # reviews during the global financial crisis (6.5% to 5.0%, then 3.5%).
    ("policy_rate", "2008-12"): "OCR cut 150bp on 4 Dec 2008",
    ("policy_rate", "2009-01"): "OCR cut 150bp on 29 Jan 2009",
}
NOT_SERVED = {"cpi_mom": "Stats NZ has no monthly CPI; the CPI is quarterly",
              "employment": "no confirmed OECD source yet",
              "participation": "no confirmed OECD source yet"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "Stats NZ quarterly GDP release (expenditure measure, current prices, seasonally adjusted)",
    "gdp_real": "Stats NZ quarterly GDP release, production measure, chain-volume",
    "gdp_growth": "Stats NZ quarterly GDP release, q/q seasonally adjusted (the headline figure)",
    "gdp_growth_yoy": "Stats NZ quarterly GDP release, 'annual change' (quarter vs same quarter a year earlier; Q2 2026: 2.6%). NOT the '12 months to' annual-average figure (Q2 2026: 1.7%)",
    "cpi": "Stats NZ quarterly CPI release, annual change",
    "cpi_qoq": "Stats NZ quarterly CPI release, quarterly change",
    "policy_rate": "Reserve Bank of New Zealand: the OCR in force now (latest decision, e.g. 2.75% from 2 Sep 2026)",
    "bond_yield_10y": "RBNZ wholesale interest rates (B2), 10-year government bond, monthly average",
    "business_confidence": "OECD business confidence indicator (no national equivalent)",
    "unemployment": "Stats NZ Household Labour Force Survey, unemployment rate, seasonally adjusted",
    "exports": "Stats NZ overseas merchandise trade, goods exports (NZ$)",
    "imports": "Stats NZ overseas merchandise trade, goods imports (NZ$)",
    "trade_balance": "Stats NZ overseas merchandise trade, monthly balance (NZ$)",
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
    res("PASS" if pr and pr[0][0] >= "1999-04" else "FAIL", "policy rate is the OCR only (no spliced earlier measure)",
        f"starts {pr[0][0] if pr else None}")
    odd = [(p, v) for p, v in pr if round(v * 100) % 25]
    res("FAIL" if odd else "PASS", "OCR moves in 25bp steps", f"{odd[:2]}")
    # The OCR must be current: at most one month behind today (BIS's daily
    # series fills the months its monthly series has not reached yet).
    if pr:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(pr[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "OCR is current (at most one month behind)",
            f"last month {pr[-1][0]} at {pr[-1][1]}%, {lag} month(s) behind")
    ex, im = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if ex and im:
        res("PASS" if ex[-1][0] == im[-1][0] else "FAIL", "exports and imports end in the same month",
            f"exports {ex[-1][0]}, imports {im[-1][0]}")
    fx = d.get("fx_to_usd") or {}
    # DEXUSNZ is US$ per NZ$, so the rate is around 0.5 to 0.9 and multiplies.
    fx_ok = fx.get("pair") == "NZD/USD" and fx.get("direction") == "multiply" and 0.35 < (fx.get("rate") or 0) < 1.0
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block (US$ per NZ$, multiply)", f"{fx.get('rate')} as of {fx.get('as_of')}")
    # Stats NZ publishes CPI rates to one decimal place; the computed rates must too.
    for k in ("cpi", "cpi_qoq"):
        many = [v for _, v in s.get(k, {}).get("points", [])[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{k} at Stats NZ's one decimal place", f"{len(many)} value(s) with more")




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
        j = get(f"https://api.worldbank.org/v2/country/NZL/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def cpi_rate():
        rows = csv.DictReader(io.StringIO(get(
            "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LONG_CPI/1.0/M.NZ.*?format=csv&startPeriod=2010-01",
            "text/csv").text))
        bis = {}
        for r in rows:
            if r.get("UNIT_MEASURE") == "771" and r.get("OBS_VALUE") not in (None, "", "NaN"):
                y, m = r["TIME_PERIOD"].split("-")
                if int(m) % 3 == 0:
                    bis[f"{y}-Q{int(m) // 3}"] = float(r["OBS_VALUE"])
        rows = [(p, round(v - bis[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in bis]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "CPI YoY: computed vs BIS long CPI YoY, last 24 quarters",
            f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.15)")

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
        for key, lag in (("gdp_growth", 1), ("gdp_growth_yoy", 4)):
            der = pct(lv, lag)
            rows = [(p, round(v - der[p], 2)) for p, v in s[key]["points"][-16:] if p in der]
            w = worst(rows)
            res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", f"{key}: published vs change in real GDP levels",
                f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.15, rounding)")

    def labour():
        ann = wb("SL.UEM.TOTL.ZS")
        qv = s["unemployment"]["points"]
        rows = []
        for y in sorted(ann)[-6:]:
            vs = [v for p, v in qv if p.startswith(f"{y}-Q")]
            if len(vs) == 4:
                rows.append((y, round(sum(vs) / 4 - ann[y], 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.0 else "FAIL", "Unemployment: quarterly (annual mean) vs World Bank ILO",
            f"{len(rows)} years: {rows}; tolerance 1.0")

    def fx():
        hist = d["fx_to_usd"]["history"]
        if not any(re.fullmatch(r"\d{4}-\d{2}", p) for p, _ in hist):
            res("FAIL", "FX: month-end mean vs World Bank annual average", "no monthly FX history (FRED key missing?)")
            return
        ann = wb("PA.NUS.FCRF")      # NZ$ per US$
        rows = []
        for y in sorted(ann)[-5:]:
            ms = [v for p, v in hist if p.startswith(f"{y}-")]
            if len(ms) == 12:
                rows.append((y, round((1 / (sum(ms) / 12)) / ann[y] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.5 else "FAIL", "FX: inverse of US$ per NZ$ vs World Bank NZ$ per US$",
            f"{len(rows)} years: {rows} (tolerance 1.5)")

    def trade():
        hist = dict(d["fx_to_usd"]["history"])
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/NZL.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        rows = []
        for k, ind in (("exports", "XG"), ("imports", "MG")):
            for p, v in s[k]["points"][-12:]:
                if (ind, p) in usd and p in hist:
                    rows.append((k, p, round(v * hist[p] / usd[(ind, p)] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[2]) <= 0.5 else "FAIL", "Trade: NZ$ x month's rate equals IMF US$",
            f"{len(rows)} comparisons, largest gap {w} % (tolerance 0.5: rounding)")

    for name, fn in (("CPI cross-check", cpi_rate), ("GDP cross-check", gdp), ("growth check", growth),
                     ("labour cross-check", labour), ("FX cross-check", fx), ("trade check", trade)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with Stats NZ / the Reserve Bank by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<20} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-nz.json"
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
