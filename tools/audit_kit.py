"""Shared machinery for the v1.7.56 pre-launch audits (audit_pe, audit_hk,
audit_is, audit_pk). Generalised from tools/audit_eg.py, adding quarterly
periods. Each audit keeps its own EXPECT ranges, KNOWN_JUMPS, NOT_SERVED and
cross-checks; this module only holds what is identical across them.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
MAX_AGE = {"months": 210, "quarters": 260, "years": 800}
MIN_POINTS = {"months": 24, "quarters": 12, "years": 10}
RESULTS: list = []
IMF = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"


def res(status, name, detail=""):
    RESULTS.append((status, name, detail))
    print(f"{status:<5} {name}  {detail}")


def period_key(p):
    p = str(p)
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m:
        return int(m.group(1)) * 12 + int(m.group(2)) - 1
    m = re.fullmatch(r"(\d{4})-Q([1-4])", p)
    if m:
        return int(m.group(1)) * 4 + int(m.group(2)) - 1
    if re.fullmatch(r"\d{4}", p):
        return int(p)
    return None


def period_end(p):
    p = str(p)
    if re.fullmatch(r"\d{4}-\d{2}", p):
        y, m = divmod(period_key(p) + 1, 12)
        return datetime(y, m + 1, 1, tzinfo=timezone.utc)
    if re.fullmatch(r"\d{4}-Q[1-4]", p):
        y, q = divmod(period_key(p) + 1, 4)
        return datetime(y, q * 3 + 1, 1, tzinfo=timezone.utc)
    return datetime(int(p) + 1, 1, 1, tzinfo=timezone.utc)


def back(p, n):
    """The period n steps before p, in p's own frequency."""
    k = period_key(p) - n
    if re.fullmatch(r"\d{4}-\d{2}", p):
        return f"{k // 12}-{k % 12 + 1:02d}"
    if re.fullmatch(r"\d{4}-Q[1-4]", p):
        return f"{k // 4}-Q{k % 4 + 1}"
    return str(k)


def worst(rows, i=-1):
    return max(rows, key=lambda x: abs(x[i])) if rows else None


def get(url, accept=None):
    import requests
    h = dict(UA)
    if accept:
        h["Accept"] = accept
    r = requests.get(url, timeout=90, headers=h)
    r.raise_for_status()
    return r


def csv_rows(url):
    return list(csv.DictReader(io.StringIO(get(url, "text/csv").text)))


def run(name, fn):
    try:
        fn()
    except Exception as exc:
        res("FAIL", name, f"cross-check could not run: {exc}")


