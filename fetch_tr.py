"""Fetch Turkey economic series and write data-tr.json.

Run:  FRED_API_KEY=yourkey python3 fetch_tr.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
IMF World Economic Outlook (via FRED, for fiscal series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Turkey build note: derived from fetch_no.py (most recent own-currency,
non-Eurozone page at build time) per the v2 country-build framework.
Turkey is a full OECD member but neither an EU nor EEA/EFTA member --
this rules out the Eurostat quarterly fiscal datasets used for Norway,
so debt_gdp/deficit use the IMF-WEO annual FRED family instead (see
below; this family does NOT exist for every country -- individually
confirmed for Turkey specifically before wiring in, per the standing
rule against silently assuming it based on a pattern that failed for
Denmark/Ireland).

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (NGDPRSAXDCTRQ): CONFIRMED live (through Q1 2026), IMF
  International Financial Statistics, quarterly, seasonally adjusted,
  millions of Turkish lira. Used for gdp_growth (via YoY transform) and
  the "Real GDP growth" charts -- NOT the same series as gdp_level.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=TUR via
  MKTGDPTRA646NWDB): CONFIRMED live, current US$, annual. Same
  fetch_worldbank() mechanism and raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family.
- unemployment (LRHUTTTTTRM156S): CONFIRMED live (through Jan 2026,
  updated Mar 2026), OECD harmonized, seasonally adjusted, MONTHLY --
  unlike Norway, Turkey's monthly SA series is live, so freq is "m"
  here rather than falling back to quarterly.
- participation_rate (LRAC64TTTRQ156S): CONFIRMED live (through Q4
  2025), OECD infra-annual labour statistics, ages 15-64, seasonally
  adjusted, quarterly.
- employment_rate: NOT included. No clean live quarterly 15-64 SA
  series was found for Turkey during this build (only an annual,
  stale-through-2022 all-persons variant turned up) -- genuine gap,
  left out rather than guessed. Revisit if a better source surfaces.
- debt_gdp (GGGDTATRA188N) / deficit (GGNLBATRA188N): CONFIRMED live
  (through 2023, updated Apr 2025), IMF World Economic Outlook, general
  government, % of GDP, ANNUAL. This is the IMF-WEO FRED family that
  does NOT exist for every country (400 Bad Request for Denmark/Ireland
  per the v1.1.6 build) -- individually confirmed for Turkey
  specifically, not assumed. Annual only, unlike Norway/Denmark's
  quarterly Eurostat-sourced equivalents.
- bond_yield_10y / policy_rate: NOT included. Searched specifically;
  FRED's OECD short-term-rate mirror for Turkey (TURLOCOSTORSTM) is
  STALE (stopped Dec 2023) and no live 10-year-bond-yield FRED series
  was found. Genuine, disclosed gap -- see the page's own footer note.
- current_account: NOT included. FRED's OECD-sourced current-account
  series for Turkey (BPBLTT01TRA188S) is DISCONTINUED since 2013, with
  no live replacement found. Genuine, disclosed gap.
- trade_balance: World Bank / OECD merchandise trade, monthly -- NOT
  individually confirmed for Turkey's specific data availability during
  this build; standard best-effort fetch, check the first Actions log.
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for Norway/Japan/India/Canada/Australia/South Korea),
  REF_AREA=TUR. Cross-checked against FRED's separate CPI mirror
  (TURCPIALLMINMEI, confirmed live through Apr 2025) as supporting
  evidence. Not individually executed end-to-end for Turkey before this
  build -- check the Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=TUR. Best-effort, not
  individually confirmed.
- fx_to_usd (DEXTUUS... NOT a real FRED series -- Turkey uses
  CCUSMA02TRM618N, OECD monthly average, since a dedicated H.10 FRED
  series like Norway's DEXNOUS does not exist for the lira): CONFIRMED
  live via web_search. Fetched through fetch_fred() same as any other
  FRED series (freq "m"), NOT the H.10 daily path Norway/Denmark use.
  Direction "divide" (TRY-per-USD), since the lira floats independently
  and has depreciated sharply -- large year-on-year moves here are real,
  not a data error.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=TUR. Not individually confirmed for
  Turkey's specific data availability -- standard World Bank annual lag
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
    "gdp_real": ("NGDPRSAXDCTRQ", "q", "Real GDP, current national prices, SA (IMF IFS)", "TRYm", None, 1.0),
    "gdp_level": ("NGDPSAXDCTRQ", "q", "Nominal GDP, current prices, SA (IMF IFS)", "TRYm", None, 1.0),
    "unemployment": ("LRHUTTTTTRM156S", "m", "Unemployment rate, 15+, SA (OECD harmonized)", "%", None, 1.0),
    "participation_rate": ("LRAC64TTTRQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "debt_gdp": ("GGGDTATRA188N", "a", "General government gross debt, % of GDP (IMF WEO)", "%", None, 1.0),
    "deficit": ("GGNLBATRA188N", "a", "General government net lending/borrowing, % of GDP (IMF WEO)", "%", None, 1.0),
    "fx_raw": ("CCUSMA02TRM618N", "m", "TRY per USD, average of daily rates (OECD)", "TRY", None, 1.0),
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


def yoy_from_level(points: list, lag: int) -> list:
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (Turkey) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/TUR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/TUR.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "TUR") != "TUR":
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

# ---- OECD live CPI -- same proven query structure already used for
# Norway/Japan/India/Canada/Australia/South Korea, just pointed at Turkey.
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

# ---- World Bank (Turkey) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/TUR/indicator/"
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
    fx_period = None
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
                    "label": "Real GDP growth, QoQ (derived from NGDPRSAXDCTRQ)",
                    "unit": "%", "freq": "quarters", "points": growth_pts,
                }
                print(f"  ok  gdp_growth      {len(growth_pts):>5} observations (derived QoQ)")

        # gdp_level_annual / gdp_real_annual: NGDPSAXDCTRQ (nominal) and
        # NGDPRSAXDCTRQ (real) are genuine per-quarter flows, NOT
        # annualized -- the "GDP (Annual)" card was showing a single
        # quarter's value as if it were the full year (same root cause as
        # the Poland/Switzerland Bug 5 writeup). Do NOT alter the
        # underlying gdp_level/gdp_real series -- QoQ/YoY growth
        # calculations correctly depend on the raw quarterly level. Add
        # separate derived annual series instead.
        for src_key, dst_key, src_sid in (
            ("gdp_level", "gdp_level_annual", "NGDPSAXDCTRQ"),
            ("gdp_real", "gdp_real_annual", "NGDPRSAXDCTRQ"),
        ):
            if src_key in out["series"]:
                pts = out["series"][src_key]["points"]
                unit = out["series"][src_key]["unit"]
                if len(pts) >= 4:
                    annual_pts = [
                        [pts[i][0], round(sum(v for _, v in pts[i - 3:i + 1]), 1)]
                        for i in range(3, len(pts))
                    ]
                    out["series"][dst_key] = {
                        "label": f"GDP, trailing 4-quarter sum (derived from {src_sid})",
                        "unit": unit, "freq": "quarters", "points": annual_pts,
                    }
                    print(f"  ok  {dst_key:<16} {len(annual_pts):>5} observations (derived trailing-4Q sum)")

        # fx_to_usd: Turkey has no dedicated H.10-style daily FRED series
        # (unlike Norway's DEXNOUS) -- CCUSMA02TRM618N (OECD, monthly
        # average, TRY per USD) is the confirmed live alternative.
        try:
            sid, freq, _, _, _, _ = FRED_SERIES["fx_raw"]
            fx_pts = fetch_fred(sid, freq, key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "TRY/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")
            else:
                print("note  fx_to_usd: no observations returned")
        except Exception as exc:
            print(f"FAIL  fx_to_usd        {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("TUR",), "M"),
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

    # gdp_level: NGDPSAXDCTRQ above (via FRED_SERIES) is now the primary
    # source, genuinely denominated in TRY -- matching the site's
    # local-currency-by-default convention and consistent with gdp_real,
    # which was already correctly TRY. This replaces the previous
    # World-Bank-USD gdp_level: since it was already in USD, "Dollarise"
    # was converting an already-dollar figure through the TRY/USD rate a
    # second time, producing a badly wrong number. If NGDPSAXDCTRQ ever
    # fails, fall back to the old World Bank USD series -- clearly labeled
    # as USD so isAlreadyUSD() in the frontend's Dollarise logic (added
    # this same session) correctly skips re-converting it.
    if "gdp_level" not in out["series"]:
        try:
            raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
            if not raw_gdp:
                raise ValueError("no usable response")
            scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD -- USD, "
                         "fallback: NGDPSAXDCTRQ unavailable this run)",
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
    # Switzerland/Chile/Colombia Bug 7 writeup -- applied here to close
    # the same gap for Turkey.
    try:
        with open("data-tr.json") as f:
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
        with open("data-tr.json") as f:
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

    with open("data-tr.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-tr.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
