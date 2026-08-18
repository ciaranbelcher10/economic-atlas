"""Fetch Australia economic series and write data-au.json.

Run:  FRED_API_KEY=yourkey python3 fetch_au.py
Sources: FRED (free key required: fred.stlouisfed.org), World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series' own FRED page before wiring in):
- gdp_level (NGDPSAXDCAUQ) / gdp_real (NGDPRSAXDCAUQ): IMF IFS quarterly,
  seasonally adjusted, confirmed live through Q1 2026.
- unemployment (LRUNTTTTAUQ156S): confirmed live, Q3 1966 to Q1 2026.
  Quarterly, not monthly -- ABS's own headline unemployment is monthly, but
  this FRED mirror is only quarterly; noted honestly in the chart explainer.
- FIXED IN 7.6.4: Australia has NO live legacy-mirror CPI series on FRED --
  same systemic failure as Japan/India/Canada: FRED's OECD "MEI" vintage
  CPI family was discontinued en masse around March 2025. Replaced with a
  live query against OECD's own SDMX prices system (DSD_PRICES@DF_PRICES_ALL),
  QUARTERLY not monthly -- OECD's own documentation for this dataflow
  states "data are available monthly for all the countries except for
  Australia and New Zealand (quarterly data)", matching the well-known
  fact that ABS's primary official CPI has always been quarterly (the
  newer monthly indicator since Oct 2022 is a supplementary series, not
  what this OECD dataflow carries). Same caveat as Japan/Canada: query
  structure sourced from OECD's own documentation, not personally executed
  end-to-end -- check the Actions log on first run.
- No live RBA cash rate series exists on FRED. The 10-year government bond
  yield (IRLTLT01AUM156N, confirmed live to May 2026) is used instead and
  honestly labelled as a bond yield, not the policy rate.
- debt_gdp (GGGDTAAUA188N) / deficit (GGNLBAAUA188N): IMF WEO annual, both
  confirmed live through 2024 -- consistent with the same series family's
  healthy lag for Japan, India and Canada.
- trade_balance (XTNTVA01AUM667S): OECD merchandise trade, monthly,
  confirmed live through Jan 2026. Same "plain US dollars, not millions"
  unit bug as the Japan/Eurozone/India/Canada "667S" trade family, so
  scale=1e-6 is applied here too. NOTE: the matching imports component
  (XTIMVA01AUQ667S) only showed confirmed data to Q4 2024 in verification,
  a full year stale relative to exports -- rather than pair a live exports
  series with a possibly-stale imports series, only the combined balance
  is shown; exports/imports breakdown is a known gap (same call made for
  Canada).
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
    "gdp_level": ("NGDPSAXDCAUQ", "q", "GDP, nominal, seasonally adjusted", "$m", None, 1.0),
    "gdp_real": ("NGDPRSAXDCAUQ", "q", "Real GDP, seasonally adjusted", "$m", None, 1.0),
    "gdp_growth": ("NGDPRSAXDCAUQ", "q", "Real GDP growth, QoQ", "%", "qoq", 1.0),
    "unemployment": ("LRUNTTTTAUQ156S", "q", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01AUM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "debt_gdp": ("GGGDTAAUA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBAAUA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "trade_balance": ("XTNTVA01AUM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
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


# ---- OECD business confidence (Australia) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
AU_AREAS = ("AUS",)
OECD_QUERIES = [
    f"{OECD_BASE}/AUS.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/AUS.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "AUS") not in AU_AREAS:
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

# ---- OECD live CPI (7.6.4) -- FRED has no live CPI series for Australia
# at all, so there's nothing to remove/replace here, just a genuine gap
# being filled. Same query structure as the Japan fix, sourced from OECD's
# own generated example query for DSD_PRICES@DF_PRICES_ALL, not personally
# executed end-to-end -- check the Actions log on first run.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io

    lag = 4 if freq == "Q" else 12
    # Staleness guard (8.3.0): a fetch that "succeeds" but returns a
    # discontinued series must be REJECTED, not shipped. Japan's pinned
    # national-methodology CPI in DF_PRICES_ALL ends June 2021 (the 2015=100
    # base was retired when Japan rebased to 2020=100 in Aug 2021), and the
    # old code happily served it as current -- the live site showed -0.5%
    # deflation for Japan in July 2026 when actual CPI was +1.5%.
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
            return 0.0  # unparseable period -> don't reject on age alone

    def to_yoy(pts):
        return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                for i in range(lag, len(pts)) if pts[i - lag][1]] or None

    def parse_groups(text: str, area: str, tag: str) -> dict:
        # Group rows by (METHODOLOGY, ADJUSTMENT) so a wildcard query that
        # returns several series variants doesn't get scrambled into one dict
        # (the pre-8.3.0 parser keyed on TIME_PERIOD alone, silently
        # overwriting one methodology's values with another's).
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
        # Pass 1: pinned national-methodology combos (verified working for
        # AU/CA/KR). Pass 2: wildcard METHODOLOGY and ADJUSTMENT -- for
        # countries where the pinned combo resolves to a discontinued base
        # series (Japan), ask the dataset for every variant it has and pick
        # the freshest. UNIT_MEASURE must still match TRANSFORMATION: GY
        # (year-on-year growth) pairs with PA (percentage), _Z (raw level)
        # pairs with IX (index); GY+IX 404s -- confirmed against
        # DF_PRICES_ALL, see the 7.6.12 diagnostic run.
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
                # Freshest last-period wins; longer history breaks ties.
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

# ---- World Bank (Australia) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/AUS/indicator/"
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
        ("cpi", lambda: fetch_oecd_cpi(("AUS",), "Q"),
         "CPI, all items, YoY, quarterly (OECD live prices system)", "%", "quarters"),
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
        with open("data-au.json") as f:
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
            fx_pts = fetch_fred("DEXUSAL", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "AUD/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "multiply",
                                     "history": fx_pts}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                      f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points)")

                to_local = lambda v: v / fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                            ser["unit"] = ser["unit"].replace("$", "$", 1)
                            ser["label"] = ser["label"].replace(", $ ", ", $ ") \
                                                        .replace(", $", ", $")
                            print(f"  ok  {tk:<16} converted {'$'}->{'$'} using {fx_rate}")
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) — "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-au.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-au.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
