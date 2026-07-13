"""Fetch US economic series and write data-us.json.

Run:  FRED_API_KEY=yourkey python3 fetch_us.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q', label, unit, transform None|'yoy'|'mom')
FRED_SERIES = {
    "gdp_level": ("GDP", "q", "GDP, nominal, seasonally adjusted annual rate", "$bn", None),
    "gdp_real": ("GDPC1", "q", "Real GDP, chained 2017 dollars, SAAR", "$bn", None),
    "gdp_growth": ("A191RL1Q225SBEA", "q", "Real GDP growth, QoQ annualised", "%", None),
    "productivity": ("OPHNFB", "q", "Nonfarm business output per hour, index", "index", None),
    "unemployment": ("UNRATE", "m", "Unemployment rate, SA", "%", None),
    "employment": ("EMRATIO", "m", "Employment-population ratio, SA", "%", None),
    "participation": ("CIVPART", "m", "Labor force participation rate, SA", "%", None),
    "cpi": ("CPIAUCSL", "m", "CPI, all items, YoY", "%", "yoy"),
    "cpi_mom": ("CPIAUCSL", "m", "CPI, all items, MoM", "%", "mom"),
    "core_cpi": ("CPILFESL", "m", "Core CPI (ex food & energy), YoY", "%", "yoy"),
    "fed_funds": ("FEDFUNDS", "m", "Effective federal funds rate", "%", None),
    "debt_gdp": ("GFDEGDQ188S", "q", "Federal debt, % of GDP", "%", None),
    "net_debt": ("GFDEBTN", "q", "Total federal public debt", "$m", None),
    "deficit": ("MTSDS133FMS", "m", "Federal surplus or deficit, monthly", "$m", None),
    "trade_balance": ("BOPGSTB", "m", "Trade balance, goods & services, SA", "$m", None),
    "exports": ("BOPTEXP", "m", "Exports, goods & services, SA", "$m", None),
    "imports": ("BOPTIMP", "m", "Imports, goods & services, SA", "$m", None),
}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    return f"{y}-{m:02d}" if freq == "m" else f"{y}-Q{(m - 1) // 3 + 1}"


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
    return points


def transform(points: list, kind: str | None) -> list:
    if kind not in ("yoy", "mom"):
        return points
    lag = 12 if kind == "yoy" else 1
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (USA) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/USA.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/USA.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "USA") != "USA":
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


# ---- World Bank (USA) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/USA/indicator/"
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
        with open("data-us.json") as f:
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
        for name, (sid, freq, label, unit, tf) in FRED_SERIES.items():
            try:
                points = transform(fetch_fred(sid, freq, key), tf)
                if not points:
                    raise ValueError("no observations")
                fr = "months" if freq == "m" else "quarters"
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

    out["new_points"] = {
        k: v["points"][-1][0] for k, v in out["series"].items()
        if k in previous and previous[k] != v["points"][-1][0]
    }
    if out["new_points"]:
        print("New data points: " + ", ".join(
            f"{k} ({p})" for k, p in out["new_points"].items()))

    with open("data-us.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-us.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
