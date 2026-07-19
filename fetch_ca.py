"""Fetch Canada economic series and write data-ca.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ca.py
Sources: FRED (free key required: fred.stlouisfed.org), World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series' own FRED page before wiring in):
- gdp_level (NGDPSAXDCCAQ) / gdp_real (NGDPRSAXDCCAQ): IMF IFS quarterly,
  seasonally adjusted, confirmed live through Q1 2026 (next release Jul 6 2026).
- unemployment (LRUNTTTTCAM156S): confirmed live, Jan 1955 to Apr 2026.
- FIXED IN 7.6.4: Canada has NO live legacy-mirror CPI series on FRED --
  both obvious mirrors (CPALCY01CAM661N, CPALTT01CAM659N) stopped updating
  around Mar 2025, the same systemic failure as Japan's and India's CPI:
  FRED's OECD "MEI" vintage CPI family was discontinued en masse around
  that date. Replaced with a live query against OECD's own SDMX prices
  system (DSD_PRICES@DF_PRICES_ALL) -- same fix, same caveat as Japan's:
  the query structure is sourced from OECD's own generated example query,
  not guessed, but hasn't been personally executed end-to-end -- check
  the Actions log on first run.
- overnight_rate (IRSTCI01CAM156N): confirmed live, May 2026 (2.24%, closely
  tracking the Bank of Canada's 2.25% target). This is the market interbank
  overnight rate, not the BoC's own policy-rate series directly (no live
  FRED series carries that verbatim) -- labelled honestly as such.
- debt_gdp (GGGDTACAA188N) / deficit (GGNLBACAA188N): IMF WEO annual, both
  confirmed live through 2024 -- consistent with the same series family's
  healthy lag for Japan and India.
- trade_balance (CANXTNTVA01CXMLQ): OECD merchandise trade, quarterly,
  confirmed live through Q1 2026. Same "plain US dollars, not millions" unit
  bug as the Japan/Eurozone/India "667S" trade family -- confirmed via a raw
  value of -1,808,055,000.00000 for Q1 2026 -- so scale=1e-6 is applied here
  too. NOTE: no live monthly/quarterly exports/imports *components* were
  found to pair with this (the obvious ones are discontinued too), so only
  the combined balance is shown -- exports/imports breakdown is a known gap.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for the other countries. Best-effort.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_level": ("NGDPSAXDCCAQ", "q", "GDP, nominal, seasonally adjusted", "$m", None, 1.0),
    "gdp_real": ("NGDPRSAXDCCAQ", "q", "Real GDP, seasonally adjusted", "$m", None, 1.0),
    "gdp_growth": ("NGDPRSAXDCCAQ", "q", "Real GDP growth, QoQ", "%", "qoq", 1.0),
    "unemployment": ("LRUNTTTTCAM156S", "m", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "overnight_rate": ("IRSTCI01CAM156N", "m", "Interbank overnight rate", "%", None, 1.0),
    "debt_gdp": ("GGGDTACAA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBACAA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "trade_balance": ("CANXTNTVA01CXMLQ", "q", "Trade balance, goods, $", "$m", None, 1e-6),
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


# ---- OECD business confidence (Canada) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
CA_AREAS = ("CAN",)
OECD_QUERIES = [
    f"{OECD_BASE}/CAN.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/CAN.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "CAN") not in CA_AREAS:
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

# ---- OECD live CPI (7.6.4) -- FRED has no live CPI series for Canada
# at all, so there's nothing to remove/replace here, just a genuine gap
# being filled. Same query structure as the Japan fix, sourced from OECD's
# own generated example query for DSD_PRICES@DF_PRICES_ALL, not personally
# executed end-to-end -- check the Actions log on first run.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io
    lag = 4 if freq == "Q" else 12
    for area in areas:
        # UNIT_MEASURE must match TRANSFORMATION: GY (year-on-year growth) only
        # exists under PA (percentage), while _Z (no transform / raw level)
        # exists under IX (index). Pairing GY with IX 404s -- confirmed against
        # OECD's own DF_PRICES_ALL dataflow, see the 7.6.11 diagnostic run.
        for unit_measure, trans_code, needs_yoy in (("PA", "GY", False), ("IX", "_Z", True)):
            url = (f"{OECD_PRICES_BASE}/{area}.{freq}.N.CPI.{unit_measure}._T.N.{trans_code}"
                  f"?format=csvfile&startPeriod=2015")
            try:
                r = requests.get(url, timeout=60,
                                 headers={"User-Agent": "economic-atlas/0.1"})
                print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} status={r.status_code}")
                r.raise_for_status()
            except Exception as exc:
                print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} request failed: {exc}")
                continue
            try:
                rows = {}
                reader = list(csv.DictReader(io.StringIO(r.text)))
                if reader:
                    print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} {len(reader)} CSV rows; "
                          f"columns: {list(reader[0].keys())}")
                else:
                    print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} 0 CSV rows; "
                          f"raw response (first 300 chars): {r.text[:300]!r}")
                for row in reader:
                    low = {k.upper(): (v or "") for k, v in row.items() if k}
                    if low.get("REF_AREA", area) != area:
                        continue
                    period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
                    if period and value:
                        try:
                            rows[period] = float(value)
                        except ValueError:
                            continue
                if not rows:
                    print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} 0 usable rows after "
                          f"filtering (REF_AREA/TIME_PERIOD/OBS_VALUE mismatch)")
                    continue
                pts = sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
                print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} SUCCESS: {len(pts)} points, "
                      f"{pts[0][0]} to {pts[-1][0]}")
                if not needs_yoy:
                    return pts
                return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                        for i in range(lag, len(pts)) if pts[i - lag][1]] or None
            except Exception as exc:
                print(f"  [oecd-cpi] {area}.{unit_measure}.{trans_code} parsing failed: {exc}")
                continue
    return None

# ---- World Bank (Canada) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/CAN/indicator/"
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


def main() -> int:
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
        ("cpi", lambda: fetch_oecd_cpi(("CAN",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
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

    try:
        with open("data-ca.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_meta = prev_full.get("new_points_meta")
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

    try:
        if key:
            fx_pts = fetch_fred("DEXCAUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "CAD/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) — "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-ca.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ca.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
