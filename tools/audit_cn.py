"""Pre-launch audit of data-cn.json. Nothing about China is shown to users
until this passes on a file written by the real pipeline.

    python3 tools/audit_cn.py                 # data-cn.json, with cross-checks
    python3 tools/audit_cn.py --offline FILE  # structure and plausibility only

Three layers:
  1. Structure: every expected series present, units, frequency, labels,
     ascending unique periods, no gaps inside a series, no nulls.
  2. Plausibility: each value inside a range that rules out unit and scale
     errors (yuan millions vs billions, percent vs fraction), every series
     current for its frequency, step sizes that a real series can take.
  3. Cross-checks against an independent publication of the same quantity:
       CPI       OECD 12-month rate vs the rate implied by the IMF index
       GDP       four OECD quarters vs the World Bank annual total
       growth    OECD year-on-year quarters vs World Bank annual growth
       trade     yuan figures back to dollars vs the IMF's own dollar data
       FX        FRED monthly average vs World Bank annual average
  Then a spot-check sheet: the latest value of every series beside the
  official release to compare it with by eye. The last step is a person.
Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None)
    "gdp_level": ("CNYm", "quarters", 1e5, 6e7, None),   # Q1 1992 was about 0.5tn yuan
    "gdp_growth": ("%", "quarters", -15, 15, None),
    "gdp_growth_yoy": ("%", "quarters", -10, 20, None),
    "gdp_real": ("CNYm", "years", 1e5, 3e8, None),
    "cpi": ("%", "months", -5, 30, 3.0),
    "cpi_mom": ("%", "months", -4, 5, None),
    "policy_rate": ("%", "months", 0, 15, 1.5),
    "bond_yield_10y": ("%", "months", 0, 10, 1.0),
    "business_confidence": ("index", "months", 80, 120, None),
    "debt_gdp": ("%", "years", 5, 200, None),
    "deficit": ("%", "years", -20, 10, None),
    "current_account": ("%", "years", -10, 15, None),
    "fdi": ("%", "years", -5, 10, None),
    "unemployment": ("%", "years", 0, 15, None),
    "exports": ("CNYm", "months", 1e5, 5e6, None),
    "imports": ("CNYm", "months", 1e5, 5e6, None),
    "trade_balance": ("CNYm", "months", -1e6, 2e6, None),
}
# Series that may be missing without failing the audit, and why. Absent is
# better than approximate: no reachable source publishes China's official
# month-on-month CPI (the OECD carries only the 12-month rate, and the
# statistics bureau blocks requests from outside China). A rate derived
# from the IMF index read 0.3% for Aug 2026 where the bureau published 0.4%.
OPTIONAL = {"cpi_mom": "no reachable source publishes the official rate; a derived one is not shown"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "NBS quarterly GDP release (stats.gov.cn, 'Preliminary accounting results of GDP')",
    "gdp_growth": "NBS quarterly GDP release, quarter-on-quarter growth",
    "gdp_growth_yoy": "NBS quarterly GDP release, year-on-year growth (the headline figure)",
    "cpi": "NBS monthly CPI release (year on year)",
    "cpi_mom": "NBS monthly CPI release (month on month)",
    "policy_rate": "PBoC / National Interbank Funding Center monthly LPR announcement (1-year)",
    "bond_yield_10y": "ChinaBond 10-year government bond yield, monthly average",
    "exports": "General Administration of Customs monthly trade release (US$, then x exchange rate)",
    "imports": "General Administration of Customs monthly trade release",
    "trade_balance": "General Administration of Customs monthly trade release",
    "unemployment": "World Bank SL.UEM.TOTL.ZS (ILO modelled); compare NBS annual surveyed urban rate for context only",
}

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
    k, now = period_key(p), datetime.now(timezone.utc)
    if re.fullmatch(r"\d{4}-\d{2}", p): y, m = divmod(k + 1, 12); return datetime(y, m + 1, 1, tzinfo=timezone.utc)
    if "Q" in p: y, q = divmod(k + 1, 4); return datetime(y, q * 3 + 1, 1, tzinfo=timezone.utc)
    return datetime(int(p) + 1, 1, 1, tzinfo=timezone.utc)


def structure_and_plausibility(d):
    s = d.get("series", {})
    for key, (unit, freq, lo, hi, step) in EXPECT.items():
        ser = s.get(key)
        if not ser and key in OPTIONAL:
            res("PASS", f"{key} absent by design", OPTIONAL[key]); continue
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
                     if abs(pts[i][1] - pts[i - 1][1]) > step]
            if jumps: problems.append(f"jump over {step} at {jumps[-1]}")
        if len(pts) < {"months": 24, "quarters": 12, "years": 10}[freq]:
            problems.append(f"only {len(pts)} points")
        if pts and (datetime.now(timezone.utc) - period_end(pts[-1][0])).days > MAX_AGE[freq]:
            problems.append(f"stale: ends {pts[-1][0]}")
        res("FAIL" if problems else "PASS", f"{key} structure and range",
            "; ".join(problems) or f"{len(pts)} pts {pts[0][0]}..{pts[-1][0]}, last {pts[-1][1]}")
    tb, ex, im = (dict(s.get(k, {}).get("points", [])) for k in ("trade_balance", "exports", "imports"))
    bad = [p for p, v in tb.items() if p in ex and p in im and abs(ex[p] - im[p] - v) > 1]
    res("FAIL" if bad else "PASS", "trade balance = exports - imports", f"{len(bad)} mismatched month(s)")
    exp, imp = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
    if exp and imp:
        res("PASS" if exp[-1][0] == imp[-1][0] else "FAIL", "exports and imports end in the same month",
            f"exports {exp[-1][0]}, imports {imp[-1][0]}")
    mom = s.get("cpi_mom", {}).get("label", "")
    res("FAIL" if "IMF" in mom else "PASS", "CPI MoM is the published rate, not derived from an index", mom or "absent")
    fx = d.get("fx_to_usd") or {}
    fx_ok = fx.get("pair") == "CNY/USD" and fx.get("direction") == "divide" and 5 < (fx.get("rate") or 0) < 9
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block", f"{fx.get('rate')} as of {fx.get('as_of')}")
    if s.get("policy_rate"):
        odd = [(p, v) for p, v in s["policy_rate"]["points"] if p >= "2019-09" and round(v * 100) % 5]
        res("FAIL" if odd else "PASS", "LPR moves in 5bp steps since Aug 2019", f"{odd[:2]}")


# ------------------------------------------------------------ cross-checks
def cross_checks(d):
    import requests
    UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
    s = d["series"]

    def wb(code):
        r = requests.get(f"https://api.worldbank.org/v2/country/CHN/indicator/{code}?format=json&per_page=200",
                         timeout=60, headers=UA)
        r.raise_for_status()
        return {x["date"]: x["value"] for x in r.json()[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def cpi():
        import fetch_ma
        idx = dict(fetch_ma.fetch_imf_cpi_index("CHN") or [])
        if not idx:
            raise RuntimeError("IMF CPI index returned no data (source unreachable or empty)")
        diffs = []
        for p, v in s["cpi"]["points"][-24:]:
            y, m = int(p[:4]), p[5:]
            base = idx.get(f"{y - 1}-{m}")
            if base and p in idx:
                diffs.append((p, round(v - (idx[p] / base - 1) * 100, 2)))
        worst = max(diffs, key=lambda x: abs(x[1])) if diffs else None
        ok = diffs and abs(worst[1]) <= 0.3
        res("PASS" if ok else "FAIL", "CPI: OECD rate vs IMF index, last 24 months",
            f"{len(diffs)} months compared, largest gap {worst} pp (tolerance 0.3)")

    def gdp():
        ann = wb("NY.GDP.MKTP.CN")
        q = dict(s["gdp_level"]["points"])
        rows = []
        for y in sorted(ann)[-6:]:
            qs = [q.get(f"{y}-Q{i}") for i in range(1, 5)]
            if None not in qs:
                rows.append((y, round(sum(qs) / (ann[y] / 1e6) * 100 - 100, 2)))
        worst = max(rows, key=lambda x: abs(x[1])) if rows else None
        ok = rows and abs(worst[1]) <= 2.0
        res("PASS" if ok else "FAIL", "GDP: four OECD quarters vs World Bank annual",
            f"{len(rows)} years, largest gap {worst} % (tolerance 2)")

    def growth():
        ann = wb("NY.GDP.MKTP.KD.ZG")
        q = dict(s["gdp_growth_yoy"]["points"])
        lv = dict(s["gdp_level"]["points"])
        rows = []
        for y in sorted(ann)[-6:]:
            qs = [q.get(f"{y}-Q{i}") for i in range(1, 5)]
            # Annual growth is the quarters' growth weighted by each quarter's
            # size a year earlier, not their plain mean: in 2021 the plain
            # mean overstates it because Q1 2020 was unusually small.
            ws = [lv.get(f"{int(y) - 1}-Q{i}") for i in range(1, 5)]
            if None not in qs and None not in ws:
                g = sum(a * b for a, b in zip(qs, ws)) / sum(ws)
                rows.append((y, round(g - ann[y], 2)))
        worst = max(rows, key=lambda x: abs(x[1])) if rows else None
        ok = rows and abs(worst[1]) <= 0.6
        res("PASS" if ok else "FAIL", "Growth: OECD YoY quarters (weighted) vs World Bank annual",
            f"{len(rows)} years, largest gap {worst} pp (tolerance 0.6)")

    def trade():
        import fetch_cn
        raw = fetch_cn.fetch_trade()
        hist = d["fx_to_usd"]["history"]
        rows = []
        for k in ("exports", "imports"):
            usd = dict(raw[k])
            for p, v in s[k]["points"][-12:]:
                if p in usd:
                    back = v / fetch_cn.rate_for(hist, p, d["fx_to_usd"]["rate"])
                    rows.append((k, p, round(back / usd[p] * 100 - 100, 3)))
        worst = max(rows, key=lambda x: abs(x[2])) if rows else None
        ok = rows and abs(worst[2]) <= 0.1
        res("PASS" if ok else "FAIL", "Trade: yuan back to dollars vs IMF dollars, last 12 months",
            f"{len(rows)} comparisons, largest gap {worst} % (tolerance 0.1)")

    def fx():
        ann = wb("PA.NUS.FCRF")
        hist = d["fx_to_usd"]["history"]
        rows = []
        for y in sorted(ann)[-5:]:
            ms = [v for p, v in hist if p.startswith(f"{y}-")]
            if len(ms) == 12 and len(hist) > 24:
                rows.append((y, round(sum(ms) / 12 / ann[y] * 100 - 100, 2)))
        if len(hist) <= 24:
            res("FAIL", "FX: month-end mean vs World Bank annual average",
                "no monthly FX history (FRED unreachable or no key); the World Bank fallback cannot be checked against itself")
            return
        worst = max(rows, key=lambda x: abs(x[1])) if rows else None
        ok = rows and abs(worst[1]) <= 1.5
        res("PASS" if ok else "FAIL", "FX: month-end mean vs World Bank annual average",
            f"{len(rows)} years, largest gap {worst} % (tolerance 1.5)")

    for name, fn in (("CPI cross-check", cpi), ("GDP cross-check", gdp), ("growth cross-check", growth),
                     ("trade cross-check", trade), ("FX cross-check", fx)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with the official release)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<14} {ser['unit']:<6} -> {OFFICIAL.get(key, 'source named in label')}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-cn.json"
    d = json.load(open(path))
    print(f"Audit of {path}, updated {d.get('updated')}\n")
    structure_and_plausibility(d)
    if not offline:
        sys.path.insert(0, ".")
        cross_checks(d)
    spot_sheet(d)
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)} PASS, {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
