"""Pre-launch audit of data-pt.json. Nothing about Portugal is shown to users
until this passes on a file written by the real pipeline, and Ciaran's
spot-check against INE's, the Banco de Portugal's and Eurostat's releases matches.

    python3 tools/audit_pt.py                 # data-pt.json, with cross-checks
    python3 tools/audit_pt.py --offline FILE  # structure and plausibility only

Built v1.7.20 from tools/audit_be.py. Cross-checks, each against a different
publisher or an identity:
  HICP        YoY vs the IMF's own HICP YoY (IMF CPI dataset, INDEX_TYPE HICP)
  GDP         four Eurostat quarters vs World Bank annual nominal GDP
  growth      q/q vs the change in Eurostat's real GDP levels
  unemployment monthly Eurostat (annual mean) vs World Bank ILO
  debt/deficit Eurostat EDP vs IMF WEO for the latest common years
  ECB rate    current (at most one month behind), 5bp grid
  FX          US$ per euro yearly mean vs inverse of World Bank euro per US$
  trade       INFO only: Eurostat (community concept) vs IMF US$ balance
Run the fetch with OECD_TURN_GROUP=ALL before auditing. Exit 1 on any FAIL.
"""
from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None)
    "gdp_level": ("\u20acm", "quarters", 1e4, 2e5, None),
    "gdp_real": ("\u20acm", "quarters", 1e4, 2e5, None),
    "gdp_growth": ("%", "quarters", -20, 20, None),          # Portugal 2020-Q2: -15.05% (COVID lockdown)
    "cpi": ("%", "months", -3, 15, 3.0),
    "cpi_mom": ("%", "months", -5, 6, None),
    "ecb_rate": ("%", "months", -1, 5, 0.8),                 # 75bp hikes in 2022
    "bond_yield_10y": ("%", "months", -1, 20, 2.5),
    "business_confidence": ("index", "months", 85, 115, 4.0),
    "unemployment": ("%", "months", 3, 20, 1.5),                 # peaked near 17.5% in 2013
    "participation_rate": ("%", "quarters", 55, 85, 3.0),
    "employment_rate": ("%", "quarters", 50, 80, 3.0),
    "trade_balance": ("\u20acm", "months", -8e3, 4e3, None),
    "debt_gdp": ("%", "years", 40, 160, None),
    "deficit": ("%", "years", -15, 5, None),
}
KNOWN_JUMPS = {
    # Named events, never loosened tolerances. Add Portuguese ones only after
    # checking them against INE or the Banco de Portugal.
    ("ecb_rate", "2009-01"): "ECB cut the deposit rate 100bp (2.0% to 1.0%), effective 21 Jan 2009",
    ("employment_rate", "2020-Q2"): "COVID-19 lockdown, Q2 2020",
    ("participation_rate", "2020-Q2"): "COVID-19 lockdown, Q2 2020",
    ("employment_rate", "2020-Q3"): "COVID-19 rebound, Q3 2020",
    ("participation_rate", "2020-Q3"): "COVID-19 rebound, Q3 2020",
}
NOT_SERVED = {"policy_rate": "Portugal has no own policy rate: the page shows the ECB's (ecb_rate)",
              "current_account": "not served on eurozone pages (Ireland excepted)",
              "fdi": "not served on eurozone pages (Ireland excepted)"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "Eurostat namq_10_gdp / INE quarterly accounts, current prices, SA, EUR million",
    "gdp_real": "Eurostat namq_10_gdp, chain-linked volumes, SA",
    "gdp_growth": "INE flash GDP, q/q seasonally and calendar adjusted (the headline)",
    "cpi": "Eurostat HICP for Portugal (INE publishes it too), annual rate; NOT INE's headline CPI, which differs",
    "cpi_mom": "Eurostat HICP for Portugal, monthly rate",
    "ecb_rate": "ECB deposit facility rate in force now (latest Governing Council decision)",
    "bond_yield_10y": "Banco de Portugal / ECB long-term interest rate for convergence, 10-year, monthly average",
    "business_confidence": "OECD business confidence indicator (INE has its own surveys; different scale)",
    "unemployment": "Eurostat une_rt_m / INE monthly estimate, seasonally adjusted",
    "participation_rate": "OECD / INE LFS, 15-64",
    "employment_rate": "OECD / INE LFS, 15-64",
    "trade_balance": "Eurostat international trade, Portugal, world partner (community concept)",
    "debt_gdp": "Eurostat EDP notification, general government gross debt (Maastricht)",
    "deficit": "Eurostat EDP notification, general government net lending/borrowing",
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
        if not ser.get("label") or re.search(r"confirmed|placeholder|inferred|probe|todo|Austria|Belgi|\bAT\b|\bBE\b", ser["label"], re.I):
            problems.append("label missing or carries internal or template wording")
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
    ecb = s.get("ecb_rate", {}).get("points", [])
    odd = [(p, v) for p, v in ecb if abs(round(v * 100) - v * 100) > 1e-6 or round(v * 100) % 5]
    res("FAIL" if odd else "PASS", "ECB rate on a 5bp grid", f"{odd[:2]}")
    if ecb:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(ecb[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "ECB rate is current (at most one month behind)",
            f"last month {ecb[-1][0]} at {ecb[-1][1]}%, {lag} month(s) behind")
    fx = d.get("fx_to_usd") or {}
    # DEXUSEU is US$ per euro, so the rate is around 0.8 to 1.6 and multiplies.
    # A range alone cannot catch an inverted rate (0.89 is inside the euro's
    # real 0.83..1.60 history), so also require US$ per euro to have averaged
    # above 1.0 since 2015, which an inverted (euro per US$) series cannot.
    recent = [v for p, v in fx.get("history") or [] if str(p) >= "2015-01"]
    fx_ok = (fx.get("pair") == "EUR/USD" and fx.get("direction") == "multiply"
             and 0.8 < (fx.get("rate") or 0) < 1.6 and recent and sum(recent) / len(recent) > 1.0
             and abs((fx.get("rate") or 0) / recent[-1] - 1) < 0.05)
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block (US$ per euro, multiply, not inverted)",
        f"{fx.get('rate')} as of {fx.get('as_of')}; mean since 2015 {round(sum(recent) / len(recent), 3) if recent else None}")
    gl, gr = s.get("gdp_level", {}).get("points", []), s.get("gdp_real", {}).get("points", [])
    if gl and gr:
        res("PASS" if gl[-1][0] == gr[-1][0] else "FAIL", "nominal and real GDP end in the same quarter",
            f"{gl[-1][0]} / {gr[-1][0]}")


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
        j = get(f"https://api.worldbank.org/v2/country/PRT/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def hicp():
        rows = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/PRT.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01",
            "text/csv").text))
        imf = {}
        for r in rows:
            if (r.get("INDEX_TYPE"), r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("HICP", "_T", "YOY_PCH_PA_PT") \
                    and r.get("OBS_VALUE"):
                imf[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
        rows = [(p, round(v - imf[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in imf]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "HICP YoY vs IMF HICP YoY, last 24 months",
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
        res("PASS" if rows and abs(w[1]) <= 3.0 else "FAIL", "GDP: four Eurostat quarters vs World Bank annual",
            f"{len(rows)} years: {rows} (tolerance 3)")

    def growth():
        der = pct(s["gdp_real"]["points"], 1)
        rows = [(p, round(v - der[p], 2)) for p, v in s["gdp_growth"]["points"][-16:] if p in der]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "gdp_growth vs change in real GDP levels",
            f"{len(rows)} quarters, largest gap {w} pp")

    def labour():
        ann = wb("SL.UEM.TOTL.ZS")
        mv = s["unemployment"]["points"]
        rows = []
        for y in sorted(ann)[-6:]:
            vs = [v for p, v in mv if p.startswith(f"{y}-")]
            if len(vs) == 12:
                rows.append((y, round(sum(vs) / 12 - ann[y], 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.0 else "FAIL", "Unemployment: monthly (annual mean) vs World Bank ILO",
            f"{len(rows)} years: {rows}; tolerance 1.0")

    def fiscal():
        sys.path.insert(0, ".")
        import imf_weo
        for key, ind in (("debt_gdp", imf_weo.DEBT), ("deficit", imf_weo.DEFICIT)):
            weo = dict(imf_weo.fetch("PRT", ind))
            ours = dict(s[key]["points"])
            common = sorted(set(weo) & set(ours))[-3:]
            rows = [(y, round(ours[y] - weo[y], 2)) for y in common]
            w = worst(rows)
            res("PASS" if rows and abs(w[1]) <= 2.0 else "FAIL", f"{key}: Eurostat EDP vs IMF WEO",
                f"{rows} (tolerance 2.0pp)")

    def fx():
        hist = d["fx_to_usd"]["history"]
        ann = wb("PA.NUS.FCRF")      # euro per US$
        rows = []
        for y in sorted(ann)[-5:]:
            ms = [v for p, v in hist if p.startswith(f"{y}-")]
            if len(ms) >= 12:
                rows.append((y, round((1 / (sum(ms) / len(ms))) / ann[y] * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.5 else "FAIL", "FX: inverse of US$ per euro vs World Bank euro per US$",
            f"{len(rows)} years: {rows} (tolerance 1.5)")

    def trade():
        hist = dict(d["fx_to_usd"]["history"])
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/PRT.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        rows = []
        for p, v in s["trade_balance"]["points"][-12:]:
            if ("XG", p) in usd and ("MG", p) in usd and p in hist:
                rows.append((p, round(v * hist[p]), round(usd[("XG", p)] - usd[("MG", p)])))
        res("INFO", "Trade balance: Eurostat (US$ at month's rate) vs IMF ITG, US$m",
            f"{rows[-6:]}  (community vs national concept; read, not scored)")

    for name, fn in (("HICP cross-check", hicp), ("GDP cross-check", gdp), ("growth check", growth),
                     ("labour cross-check", labour), ("fiscal cross-check", fiscal), ("FX cross-check", fx),
                     ("trade comparison", trade)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with INE / the Banco de Portugal / Eurostat by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<20} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-pt.json"
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