def structure(d, expect, known_jumps, not_served, internal, known_gaps=None):
    known_gaps = known_gaps or {}
    s = d.get("series", {})
    for key, why in not_served.items():
        res("FAIL" if key in s else "PASS", f"{key} not served", why if key not in s else "served: must not be")
    for key, (unit, freq, lo, hi, step) in expect.items():
        ser = s.get(key)
        if not ser:
            res("FAIL", f"{key} present")
            continue
        pts = ser.get("points") or []
        problems = []
        if ser.get("unit") != unit:
            problems.append(f"unit {ser.get('unit')} != {unit}")
        if ser.get("freq") != freq:
            problems.append(f"freq {ser.get('freq')} != {freq}")
        if not ser.get("label") or re.search(internal, ser["label"], re.I):
            problems.append("label missing or carries internal wording")
        if re.search("\u2014| -- ", ser.get("label", "")):
            problems.append("dash in label")
        keys = [period_key(str(p)) for p, _ in pts]
        if None in keys:
            problems.append("unparseable period")
        elif keys != sorted(set(keys)):
            problems.append("periods not ascending and unique")
        else:
            gaps = [pts[i][0] for i in range(1, len(keys)) if keys[i] - keys[i - 1] != 1]
            if gaps:
                miss = [back(pts[i][0], j) for i in range(1, len(keys)) for j in range(1, keys[i] - keys[i - 1])]
                unnamed = [p for p in miss if (key, p) not in known_gaps]
                if unnamed:
                    problems.append(f"{len(gaps)} gap(s), missing {unnamed[:8]}")
        nulls = [p for p, v in pts if not isinstance(v, (int, float))]
        if nulls:
            problems.append(f"non-numeric at {nulls[0]}")
        out = [(p, v) for p, v in pts if isinstance(v, (int, float)) and not lo <= v <= hi]
        if out:
            problems.append(f"{len(out)} value(s) outside {lo}..{hi}, e.g. {out[-1]}")
        if step and not nulls:
            jumps = [(pts[i][0], round(pts[i][1] - pts[i - 1][1], 2)) for i in range(1, len(pts))
                     if abs(pts[i][1] - pts[i - 1][1]) > step and (key, pts[i][0]) not in known_jumps]
            if jumps:
                problems.append(f"{len(jumps)} unnamed jump(s) over {step}: {jumps}")
        if len(pts) < MIN_POINTS[freq]:
            problems.append(f"only {len(pts)} points")
        if pts and (datetime.now(timezone.utc) - period_end(pts[-1][0])).days > MAX_AGE[freq]:
            problems.append(f"stale: ends {pts[-1][0]}")
        res("FAIL" if problems else "PASS", f"{key} structure and range",
            "; ".join(problems) or f"{len(pts)} pts {pts[0][0]}..{pts[-1][0]}, last {pts[-1][1]}")
    if "exports" in expect:
        tb, ex, im = (dict(s.get(k, {}).get("points", [])) for k in ("trade_balance", "exports", "imports"))
        bad = [p for p, v in tb.items() if p in ex and p in im and abs(ex[p] - im[p] - v) > 0.2]
        res("FAIL" if bad else "PASS", "trade balance = exports - imports", f"{len(bad)} mismatched month(s)")
        same = [p for p, v in ex.items() if p in im and v == im[p]]
        res("FAIL" if same else "PASS", "no month where imports equal exports exactly (a copied figure)",
            f"{same or 'none'}")
        exp, imp = s.get("exports", {}).get("points", []), s.get("imports", {}).get("points", [])
        if exp and imp:
            tbl = (s.get("trade_balance", {}).get("points") or [[None]])[-1][0]
            res("PASS" if exp[-1][0] == imp[-1][0] == tbl else "FAIL",
                "exports, imports and balance end in the same month", f"exports {exp[-1][0]}, imports {imp[-1][0]}")


def one_decimal(d, keys):
    for key in keys:
        pts = d["series"].get(key, {}).get("points", [])
        many = [v for _, v in pts[-36:] if round(v, 1) != v]
        res("FAIL" if many else "PASS", f"{key} at one decimal place", f"{len(many)} value(s) with more")


def bis_avg(area, cur):
    rows = csv_rows(f"https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.{area}.{cur}.A?format=csv")
    return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in rows
            if r.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", r["TIME_PERIOD"])}


def cpi_index_check(d, iso3):
    """The IMF's published y/y and m/m vs the change in its own all-items
    index: an identity, and a test that a rebased index joins cleanly."""
    s = d["series"]
    ix = {r["TIME_PERIOD"].replace("-M", "-"): float(r["OBS_VALUE"])
          for r in csv_rows(IMF + f"CPI/~/{iso3}.CPI._T.IX.M?c[TIME_PERIOD]=ge:2000-M01") if r.get("OBS_VALUE")}
    for key, lag, tol in (("cpi", 12, 0.15), ("cpi_mom", 1, 0.15)):
        got = [(p, round(v - (ix[p] / ix[back(p, lag)] - 1) * 100, 2)) for p, v in s[key]["points"]
               if p in ix and back(p, lag) in ix]
        recent = got[-24:]
        w = worst(recent)
        res("PASS" if recent and abs(w[1]) <= tol else "FAIL",
            f"{key}: IMF published rate vs change in the IMF index (last 24 months)",
            f"{len(recent)} months, largest gap {w} pp (tolerance {tol})")
        old = [g for g in got[:-24] if abs(g[1]) > tol]
        res("INFO", f"{key}: earlier months where the published rate and the index disagree", f"{len(old)}: {old[:6]}")


def wb_growth(iso3):
    j = get(f"https://api.worldbank.org/v2/country/{iso3}/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=200").json()
    return {x["date"]: x["value"] for x in j[1] if x["value"] is not None}


def wb_growth_check(d, iso3, tol=0.15):
    wb = wb_growth(iso3)
    got = [(p, round(v - wb[p], 2)) for p, v in d["series"]["gdp_growth"]["points"][-10:] if p in wb]
    w = worst(got)
    res("PASS" if got and abs(w[1]) <= tol else "FAIL", "gdp_growth vs World Bank published real growth",
        f"{len(got)} years, largest gap {w} pp (tolerance {tol})")


