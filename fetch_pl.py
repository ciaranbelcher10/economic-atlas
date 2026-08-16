"""Fetch Poland economic series and write data-pl.json.

Run:  FRED_API_KEY=yourkey python3 fetch_pl.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
IMF World Economic Outlook (via FRED, for fiscal series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Poland build note: derived from fetch_tr.py (most recent non-OECD,
own-currency page at build time -- Poland itself IS an OECD member,
first in this batch, so every series below was individually verified
rather than assumed from the pattern) per the v2 country-build
framework. Poland is an EU member but not Eurozone (own currency, the
zloty) and not EEA/EFTA.

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (NGDPRSAXDCPLQ): CONFIRMED live, IMF International Financial
  Statistics, quarterly, seasonally adjusted, millions of chained zloty.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=POL): standard
  fetch_worldbank() mechanism, same raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family.
- unemployment (LRHUTTTTPLM156S): CONFIRMED live (through Oct 2025),
  OECD harmonized, seasonally adjusted, MONTHLY.
- bond_yield_10y (IRLTLT01PLM156N): CONFIRMED live (through Feb 2026,
  updated Mar 2026), OECD, 10-year government bond yield, monthly.
  Poland has this where Turkey/Indonesia did not -- included as a
  genuinely available series rather than skipped by habit.
- debt_gdp (GGGDTAPLA188N) / deficit (GGNLBAPLA188N): CONFIRMED live
  (through 2024, updated Apr 2025), IMF World Economic Outlook, general
  government, % of GDP, ANNUAL. Poland is an EU member and Eurostat's
  quarterly gov_10q_ggdebt dataset also genuinely covers it (confirmed
  via Eurostat's own release commentary, which explicitly discusses
  Poland's debt ratio) -- the IMF-WEO annual series was used instead
  for consistency with the fetch pipeline's simpler, already-proven
  code path, not because the Eurostat option doesn't exist.
- participation_rate / policy_rate / current_account: NOT included. No
  clean live source individually confirmed for any of these during this
  build (Poland IS an OECD member, so the standard participation-rate
  family was worth checking, but wasn't actually verified in this
  build's research pass) -- genuine, disclosed gaps, not guesses.
- fx_to_usd (CCUSMA02PLM618N): CONFIRMED live (through Feb 2026, OECD,
  monthly average, PLN per USD).
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for every other country on this site), REF_AREA=POL.
  Not individually executed end-to-end for Poland before this build --
  check the Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=POL. Best-effort, not
  individually confirmed.
- trade_balance: standard OECD merchandise trade, monthly -- not
  individually confirmed for Poland's specific data availability;
  best-effort, check the first Actions log.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=POL. Not individually confirmed for
  Poland's specific data availability -- standard World Bank annual lag
  applies.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_real": ("NGDPRSAXDCPLQ", "q", "Real GDP, current national prices, SA (IMF IFS)", "PLNm", None, 1.0),
    "gdp_level": ("NGDPSAXDCPLQ", "q", "Nominal GDP, current prices, SA (IMF IFS)", "PLNm", None, 1.0),
    "unemployment": ("LRHUTTTTPLM156S", "m", "Unemployment rate, 15+, SA (OECD harmonized)", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01PLM156N", "m", "10-year government bond yield (OECD)", "%", None, 1.0),
    "debt_gdp": ("GGGDTAPLA188N", "a", "General government gross debt, % of GDP (IMF WEO)", "%", None, 1.0),
    "deficit": ("GGNLBAPLA188N", "a", "General government net lending/borrowing, % of GDP (IMF WEO)", "%", None, 1.0),
    "fx_raw": ("CCUSMA02PLM618N", "m", "PLN per USD, average of daily rates (OECD)", "PLN", None, 1.0),
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


# ---- OECD business confidence (Poland) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/POL.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/POL.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "POL") != "POL":
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
# pointed at Poland.
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

# ---- World Bank (Poland) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/POL/indicator/"
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
            if name == "fx_raw":
                continue
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

        # gdp_growth: derived as QoQ from the real-GDP level series above.
        # NOTE: lag=1 is genuine quarter-on-quarter for quarterly data --
        # lag=4 (the old value) is YoY, which duplicated the separately-
        # computed gdpYoY frontend variable under a card titled "QoQ".
        # See the Switzerland Bug 6 writeup for the full diagnosis.
        if "gdp_real" in out["series"]:
            level_pts = out["series"]["gdp_real"]["points"]
            growth_pts = yoy_from_level(level_pts, 1)
            if growth_pts:
                out["series"]["gdp_growth"] = {
                    "label": "Real GDP growth, QoQ (derived from NGDPRSAXDCPLQ)",
                    "unit": "%", "freq": "quarters", "points": growth_pts,
                }
                print(f"  ok  gdp_growth      {len(growth_pts):>5} observations (derived QoQ)")

        try:
            sid, freq, _, _, _, _ = FRED_SERIES["fx_raw"]
            fx_pts = fetch_fred(sid, freq, key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "PLN/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")
            else:
                print("note  fx_to_usd: no observations returned")
        except Exception as exc:
            print(f"FAIL  fx_to_usd        {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("POL",), "M"),
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

    if "gdp_level" not in out["series"]:
        # NGDPSAXDCPLQ above (via FRED_SERIES) is now the primary source,
        # genuinely denominated in PLN -- matching gdp_real and the site's
        # local-currency-by-default convention. This World Bank USD series
        # is now only a fallback, clearly labeled as USD so the frontend's
        # isAlreadyUSD() guard (added this session) correctly skips
        # re-converting it if this fallback ever gets used.
        try:
            raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
            if not raw_gdp:
                raise ValueError("no usable response")
            scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD -- USD, "
                         "fallback: NGDPSAXDCPLQ unavailable this run)",
                "unit": "$m", "freq": "years", "points": scaled_gdp,
            }
            print(f"  ok  gdp_level (WB USD fallback) {len(scaled_gdp):>5} observations "
                  f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years)")
            if "gdp_level" in failures:
                failures.remove("gdp_level")
        except Exception as exc:
            failures.append("gdp_level")
            print(f"FAIL  gdp_level (WB USD fallback) {exc}")

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run, so a transient failure (e.g. FRED 429 rate-limiting)
    # doesn't permanently wipe good data from the live page. See the
    # Switzerland/Chile/Colombia Bug 7 writeup -- this only protects
    # against future data loss, applied here to close the same gap for
    # Poland.
    try:
        with open("data-pl.json") as f:
            _prev_for_merge = json.load(f)
    except Exception:
        _prev_for_merge = {}
    _prev_series = _prev_for_merge.get("series", {})
    carried_over = []
    for k, v in _prev_series.items():
        if k not in out["series"]:
            out["series"][k] = v
            carried_over.append(k)
    if carried_over:
        print(f"CARRIED OVER from previous run (failed this run, kept prior data rather than deleting it): {', '.join(carried_over)}")
    if not out.get("fx_to_usd") and _prev_for_merge.get("fx_to_usd"):
        out["fx_to_usd"] = _prev_for_merge["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-pl.json") as f:
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

    with open("data-pl.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-pl.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
