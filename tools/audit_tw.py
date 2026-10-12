"""Pre-launch audit of data-tw.json (v1.7.50, partial-coverage page, built
from tools/audit_ph.py). Taiwan's statistics office cannot be reached, so
GDP, inflation and unemployment are IMF WEO annual actuals; the policy rate
is the CBC's discount rate; trade is IMF ITG converted at FRED DEXTAUS.
Nothing about Taiwan is shown to users until this passes on a file written
by the real pipeline.

    python3 tools/audit_tw.py                 # data-tw.json, with cross-checks (needs FRED_API_KEY)
    python3 tools/audit_tw.py --offline FILE  # structure and plausibility only

Cross-checks:
  trade       NT$ / FRED DEXTAUS monthly mean = the IMF's own US$ figures
  growth      WEO real growth vs the change in WEO real GDP levels
Ranges are first estimates; resize only with the publisher's figure in a
comment. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, os, re, sys
from datetime import datetime, timezone

DEFAULT_FILE = "data-tw.json"
EXPECT = {
    # key: (unit, freq, low, high, max step or None). First estimates.
    "gdp_level": ("TWDm", "years", 1e6, 4e7, None),          # about NT$24.6tn in 2024
    "gdp_real": ("TWDm", "years", 1e6, 4e7, None),
    "gdp_growth": ("%", "years", -5, 16, None),
    "cpi": ("%", "years", -2, 20, None),                     # 1980-81 oil shock near 19%
    "unemployment": ("%", "years", 1, 7, 1.5),
    "policy_rate": ("%", "months", 0.5, 8, 0.75),            # Dec 2008 cut was 0.75pp
    "exports": ("TWDm", "months", 2e5, 4e6, None),           # about US$40-60bn a month by 2026
    "imports": ("TWDm", "months", 2e5, 3e6, None),
    "trade_balance": ("TWDm", "months", -3e5, 2e6, None),    # a surplus almost every month
    "debt_gdp": ("%", "years", 5, 60, None),
    "deficit": ("%", "years", -10, 6, None),
}
KNOWN_JUMPS = {
    # Run 1 (12 Oct 2026); tolerances unchanged. DGBAS annual unemployment.
    ("unemployment", "2001"): "dot-com bust: 2.99% in 2000 to 4.57% in 2001 (DGBAS)",
    ("unemployment", "2009"): "global financial crisis: 4.14% in 2008 to 5.85% in 2009 (DGBAS)",
}
NOT_SERVED = {"bond_yield_10y": "no free series", "business_confidence": "no OECD coverage",
              "current_account": "Taiwan is not in World Bank data", "fdi": "Taiwan is not in World Bank data",
              "cpi_mom": "no monthly CPI source reachable", "ecb_rate": "not a euro member"}
OFFICIAL = {
    "gdp_level": "DGBAS national accounts (via IMF WEO)", "gdp_real": "DGBAS (via IMF WEO)",
    "gdp_growth": "DGBAS annual real growth", "cpi": "DGBAS annual CPI change",
    "unemployment": "DGBAS annual unemployment rate", "policy_rate": "CBC discount rate in force now",
    "exports": "Ministry of Finance customs statistics (US$; NT$ here)", "imports": "Ministry of Finance customs statistics",
    "trade_balance": "Ministry of Finance trade balance", "debt_gdp": "IMF WEO", "deficit": "IMF WEO",
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
    s = d["series"]
    pr = s.get("policy_rate", {}).get("points", [])
    odd = [(p, v) for p, v in pr if abs(round(v * 1000) - v * 1000) > 1e-6 or round(v * 1000) % 125]
    res("FAIL" if odd else "PASS", "discount rate on a 12.5bp grid", f"{odd[:2]}")
    if pr:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(pr[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "policy rate is current (at most one month behind)",
            f"last month {pr[-1][0]} at {pr[-1][1]}%, {lag} month(s) behind")
    fx = d.get("fx_to_usd") or {}
    hist = fx.get("history") or []
    ok = bool(fx.get("pair") == "TWD/USD" and fx.get("direction") == "divide" and 25 < (fx.get("rate") or 0) < 40
              and hist and fx.get("rate") == hist[-1][1] and all(re.fullmatch(r"\d{4}-\d{2}", p) for p, _ in hist))
    res("PASS" if ok else "FAIL", "fx_to_usd block (NT$ per US$, monthly, divide)", f"{fx.get('rate')} as of {fx.get('as_of')}")


def cross_checks(d):
    def trade():
        key = os.environ.get("FRED_API_KEY")
        if not key:
            raise ValueError("FRED_API_KEY not set")
        j = get("https://api.stlouisfed.org/fred/series/observations?series_id=DEXTAUS"
                f"&api_key={key}&file_type=json&observation_start=2023-06-01").json()
        by = {}
        for o in j["observations"]:
            if o["value"] not in ("", "."):
                by.setdefault(o["date"][:7], []).append(float(o["value"]))
        trade_check(d, "TWN", {p: sum(v) / len(v) for p, v in by.items()})

    run("trade check", trade)
    run("growth identity", lambda: growth_identity(d, 0.15))


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