def annual_from_quarters(points):
    by = {}
    for p, v in points:
        by.setdefault(p[:4], []).append(v)
    return {y: sum(v) for y, v in by.items() if len(v) == 4}


def wb_growth_vs_quarters(d, iso3, tol):
    """World Bank annual real growth vs the change in the sum of the four
    served real-GDP quarters."""
    ann = annual_from_quarters(d["series"]["gdp_real"]["points"])
    wb = wb_growth(iso3)
    got = [(y, round((ann[y] / ann[str(int(y) - 1)] - 1) * 100 - wb[y], 2))
           for y in sorted(ann) if str(int(y) - 1) in ann and y in wb][-10:]
    w = worst(got)
    res("PASS" if got and abs(w[1]) <= tol else "FAIL", "World Bank annual growth vs four served quarters of real GDP",
        f"{len(got)} years, largest gap {w} pp (tolerance {tol})")


def yoy_identity(d, tol, n=20):
    """Published y/y real growth vs the change in the served real level."""
    s = d["series"]
    real = dict(s["gdp_real"]["points"])
    got = [(p, round(v - (real[p] / real[back(p, 4)] - 1) * 100, 2)) for p, v in s["gdp_growth_yoy"]["points"]
           if p in real and back(p, 4) in real][-n:]
    w = worst(got)
    res("PASS" if got and abs(w[1]) <= tol else "FAIL", "gdp_growth_yoy vs change in served real GDP",
        f"{len(got)} quarters, largest gap {w} pp (tolerance {tol})")


def fx_vs_bis(d, bis):
    """World Bank annual average vs the mean of BIS monthly averages."""
    by = {}
    for p, v in bis.items():
        by.setdefault(p[:4], []).append(v)
    wbx = dict(d["fx_to_usd"]["history"])
    got = [(y, round(wbx[y] / (sum(v) / len(v)) * 100 - 100, 2)) for y, v in by.items()
           if len(v) == 12 and y in wbx and y >= "2018"]
    w = worst(got)
    res("PASS" if got and abs(w[1]) <= 1.0 else "FAIL", "FX: World Bank annual vs mean of BIS monthly averages",
        f"{got} (tolerance 1%)")


def itg_usd(iso3):
    usd = {}
    for r in csv_rows(IMF + f"ITG/~/{iso3}.*.*.M?c[TIME_PERIOD]=ge:2024-M01"):
        if r.get("UNIT") == "USD" and r.get("OBS_VALUE"):
            usd[(r.get("INDICATOR"), r["TIME_PERIOD"].replace("-M", "-"))] = float(r["OBS_VALUE"]) / 1e6
    return usd


def trade_vs_usd(d, usd, rate, tol, flows=(("exports", "XG"), ("imports", "MG")), what="the IMF's own US$"):
    """Local-currency trade / the conversion rate = an independent US$ figure."""
    s = d["series"]
    rows = []
    for k, ind in flows:
        for p, v in s[k]["points"][-6:]:
            if (ind, p) in usd and p in rate and usd[(ind, p)]:
                rows.append((k, p, round(v / rate[p] / usd[(ind, p)] * 100 - 100, 3)))
    w = worst(rows)
    res("PASS" if rows and abs(w[2]) <= tol else "FAIL", f"Trade: local currency / conversion rate = {what}",
        f"{len(rows)} comparisons, largest gap {w} % (tolerance {tol})")


def spot_sheet(d, expect, official):
    print("\n== SPOT-CHECK SHEET (compare each latest value with the publisher by eye)")
    for key in expect:
        ser = d["series"].get(key)
        if ser:
            p, v = ser["points"][-1]
            print(f"  {key:<16} {p:>8}  {v:<14} {ser['unit']:<5} -> {official.get(key, 'source named in label')}")


def fx_history_sheet(d, scale, glyph):
    """The whole FX history in the page's own terms (US$ per `scale` units),
    so the floor year can be chosen from evidence (fx_config.SERIES_START)."""
    hist = (d.get("fx_to_usd") or {}).get("history") or []
    print(f"\n== FX HISTORY (US$ per {glyph}{scale:,}): pick the first market-rate year")
    step = 6 if hist and re.fullmatch(r"\d{4}", str(hist[0][0])) else 12
    for i in range(0, len(hist), step):
        print("  " + "   ".join(f"{p} {scale / v:,.4g}" for p, v in hist[i:i + step] if v))


def finish():
    fails = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS) - len(fails)} PASS/INFO, {len(fails)} FAIL")
    return 1 if fails else 0
