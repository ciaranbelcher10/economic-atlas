"""Pre-launch audit of data-ro.json (v1.7.34, built before the probe from
tools/audit_cz.py). Nothing about Romania is shown to users until this passes
on a file written by the real pipeline and the spot-check against INS's, the
NBR's and Eurostat's releases matches.

    python3 tools/audit_ro.py                 # data-ro.json, with cross-checks
    python3 tools/audit_ro.py --offline FILE  # structure and plausibility only

Cross-checks as Czechia. Ranges are first estimates from Romania's history;
the 1990s (inflation above 150% in 1997, the leu redenomination in 2005) will
likely need SERIES_START decisions at the real run. Exit 1 on any FAIL.
"""

from __future__ import annotations

import csv, io, json, re, sys
from datetime import datetime, timezone

EXPECT = {
    # key: (unit, freq, low, high, max step between periods or None). First estimates; resize only for named events.
    "gdp_level": ("RONm", "quarters", 1e3, 1e6, None),          # about RON 470bn a quarter in 2026; tiny in new lei in the mid-1990s
    "gdp_real": ("RONm", "quarters", 1e4, 1e6, None),
    "gdp_growth": ("%", "quarters", -15, 10, None),
    "cpi": ("%", "months", -4, 40, 3.0),                      # HICP from 2002 (served start); about 14% in late 2022
    "cpi_mom": ("%", "months", -3, 6, None),
    "cpi_national": ("%", "months", -4, 35, 3.0),             # early 2002 still above 25% as disinflation continued             # INS CPI via the IMF, from 2002; -3.5% in May 2016 after VAT cuts (food June 2015, standard Jan 2016)
    "policy_rate": ("%", "months", 0, 12, 1.5),               # 10.25% in 2008; 1.25% in 2021; 7% from January 2023
    "bond_yield_10y": ("%", "months", 2, 12, 1.5),
    "business_confidence": ("index", "months", 85, 115, 4.0),
    "unemployment": ("%", "months", 3, 10, 1.0),             # served from 2009; 9.1-9.6% in 2010-13 after the 2009 recession
    "exports": ("RONm", "months", 1e4, 1.5e5, None),          # roughly RON 20bn to 45bn a month since 2015
    "imports": ("RONm", "months", 1e4, 1.5e5, None),
    "trade_balance": ("RONm", "months", -3e4, 5e3, None),      # a deficit every month
    "debt_gdp": ("%", "years", 10, 65, None),                 # about 12% in 2007, near 57% in 2025
    "deficit": ("%", "years", -11, 2, None),                  # about -9% in 2024
    "fdi": ("%", "years", -2, 12, None),
    "current_account": ("%", "years", -15, 10, None),           # about -13% in 2007; surpluses 1987-89 while the Ceausescu regime repaid foreign debt
}
KNOWN_GAPS = {
    # (key, first period after the gap): reason. A named, disclosed hole in the
    # source; never filled with an invented value. None known for Romania yet.
}

KNOWN_XCHECK = {
    # Cross-check years with a verified, named difference (tolerance unchanged).
    ("debt_gdp_weo", "2022"): "IMF debt follows GFSM 2014 and includes other accounts payable (trade credits); Maastricht EDP debt excludes them and values bonds at face value",
    ("debt_gdp_weo", "2023"): "as 2022: GFSM 2014 (IMF) vs Maastricht (Eurostat) definitions",
    ("debt_gdp_weo", "2024"): "as 2022: GFSM 2014 (IMF) vs Maastricht (Eurostat) definitions",
    ("unemployment_wb", "2020"): "Eurostat back-casts 2020 to the 2021 EU labour force survey method; the ILO's model does not",
}

KNOWN_JUMPS = {
    # Named events, checked 9 Oct 2026; tolerances unchanged.
    ("cpi", "2011-07"): "base effect a year after VAT rose from 19% to 24% in July 2010",
    ("cpi_national", "2011-07"): "base effect a year after VAT rose from 19% to 24% in July 2010",
    ("cpi_national", "2022-04"): "INS CPI 10.2% to 13.8% in April 2022 (energy and food prices)",
    ("cpi_national", "2023-04"): "INS CPI 14.5% to 11.2% in April 2023 (base effect)",
    ("bond_yield_10y", "2009-06"): "2009, Romania's IMF and EU support programme: thin 10-year market (yield 8.3% to 11.3%, then unchanged in July and August)",
    ("bond_yield_10y", "2009-10"): "2009 support programme: yield back from 11.0% to 9.1% as the market reopened",
}
NOT_SERVED = {"ecb_rate": "Romania is outside the euro area: the page shows the NBR's own rate (policy_rate)",
              "participation_rate": "no OECD 15-64 series for Romania; decide at the probe",
              "employment_rate": "no OECD 15-64 series for Romania; decide at the probe"}
