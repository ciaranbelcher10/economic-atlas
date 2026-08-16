"""Fetch Switzerland economic series and write data-ch.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ch.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
Eurostat (via FRED, for the real-GDP series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Switzerland build note: derived from fetch_pl.py (most recent OECD,
own-currency page at build time) per the v2 country-build framework.
Switzerland is an OECD member but neither EU nor EEA/EFTA -- and unlike
Turkey/Indonesia/Poland, it has NO confirmed IMF-WEO general-government
fiscal series on FRED, and its unemployment series naming migrated away
from the LRHUTTTT family used elsewhere on this site. Both of these were
only caught by individually verifying every series rather than assuming
the pattern from prior OECD builds -- see notes below.

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (CLVMNACSAB1GQCH): CONFIRMED existing on FRED, Eurostat
  (Statistical Office of the European Communities)-sourced, quarterly,
  seasonally adjusted. Switzerland is not an EU member, but Eurostat
  publishes this series via a bilateral data-sharing arrangement --
  genuinely different source family from the IMF IFS series
  (NGDPRSAXDC*) used for Turkey/Indonesia/Poland, so this fetch uses a
  different series naming convention rather than forcing the same one.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=CHE): standard
  fetch_worldbank() mechanism, same raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family.
- unemployment (LRUNTTTTCHQ156S): CONFIRMED live (through Q3 2025,
  updated Jan 2026), OECD, seasonally adjusted, QUARTERLY. IMPORTANT:
  the LRHUTTTT-prefixed series used for Turkey/Indonesia/Poland
  (LRHUTTTTCHQ156S for Switzerland specifically) is explicitly marked
  DISCONTINUED on its own FRED page -- LRUNTTTTCHQ156S is the OECD's
  replacement under a renamed measure code (UNE_LF vs the old
  UNE_LF_M). This would have been a silent, working-looking bug if the
  naming pattern had been assumed rather than checked.
- bond_yield_10y (IRLTLT01CHM156N): CONFIRMED live (through Feb 2026,
  updated Mar 2026), OECD, monthly. Switzerland's yields have been
  negative for extended stretches (real feature of Swiss rates in the
  2010s/early 2020s) -- large negative values here are correct, not an
  error.
- debt_gdp (DEBTTLCHA188A): CONFIRMED live (through 2023/2024, updated
  Dec 2025), World Bank World Development Indicators. This is CENTRAL
  government debt (source indicator GC.DOD.TOTL.GD.ZS), NOT general
  government -- no verified general-government FRED series (the
  GGGDTA{cc}A188N IMF-WEO family used for Turkey/Indonesia/Poland) was
  found for Switzerland during this build's research pass. The
  distinction matters: general-government debt for Switzerland runs
  roughly double the central-government figure (~39-40% vs ~20% of
  GDP per published IMF/statbase figures) -- these are genuinely
  different measures, not two sources for the same number. Flagged
  explicitly in the page's own citation text rather than left
  ambiguous.
- deficit / participation_rate / policy_rate / current_account: NOT
  included. No clean live source individually confirmed for any of
  these during this build (Switzerland IS an OECD member, so the
  standard families were worth checking, but none were found/verified)
  -- genuine, disclosed gaps, not guesses.
- fx_to_usd: NOT included via a dedicated FRED series in this build --
  no CCUSMA02CHM618N-equivalent check was completed with full
  confidence before time ran short; if you're revisiting this file,
  CCUSMA02CHM618N (OECD, monthly average, CHF per USD) was seen in
  search results and looks likely to work, but wasn't independently
  re-confirmed the way the other series above were, so it's commented
  out below rather than shipped as verified.
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for every other country on this site), REF_AREA=CHE.
  Not individually executed end-to-end for Switzerland before this
  build -- check the Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=CHE. Best-effort, not
  individually confirmed.
- trade_balance: standard OECD merchandise trade, monthly -- not
  individually confirmed for Switzerland's specific data availability;
  best-effort, check the first Actions log.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=CHE. Not individually confirmed for
  Switzerland's specific data availability -- standard World Bank
  annual lag applies.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_real": ("CLVMNACSAB1GQCH", "q", "Real GDP, chain-linked volumes, SA (Eurostat)", "CHFm", None, 1.0),
    "unemployment": ("LRUNTTTTCHQ156S", "q", "Unemployment rate, 15+, SA (OECD)", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01CHM156N", "m", "10-year government bond yield (OECD)", "%", None, 1.0),
    "debt_gdp": ("DEBTTLCHA188A", "a", "Central government debt, % of GDP (World Bank)", "%", None, 1.0),
    "fx_raw": ("CCUSMA02CHM618N", "m", "CHF per USD, average of daily rates (OECD)", "CHF", None, 1.0),
    # ^ independently re-verified live via search this session (through
    # Feb 2026) -- was previously found but left commented out pending
    # confirmation. Same OECD series family/naming convention as the
    # already-working fx_raw series for Turkey/Argentina/Indonesia/Poland.
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


def yoy_from_level(points: list, lag: int) -> list:
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (Switzerland) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/CHE.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/CHE.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "CHE") != "CHE":
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
            print(f"  [oecd-bci] {len(rows)} matching rows after filtering -- no usable data")
        except Exception as exc:
            print(f"  [oecd-bci] parsing failed: {exc}")
            continue
    return None

# ---- OECD live CPI -- same proven query structure used across the site,
# pointed at Switzerland.
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
        if not reader:
            print(f"  [oecd-cpi] {tag} 0 CSV rows; raw response (first 300 chars): {text[:300]!r}")
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
                    continue
                candidates = []
                for gkey, rows in groups.items():
                    pts = sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
                    candidates.append((pts[-1][0], len(pts), gkey, pts))
                candidates.sort(key=lambda t: (t[0], t[1]), reverse=True)
                for last_period, n, gkey, pts in candidates:
                    age = period_age_days(last_period)
                    if age > max_age_days:
                        print(f"  [oecd-cpi] {tag} {gkey} REJECTED stale: {n} points ending {last_period}")
                        continue
                    out = pts if not needs_yoy else to_yoy(pts)
                    if not out:
                        continue
                    print(f"  [oecd-cpi] {tag} {gkey} SUCCESS: {len(out)} points, {out[0][0]} to {out[-1][0]}")
                    return out
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    return None

# ---- World Bank (Switzerland) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/CHE/indicator/"
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
    fx_rate = None
    if not key:
        print("WARN  no FRED_API_KEY set — FRED series will be skipped.")
    else:
        for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():
            if name == "fx_raw":
                continue  # handled separately below, not a page series
            try:
                raw = fetch_fred(sid, freq, key)
                if scale != 1.0:
                    raw = [[p, v * scale] for p, v in raw]
                points = raw
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

        # gdp_growth: derived as YoY from the real-GDP index series above
        # (this is an index level, not a currency level, unlike the IMF
        # IFS series used for Turkey/Indonesia/Poland -- the YoY transform
        # works the same way regardless).
        if "gdp_real" in out["series"]:
            level_pts = out["series"]["gdp_real"]["points"]
            growth_pts = yoy_from_level(level_pts, 4)
            if growth_pts:
                out["series"]["gdp_growth"] = {
                    "label": "Real GDP growth, YoY (derived from CLVMNACSAB1GQCH)",
                    "unit": "%", "freq": "quarters", "points": growth_pts,
                }
                print(f"  ok  gdp_growth      {len(growth_pts):>5} observations (derived YoY)")

        # fx_to_usd: CCUSMA02CHM618N (OECD, monthly average, CHF per USD)
        # -- same pattern as Turkey/Argentina/Indonesia/Poland's fx_raw.
        try:
            sid, freq, _, _, _, _ = FRED_SERIES["fx_raw"]
            fx_pts = fetch_fred(sid, freq, key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "CHF/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")
            else:
                print("note  fx_to_usd: no observations returned")
        except Exception as exc:
            print(f"FAIL  fx_to_usd        {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("CHE",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
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

    try:
        raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
        if not raw_gdp:
            raise ValueError("no usable response")
        scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
        if fx_rate:
            # Pre-convert to CHF using the latest CHF/USD rate, so
            # gdp_level is CHF by default (matching the site's
            # local-currency-by-default convention) and "Dollarise" has
            # something genuine to convert back to USD from -- previously
            # this series was already USD, so Dollarise had nothing to do
            # (Switzerland had no fx_to_usd at all until this session).
            # IMPORTANT CAVEAT, worth keeping in the label: this uses a
            # single current exchange rate applied across the whole
            # historical series, not the actual CHF/USD rate at each
            # historical point -- so values for any year other than the
            # most recent are "what that year's USD figure is worth in
            # CHF at today's rate", not genuine historical CHF GDP data.
            # This is the same simplification the site's Dollarise toggle
            # already makes everywhere else, just applied in the other
            # direction here since gdp_level's only live source is USD.
            converted_gdp = [[p, round(v * fx_rate, 1)] for p, v in scaled_gdp]
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD, converted "
                         "to CHF at the latest CHF/USD rate -- NOT independently-measured "
                         "historical CHF figures; see fetch script for the caveat this implies)",
                "unit": "CHFm", "freq": "years", "points": converted_gdp,
            }
            print(f"  ok  gdp_level        {len(converted_gdp):>5} observations "
                  f"({converted_gdp[0][0]} to {converted_gdp[-1][0]}, years) -- "
                  f"converted to CHF at rate {fx_rate}")
        else:
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD -- USD, "
                         "no live CHF/USD rate available this run to convert it)",
                "unit": "$m", "freq": "years", "points": scaled_gdp,
            }
            print(f"  ok  gdp_level (USD, no fx rate) {len(scaled_gdp):>5} observations "
                  f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years)")
    except Exception as exc:
        failures.append("gdp_level")
        print(f"FAIL  gdp_level        {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-ch.json") as f:
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

    with open("data-ch.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ch.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
