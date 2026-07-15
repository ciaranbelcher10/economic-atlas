"""Fetch euro-area economic series and write data-ez.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ez.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q', label, unit, transform None|'yoy'|'mom', scale)
# scale multiplies the raw FRED value before any transform. Use this to correct
# unit mismatches at the source rather than patching displayed numbers downstream.
# The OECD '667S' goods-trade family (exports/imports) reports PLAIN US DOLLARS,
# not millions -- verified against FRED's own "Units" field on the series page --
# so scale=1e-6 converts it to $m to match the declared unit and the bnD/bnD0
# chart formatters (which assume $m and divide by 1000 for $bn).
FRED_SERIES = {
    "gdp_level": ("CPMNACSCAB1GQEA19", "q", "GDP, nominal, quarterly level", "\u20acm", None, 1.0),
    "gdp_real": ("CLVMEURSCAB1GQEA19", "q", "Real GDP, chained, quarterly level", "\u20acm", None, 1.0),
    "gdp_growth": ("CLVMEURSCAB1GQEA19", "q", "Real GDP growth, QoQ", "%", "qoq", 1.0),
    "cpi": ("CP0000EZ19M086NEST", "m", "HICP, all items, YoY", "%", "yoy", 1.0),
    "cpi_mom": ("CP0000EZ19M086NEST", "m", "HICP, all items, MoM", "%", "mom", 1.0),
    "ecb_rate": ("ECBDFR", "d", "ECB deposit facility rate", "%", None, 1.0),
    "exports": ("XTEXVA01EZM667S", "m", "Exports of goods, $", "$m", None, 1e-6),
    "imports": ("XTIMVA01EZM667S", "m", "Imports of goods, $", "$m", None, 1e-6),
}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    if freq == "a":
        return y
    if freq == "q":
        return f"{y}-Q{(m - 1) // 3 + 1}"
    return f"{y}-{m:02d}"  # monthly, and daily reduced to months


def fetch_fred(sid: str, freq: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    points = []
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        try:
            points.append([fred_period(o["date"], freq), float(o["value"])])
        except (KeyError, ValueError):
            continue
    points.sort(key=lambda p: p[0])
    dedup = {}
    for p, v in points:          # daily series reduce to last value per month
        dedup[p] = v
    return sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])


def transform(points: list, kind: str | None) -> list:
    if kind not in ("yoy", "mom", "qoq"):
        return points
    lag = 12 if kind == "yoy" else 1
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (USA) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
EZ_AREAS = ("EA20", "EA19", "XEA")
OECD_QUERIES = [
    f"{OECD_BASE}/EA20.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/EA19.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=2000",
]


def fetch_oecd_bci() -> list | None:
    import csv
    import io
    for url in OECD_QUERIES:
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            r.raise_for_status()
        except Exception:
            continue
        try:
            rows = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                low = {k.upper(): (v or "") for k, v in row.items() if k}
                if low.get("REF_AREA", "EA20") not in EZ_AREAS:
                    continue
                if low.get("MEASURE", "BCICP") != "BCICP":
                    continue
                if (low.get("FREQ") or low.get("FREQUENCY") or "M") != "M":
                    continue
                period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
                if period and value:
                    try:
                        rows[period] = float(value)
                    except ValueError:
                        continue
            if rows:
                return sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
        except Exception:
            continue
    return None


# ---- Eurostat live unemployment + government finance (7.6.9) -- rebuilt
# using Eurostat's "API Statistics" endpoint, which takes NAMED query
# parameters (geo=, sector=, unit=, etc.) rather than the SDMX 2.1 REST
# API's positional dot-path segments. This completely avoids the
# dimension-ORDER guessing that the previous version relied on -- a
# confirmed working example of this named-parameter style is documented
# directly in Eurostat's own API guide: .../data/reg_area3?format=JSON&
# geo=BE&unit=KM2&landuse=TOTAL&lang=EN&TIME=2025. Response format is
# JSON-stat, parsed generically below (all non-time dimensions are held
# fixed to a single value, so "time" is the only dimension that varies).
EUROSTAT_STATS_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _parse_jsonstat(text: str, tag: str) -> list | None:
    """Generic JSON-stat parser: extracts (period, value) pairs assuming
    every dimension except 'time' is fixed to a single filtered value."""
    import json as jsonlib
    data = jsonlib.loads(text)
    if "dimension" not in data or "time" not in data.get("dimension", {}):
        print(f"  [{tag}] response has no time dimension; top-level keys: "
              f"{list(data.keys())}")
        return None
    time_index = data["dimension"]["time"]["category"]["index"]
    pos_to_period = {v: k for k, v in time_index.items()}
    value = data.get("value")
    points = {}
    if isinstance(value, dict):
        for pos_str, val in value.items():
            try:
                pos = int(pos_str)
            except ValueError:
                continue
            if pos in pos_to_period and val is not None:
                points[pos_to_period[pos]] = float(val)
    elif isinstance(value, list):
        for pos, val in enumerate(value):
            if val is not None and pos in pos_to_period:
                points[pos_to_period[pos]] = float(val)
    if not points:
        print(f"  [{tag}] parsed JSON-stat but got 0 points; "
              f"value type={type(value)}, size={data.get('size')}")
        return None
    pts = sorted([[p, v] for p, v in points.items()], key=lambda x: x[0])
    print(f"  [{tag}] SUCCESS: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return pts


def fetch_eurostat_unemployment() -> list | None:
    for area in ("EA21", "EA20", "EA19"):
        url = (f"{EUROSTAT_STATS_BASE}/une_rt_m?format=JSON&lang=EN"
              f"&geo={area}&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA"
              f"&sinceTimePeriod=2000")
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            print(f"  [eurostat-unemp] {area} status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            print(f"  [eurostat-unemp] {area} request failed: {exc}")
            continue
        try:
            pts = _parse_jsonstat(r.text, f"eurostat-unemp-{area}")
            if pts:
                return pts
        except Exception as exc:
            print(f"  [eurostat-unemp] {area} parsing failed: {exc}; "
                  f"first 300 chars: {r.text[:300]!r}")
    return None


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    for area in ("EA20", "EA19", "EA21"):
        url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
              f"&geo={area}&sector=S13&unit=PC_GDP&na_item={na_item}"
              f"&sinceTimePeriod=2000")
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            print(f"  [eurostat-gov-{na_item}] {area} status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            print(f"  [eurostat-gov-{na_item}] {area} request failed: {exc}")
            continue
        try:
            pts = _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-{area}")
            if pts:
                return pts
        except Exception as exc:
            print(f"  [eurostat-gov-{na_item}] {area} parsing failed: {exc}; "
                  f"first 300 chars: {r.text[:300]!r}")
    return None


WB_URL = ("https://api.worldbank.org/v2/country/EMU/indicator/"
          "{code}?format=json&per_page=200")


def fetch_worldbank(code: str) -> list | None:
    r = requests.get(WB_URL.format(code=code), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    points = []
    for row in payload[1]:
        try:
            if row.get("value") is None:
                continue
            points.append([str(row["date"]), float(row["value"])])
        except (KeyError, ValueError, TypeError):
            continue
    points.sort(key=lambda p: p[0])
    return points or None


def load_previous() -> dict:
    try:
        with open("data-ez.json") as f:
            old = json.load(f)
        return {k: v["points"][-1][0]
                for k, v in old.get("series", {}).items() if v.get("points")}
    except Exception:
        return {}


def main() -> int:
    previous = load_previous()
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": False,
        "series": {},
    }
    failures = []

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("WARN  no FRED_API_KEY set — FRED series will be skipped.")
    else:
        for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():
            try:
                raw = fetch_fred(sid, freq, key)
                if scale != 1.0:
                    raw = [[p, v * scale] for p, v in raw]
                points = transform(raw, tf)
                if not points:
                    raise ValueError("no observations")
                fr = {"m": "months", "d": "months", "q": "quarters", "a": "years"}[freq]
                out["series"][name] = {"label": f"{label} ({sid})", "unit": unit,
                                       "freq": fr, "points": points}
                print(f"  ok  {name:<16} {len(points):>5} observations "
                      f"({points[0][0]} to {points[-1][0]}, {fr})")
            except Exception as exc:
                failures.append(name)
                print(f"FAIL  {name:<16} {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("unemployment", lambda: fetch_eurostat_unemployment(),
         "Unemployment rate, SA (Eurostat une_rt_m)", "%", "months"),
        ("debt_gdp", lambda: fetch_eurostat_govfinance("GD"),
         "General government gross debt, % of GDP (Eurostat gov_10dd_edpt1)", "%", "years"),
        ("deficit", lambda: fetch_eurostat_govfinance("B9"),
         "General government net lending/borrowing, % of GDP (Eurostat gov_10dd_edpt1)", "%", "years"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
    ]
    for name, fn, label, unit, fr in extras:
        try:
            points = fn()
            if not points:
                raise ValueError("no usable response")
            out["series"][name] = {"label": label, "unit": unit,
                                   "freq": fr, "points": points}
            print(f"  ok  {name:<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, {fr})")
        except Exception as exc:
            failures.append(name)
            print(f"FAIL  {name:<16} {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    if "exports" in out["series"] and "imports" in out["series"]:
        imp = dict(out["series"]["imports"]["points"])
        tb = [[p, round(x - imp[p], 1)]
              for p, x in out["series"]["exports"]["points"] if p in imp]
        if tb:
            out["series"]["trade_balance"] = {
                "label": "Trade balance, goods (exports minus imports)", "unit": "$m",
                "freq": "months", "points": tb}
            print(f"  ok  {'trade_balance':<16} {len(tb):>5} observations (derived)")

    try:
        with open("data-ez.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_meta = prev_full.get("new_points_meta")
    # migrating from the old pipeline (or a corrupted/missing meta file): back-date
    # everything to the last known-good run instead of "now", so turning this
    # tracking on (or recovering from a bad file) doesn't falsely flag every
    # series as freshly released.
    migrating = prev_meta is None
    backdate = prev_full.get("updated")
    prev_meta = prev_meta or {}
    now_iso = out["updated"]
    new_meta = {}
    for k, v in out["series"].items():
        period = v["points"][-1][0]
        prior = prev_meta.get(k)
        if prior and prior.get("period") == period:
            new_meta[k] = {"period": period, "first_seen": prior["first_seen"]}
        elif migrating and backdate:
            new_meta[k] = {"period": period, "first_seen": backdate}
        else:
            new_meta[k] = {"period": period, "first_seen": now_iso}
    out["new_points_meta"] = new_meta

    def _age_days(iso):
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - t).total_seconds() / 86400
        except Exception:
            return 999

    out["new_points"] = {k: m["period"] for k, m in new_meta.items()
                          if _age_days(m["first_seen"]) < 2}
    if out["new_points"]:
        print("Fresh (< 2 days old): " + ", ".join(
            f"{k} ({p})" for k, p in out["new_points"].items()))

    with open("data-ez.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ez.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