MAX_AGE = {"months": 130, "quarters": 230, "years": 900}
OFFICIAL = {
    "gdp_level": "Eurostat namq_10_gdp / INS quarterly national accounts, current prices, SA, RON million",
    "gdp_real": "Eurostat namq_10_gdp, chain-linked volumes, SA, RON million",
    "gdp_growth": "INS quarterly GDP, q/q seasonally adjusted (the flash estimate headline)",
    "cpi": "Eurostat HICP for Romania, annual rate; NOT INS's headline (that is cpi_national)",
    "cpi_mom": "Eurostat HICP for Romania, monthly rate",
    "cpi_national": "INS consumer price index, annual rate (INS's headline; the NBR's 2.5% target measure; served from the IMF CPI dataset)",
    "policy_rate": "NBR monetary policy rate in force now (latest Board decision)",
    "bond_yield_10y": "NBR / ECB long-term interest rate for convergence, 10-year, monthly average",
    "unemployment": "Eurostat une_rt_m / INS, seasonally adjusted",
    "business_confidence": "OECD business confidence indicator",
    "exports": "Eurostat international trade, Romania, world partner, in RON",
    "imports": "Eurostat international trade, Romania, world partner, in RON",
    "trade_balance": "Eurostat, exports less imports, RON; INS's own balance (FOB/CIF, euro) differs",
    "debt_gdp": "Eurostat EDP notification, general government gross debt (Maastricht)",
    "deficit": "Eurostat EDP notification, general government net lending/borrowing",
    "fdi": "World Bank, FDI net inflows, % of GDP (NBR balance of payments)",
    "current_account": "World Bank, current account, % of GDP (NBR balance of payments)",
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
        if not ser.get("label") or re.search(r"confirmed|placeholder|inferred|probe|todo|Czech|Greece|Greek|Poland|Polish|China|Chinese|\bCZ\b|\bGR\b|\bEL\b|\bPL\b|\bCN\b", ser["label"], re.I):
            problems.append("label missing or carries internal or template wording")
        if re.search("\u2014| -- ", ser.get("label", "")): problems.append("dash in label")
        keys = [period_key(str(p)) for p, _ in pts]
        if None in keys: problems.append("unparseable period")
        elif keys != sorted(set(keys)): problems.append("periods not ascending and unique")
        else:
            gaps = [pts[i][0] for i in range(1, len(keys)) if keys[i] - keys[i - 1] != 1
                    and (key, pts[i][0]) not in KNOWN_GAPS]
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
    pr = s.get("policy_rate", {}).get("points", [])
    odd = [(p, v) for p, v in pr if abs(round(v * 100) - v * 100) > 1e-6 or round(v * 100) % 5]
    res("FAIL" if odd else "PASS", "Policy rate on a 5bp grid", f"{odd[:2]}")
    if pr:
        now = datetime.now(timezone.utc)
        lag = (now.year * 12 + now.month - 1) - period_key(pr[-1][0])
        res("PASS" if lag <= 1 else "FAIL", "Policy rate is current (at most one month behind)",
            f"last month {pr[-1][0]} at {pr[-1][1]}%, {lag} month(s) behind")
        res("PASS" if pr[0][0] == "2005-08" else "FAIL",
            "policy_rate starts at 2005-08 (NBR inflation targeting from August 2005; confirm against the BIS break note in the probe)", f"first {pr[0][0]}")
    fx = d.get("fx_to_usd") or {}
    # World Bank PA.NUS.FCRF is leu per US$, annual, and divides. An
    # inverted (US$ per leu) series would sit near 0.04, far outside 14..45.
    hist = fx.get("history") or []
    fx_ok = bool(fx.get("pair") == "RON/USD" and fx.get("direction") == "divide"
                 and 0.05 < (fx.get("rate") or 0) < 6 and hist and all(0.05 < v < 6 for p, v in hist)
                 and all(re.fullmatch(r"\d{4}", str(p)) for p, v in hist)
                 and fx.get("rate") == hist[-1][1]
                 and fx["rate"] > 2)   # lei per US$ has been above 2 since 2005; an inverted rate sits near 0.2
    res("PASS" if fx_ok else "FAIL", "fx_to_usd block (leu per US$, annual, divide, not inverted)",
        f"{fx.get('rate')} as of {fx.get('as_of')}; {len(hist)} years")
    ex, im, tb = (dict(s.get(k, {}).get("points", [])) for k in ("exports", "imports", "trade_balance"))
    bad = [p for p in tb if p in ex and p in im and abs(ex[p] - im[p] - tb[p]) > 0.15]
    ends = {k: (s.get(k, {}).get("points") or [[None]])[-1][0] for k in ("exports", "imports", "trade_balance")}
    res("PASS" if tb and not bad and len(set(ends.values())) == 1 else "FAIL",
        "trade: balance = exports - imports, all three end in the same month", f"ends {ends}; mismatches {bad[:3]}")
    for k in ("participation_rate", "employment_rate"):
        pts = s.get(k, {}).get("points") or [[None, None]]
        # No known break for Romania: print the depth so the real run shows it.
        # If a step FAILs, check the identity (1 - employment/participation).
        res("INFO", f"{k} history", f"first {pts[0][0]}, {len(pts)} quarters")
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
        j = get(f"https://api.worldbank.org/v2/country/ROU/indicator/{code}?format=json&per_page=200").json()
        return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}

    def run(name, fn):
        try:
            fn()
        except Exception as exc:
            res("FAIL", name, f"cross-check could not run: {exc}")

    def hicp():
        rows = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/ROU.*.*.*.M?c[TIME_PERIOD]=ge:2023-M01",
            "text/csv").text))
        imf, imf_cpi = {}, {}
        for r in rows:
            if (r.get("INDEX_TYPE"), r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("CPI", "_T", "YOY_PCH_PA_PT") \
                    and r.get("OBS_VALUE"):
                imf_cpi[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
            if (r.get("INDEX_TYPE"), r.get("COICOP_1999"), r.get("TYPE_OF_TRANSFORMATION")) == ("HICP", "_T", "YOY_PCH_PA_PT") \
                    and r.get("OBS_VALUE"):
                imf[r["TIME_PERIOD"].replace("-M", "-")] = float(r["OBS_VALUE"])
        rows = [(p, round(v - imf[p], 2)) for p, v in s["cpi"]["points"][-24:] if p in imf]
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 0.15 else "FAIL", "HICP YoY vs IMF HICP YoY, last 24 months",
            f"{len(rows)} months, largest gap {w} pp (tolerance 0.15)")
        # cpi_national IS the IMF series here, so compare it with the World Bank's
        # annual CPI inflation (FP.CPI.TOTL.ZG): mean of the twelve monthly
        # annual rates vs the annual-average rate; they differ a little by design.
        wbc = dict(wb("FP.CPI.TOTL.ZG"))
        nat = dict(s["cpi_national"]["points"])
        rows = []
        for y in sorted(wbc)[-4:]:
            ms = [nat.get(f"{y}-{m:02d}") for m in range(1, 13)]
            if all(v is not None for v in ms):
                rows.append((y, round(sum(ms) / 12 - wbc[y], 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.0 else "FAIL", "national CPI (IMF): mean annual rate vs World Bank annual CPI inflation",
            f"{rows} (tolerance 1.0pp)")

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

    def growth_published():
        # Eurostat publishes its own q/q rate (one decimal) beside the levels
        # (v1.7.24). It compares against the publisher's current figure, so
        # revisions do not raise false alarms (news reports the first release).
        j = get("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/namq_10_gdp"
                "?format=JSON&lang=EN&geo=RO&na_item=B1GQ&s_adj=SCA&unit=CLV_PCH_PRE&sinceTimePeriod=2022-Q1").json()
        idx = {v: k for k, v in j["dimension"]["time"]["category"]["index"].items()}
        pub = {idx[int(k)]: v for k, v in j["value"].items()}
        rows = [(p, round(v - pub[p], 2)) for p, v in s["gdp_growth"]["points"][-12:] if p in pub]
        w = worst(rows)
        # Eurostat rounds to one decimal, so up to 0.05 is rounding; 0.06 allows float noise.
        res("PASS" if rows and abs(w[1]) <= 0.06 else "FAIL", "gdp_growth vs Eurostat's published q/q rate",
            f"{len(rows)} quarters, largest gap {w} pp (tolerance 0.06, Eurostat rounds to 0.1)")

    def labour():
        ann = wb("SL.UEM.TOTL.ZS")
        mv = s["unemployment"]["points"]
        rows = []
        for y in sorted(ann)[-6:]:
            vs = [v for p, v in mv if p.startswith(f"{y}-")]
            if len(vs) == 12:
                rows.append((y, round(sum(vs) / 12 - ann[y], 2)))
        named = [r for r in rows if ("unemployment_wb", r[0]) in KNOWN_XCHECK]
        scored = [r for r in rows if r not in named]
        w = worst(scored)
        res("PASS" if scored and abs(w[1]) <= 1.0 else "FAIL", "Unemployment: monthly (annual mean) vs World Bank ILO",
            f"{len(scored)} years: {scored}; tolerance 1.0" + (f"; named, not scored: {named}" if named else ""))

    def fiscal():
        sys.path.insert(0, ".")
        import imf_weo
        for key, ind in (("debt_gdp", imf_weo.DEBT), ("deficit", imf_weo.DEFICIT)):
            got = imf_weo.fetch("ROU", ind)
            if not got:
                raise RuntimeError(f"IMF WEO returned no data for {ind} (source unreachable or rejected)")
            weo = dict(got)
            ours = dict(s[key]["points"])
            common = sorted(set(weo) & set(ours))[-3:]
            rows = [(y, round(ours[y] - weo[y], 2)) for y in common]
            named = [r for r in rows if (key + "_weo", r[0]) in KNOWN_XCHECK]
            rows = [r for r in rows if r not in named]
            w = worst(rows) if rows else ("none", 0)
            res("PASS" if (rows or named) and abs(w[1]) <= 2.0 else "FAIL", f"{key}: Eurostat EDP vs IMF WEO" + (f" (named, not scored: {named})" if named else ""),
                f"{rows} (tolerance 2.0pp)")

    def fx():
        hist = dict(d["fx_to_usd"]["history"])          # leu per US$, World Bank, annual

        def ecb(k):
            rows = csv.DictReader(io.StringIO(get(f"https://data-api.ecb.europa.eu/service/data/EXR/{k}?format=csvdata").text))
            return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows if r.get("OBS_VALUE")}
        nat, usd = ecb("M.RON.EUR.SP00.A"), ecb("M.USD.EUR.SP00.A")
        rows = []
        for y in sorted(hist)[-5:]:
            ms = [nat[m] / usd[m] for m in (f"{y}-{i:02d}" for i in range(1, 13)) if m in nat and m in usd]
            if len(ms) == 12:
                rows.append((y, round(hist[y] / (sum(ms) / 12) * 100 - 100, 2)))
        w = worst(rows)
        res("PASS" if rows and abs(w[1]) <= 1.5 else "FAIL",
            "FX: World Bank leu per US$ vs ECB reference rates (RON/EUR over USD/EUR)",
            f"{len(rows)} years: {rows} (tolerance 1.5%)")

    def trade():
        fx = dict(d["fx_to_usd"]["history"])
        itg = csv.DictReader(io.StringIO(get(
            "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/ROU.*.*.M?c[TIME_PERIOD]=ge:2024-M01",
            "text/csv").text))
        usd = {}
        for r in itg:
            if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
                usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
        rows = []
        for p, v in s["trade_balance"]["points"][-12:]:
            rate = fx.get(p[:4]) or fx.get(str(int(p[:4]) - 1))
            if ("XG", p) in usd and ("MG", p) in usd and rate:
                rows.append((p, round(v / rate), round(usd[("XG", p)] - usd[("MG", p)])))
        res("INFO", "Trade balance: Eurostat (US$ at the year's rate) vs IMF ITG, US$m",
            f"{rows[-6:]}  (community vs national concept; read, not scored)")

    for name, fn in (("HICP cross-check", hicp), ("GDP cross-check", gdp), ("growth check", growth), ("published growth check", growth_published),
                     ("labour cross-check", labour), ("fiscal cross-check", fiscal), ("FX cross-check", fx),
                     ("trade comparison", trade)):
        run(name, fn)


def spot_sheet(d):
    print("\n== SPOT-CHECK SHEET (compare each latest value with INS / the NBR / Eurostat by eye)")
    for key in EXPECT:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<20} {p:>8}  {v:<12} {ser['unit']:<5} -> {OFFICIAL.get(key, 'source named in label')}")
            print(f"  {'':<20} label: {ser['label']}")


def main(argv):
    offline = "--offline" in argv
    files = [a for a in argv[1:] if not a.startswith("--")]
    path = files[0] if files else "data-ro.json"
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
