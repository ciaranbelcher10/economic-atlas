"""Fetch Mexico economic series and write data-mx.json.

Run:  FRED_API_KEY=yourkey python3 fetch_mx.py
Sources: FRED (free key required), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (desk-research checked against each series' own FRED/OECD
page before wiring in -- NOT a live end-to-end run, so treat every one of
these as "expected to work, confirm in the first Actions log", per the
same discipline as every other country):

- gdp_level (NGDPSAXDCMXQ) and gdp_real (NGDPRSAXDCMXQ): unlike Israel,
  both of these were checked directly and are LIVE -- Q1 1993 to Q1 2026,
  still updating. This means, unlike Israel, Mexico should get a working
  "Make it real" toggle from day one.
- fx_to_usd (DEXMXUS): checked directly, live daily H.10 series, last
  observation within days of the check. Unlike Israel's shekel, the peso
  has a confirmed daily FRED mirror, so Dollarise should work properly too.
- unemployment (LRUNTTTTMXQ156S): quarterly, not monthly -- Mexico's
  OECD-mirrored monthly unemployment series looked annual-only/stale on
  inspection, so this quarterly series was used instead as the live option.
- bond_yield_10y (IRLTLT01MXM156N): checked directly, monthly, live
  through Feb 2026 as of the check.
- debt_gdp / deficit (GGGDTAMXA188N / GGNLBAMXA188N): follow the same
  IMF WEO annual naming convention already confirmed working for every
  other country (just the country-code segment swapped to MX) -- not
  individually opened and checked the way GDP/FX/bond yield were above,
  so if these come back FAIL in the log, that's why.
- trade_balance (XTNTVA01MXQ667S): same OECD merchandise-trade quarterly
  convention as every other country.
- cpi: wired in via OECD's live SDMX prices system (DSD_PRICES@DF_PRICES_ALL),
  the same fix already proven for Japan/India/Canada/Australia/South
  Korea/Israel, rather than assuming a FRED mirror is current.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for every other country.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
# - participation_rate (LRAC64TTMXQ156S) / employment_rate (LREM64TTMXQ156S): OECD infra-annual labour-statistics FRED family, quarterly, ages 15-64. Same pattern confirmed live for Germany (pilot); inferred-by-pattern for Mexico -- not individually confirmed, check the first Actions log.
FRED_SERIES = {
    "gdp_level": ("NGDPSAXDCMXQ", "q", "GDP nominal, SA", "$m", None, 1.0),
    "gdp_real": ("NGDPRSAXDCMXQ", "q", "Real GDP, SA", "$m", None, 1.0),
    "unemployment": ("LRUNTTTTMXQ156S", "q", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "participation_rate": ("LRAC64TTMXQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTMXQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01MXM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "debt_gdp": ("GGGDTAMXA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBAMXA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "trade_balance": ("XTNTVA01MXQ667S", "q", "Trade balance, goods, $", "$m", None, 1e-6),
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
    return f"{y}-{m:02d}"


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
    for p, v in points:
        dedup[p] = v
    return sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])


def transform(points: list, kind: str | None) -> list:
    if kind not in ("yoy", "mom", "qoq"):
        return points
    lag = 12 if kind == "yoy" else 1
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


def gdp_growth_from_level(points: list) -> list:
    return [[points[i][0], round((points[i][1] / points[i - 1][1] - 1) * 100, 2)]
            for i in range(1, len(points)) if points[i - 1][1]]


# ---- OECD business confidence (Mexico) -- free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
MX_AREAS = ("MEX",)
OECD_QUERIES = [
    f"{OECD_BASE}/MEX.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/MEX.M.BCICP......?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=2000",
]


def fetch_oecd_bci() -> list | None:
    import csv
    import io
    for url in OECD_QUERIES:
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            print(f"  [oecd-bci] status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            print(f"  [oecd-bci] request failed: {exc}")
            continue
        try:
            rows = {}
            for row in csv.DictReader(io.StringIO(r.text)):
                low = {k.upper(): (v or "") for k, v in row.items() if k}
                if low.get("REF_AREA", "MEX") not in MX_AREAS:
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
            print(f"  [oecd-bci] {len(rows)} matching rows after filtering -- no usable data in this response")
        except Exception as exc:
            print(f"  [oecd-bci] parsing failed: {exc}")
            continue
    return None

# ---- OECD live CPI -- same fix proven for Japan/India/Canada/Australia/
# South Korea/Israel ----
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io

    lag = 4 if freq == "Q" else 12
    max_age_days = 460 if freq == "Q" else 370

    def period_age_days(period: str) -> float:
        try:
            if "-Q" in period:
                y, q = period.split("-Q")
                dt = datetime(int(y), int(q) * 3, 1, tzinfo=timezone.utc)
            else:
                y, m = period.split("-")[:2]
                dt = datetime(int(y), int(m), 1, tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except Exception:
            return 0.0

    def to_yoy(pts):
        return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                for i in range(lag, len(pts)) if pts[i - lag][1]] or None

    def parse_groups(text: str, area: str, tag: str) -> dict:
        reader = list(csv.DictReader(io.StringIO(text)))
        if reader:
            print(f"  [oecd-cpi] {tag} {len(reader)} CSV rows; "
                  f"columns: {list(reader[0].keys())}")
        else:
            print(f"  [oecd-cpi] {tag} 0 CSV rows; "
                  f"raw response (first 300 chars): {text[:300]!r}")
            return {}
        groups: dict = {}
        for row in reader:
            low = {k.upper(): (v or "") for k, v in row.items() if k}
            if low.get("REF_AREA", area) != area:
                continue
            period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
            if not (period and value):
                continue
            gkey = (low.get("METHODOLOGY", "?"), low.get("ADJUSTMENT", "?"))
            try:
                groups.setdefault(gkey, {})[period] = float(value)
            except ValueError:
                continue
        return groups

    for area in areas:
        attempts = (
            ("PA", "GY", False, "N", "N"),
            ("IX", "_Z", True, "N", "N"),
            ("PA", "GY", False, "", ""),
            ("IX", "_Z", True, "", ""),
        )
        for unit_measure, trans_code, needs_yoy, meth, adj in attempts:
            tag = f"{area}.{meth or '*'}.{unit_measure}.{trans_code}"
            url = (f"{OECD_PRICES_BASE}/{area}.{freq}.{meth}.CPI."
                   f"{unit_measure}._T.{adj}.{trans_code}"
                   f"?format=csvfile&startPeriod=2015")
            try:
                r = requests.get(url, timeout=60,
                                 headers={"User-Agent": "economic-atlas/0.1"})
                print(f"  [oecd-cpi] {tag} status={r.status_code}")
                r.raise_for_status()
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} request failed: {exc}")
                continue
            try:
                groups = parse_groups(r.text, area, tag)
                if not groups:
                    print(f"  [oecd-cpi] {tag} 0 usable rows after filtering "
                          f"(REF_AREA/TIME_PERIOD/OBS_VALUE mismatch)")
                    continue
                candidates = []
                for gkey, rows in groups.items():
                    pts = sorted([[p, v] for p, v in rows.items()],
                                 key=lambda x: x[0])
                    candidates.append((pts[-1][0], len(pts), gkey, pts))
                candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
                for last_period, n, gkey, pts in candidates:
                    age = period_age_days(last_period)
                    if age > max_age_days:
                        print(f"  [oecd-cpi] {tag} {gkey} REJECTED stale: "
                              f"{n} points ending {last_period} "
                              f"({age:.0f} days old, limit {max_age_days})")
                        continue
                    out = pts if not needs_yoy else to_yoy(pts)
                    if not out:
                        print(f"  [oecd-cpi] {tag} {gkey} YoY transform "
                              f"produced no points -- skipping")
                        continue
                    print(f"  [oecd-cpi] {tag} {gkey} SUCCESS: {len(out)} "
                          f"points, {out[0][0]} to {out[-1][0]}")
                    return out
                print(f"  [oecd-cpi] {tag} all series variants stale or "
                      f"unusable -- trying next combo")
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    return None

# ---- World Bank (Mexico) -- free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/MEX/indicator/"
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


def fetch_cpi_with_fallback() -> tuple[list | None, str]:
    """Try OECD live CPI first; if that fails (dead/stale/rate-limited),
    fall back to World Bank's annual CPI indicator rather than showing
    nothing at all -- same pattern proven working for Morocco."""
    pts = fetch_oecd_cpi(("MEX",), "M")
    if pts:
        return pts, "OECD live prices system"
    print("  [cpi] OECD attempt exhausted, falling back to World Bank annual CPI")
    pts = fetch_worldbank("FP.CPI.TOTL.ZG")
    if pts:
        return pts, "World Bank, annual"
    return None, ""


def main() -> int:
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": False,
        "series": {},
    }
    failures = []

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("WARN  no FRED_API_KEY set -- FRED series will be skipped.")
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

        if "gdp_level" in out["series"]:
            try:
                gpts = out["series"]["gdp_level"]["points"]
                growth = gdp_growth_from_level(gpts)
                if growth:
                    out["series"]["gdp_growth"] = {
                        "label": "Real GDP growth, QoQ (derived)", "unit": "%",
                        "freq": "quarters", "points": growth}
                    print(f"  ok  gdp_growth       {len(growth):>5} observations (derived)")
            except Exception as exc:
                print(f"FAIL  gdp_growth       {exc}")

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

    # CPI handled separately since it has a two-stage fallback (OECD, then
    # World Bank annual) rather than a single source -- OECD's own data was
    # observed rejected-as-stale or rate-limited on live runs, which
    # previously meant no CPI at all rather than falling back cleanly.
    try:
        cpi_points, cpi_source = fetch_cpi_with_fallback()
        if not cpi_points:
            raise ValueError("no usable response from OECD or World Bank")
        out["series"]["cpi"] = {
            "label": f"CPI, all items, YoY ({cpi_source})", "unit": "%",
            "freq": "months" if cpi_source.startswith("OECD") else "years",
            "points": cpi_points}
        print(f"  ok  cpi              {len(cpi_points):>5} observations "
              f"({cpi_points[0][0]} to {cpi_points[-1][0]}, via {cpi_source})")
    except Exception as exc:
        failures.append("cpi")
        print(f"FAIL  cpi              {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-mx.json") as f:
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
            fx_pts = fetch_fred("DEXMXUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "MXN/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide",
                                     "history": fx_pts}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                      f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points)")

                to_local = lambda v: v * fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                            print(f"  ok  {tk:<16} converted using {fx_rate}")
            else:
                print("note  fx_to_usd: no observations returned; check the log")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) -- "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-mx.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-mx.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
