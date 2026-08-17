"""Fetch Netherlands economic series and write data-nl.json.

Run:  FRED_API_KEY=yourkey python3 fetch_nl.py
Sources: FRED (free key required), OECD, Eurostat.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sixth individual Eurozone-member country page (Tier 2), derived from
Germany's structure (full monthly bond yield), since the Netherlands'
bond yield turned out to be unambiguously confirmed live monthly, unlike
Italy/Spain's ambiguous situation.

VERIFICATION NOTES:

- gdp_level (CPMNACSCAB1GQNL): checked directly, live nominal through
  Q1 2026. NOT the same naming family as Germany/France/Italy's GDP
  (no NGDPSAXDCNLQ was found for the Netherlands) -- this is the SAME
  Eurostat-QNA family the Eurozone AGGREGATE itself uses on this site
  (CPMNACSCAB1GQEA19), just with "NL" instead of "EA19".
- gdp_real: FIX (9.15.1) -- NAEXKP01NLQ657S was live and returning data, but the
  values (0.2-0.9) turned out to be a QoQ % growth rate, not a GDP level in
  euros, despite the label/unit metadata claiming otherwise. Site-wide
  yoyGDP() expects a level series and silently produced a nonsensical result
  (ratio of two small percentages). Switched to CLVMNACSCAB1GQNL, the
  chain-linked-volume ("real") counterpart of the CPMNACSCAB1GQNL nominal
  series already used for gdp_level here, following the same Eurostat-QNA
  naming family the Eurozone aggregate itself uses for real GDP
  (CLVMEURSCAB1GQEA19). Confirm this ID resolves and returns level-scale
  values (hundreds of thousands, matching gdp_level's magnitude) on the
  first live workflow run -- FRED is not reachable from this sandbox to
  verify in advance.
  A different (OECD MEI) naming family than gdp_level above -- the
  direct Eurostat-QNA analogue for real GDP was not confirmed to exist
  under the expected ID, so this confirmed-live alternative was used
  instead rather than guess.
- unemployment (LRHUTTTTNLM156N): checked directly, live monthly through
  Mar 2026. NOTE the suffix is "N" not "S" like every other Eurozone
  country's unemployment series on this site -- a different naming
  variant, not a typo.
- bond_yield_10y (IRLTLT01NLM156N): checked directly, live monthly
  through Feb 2026 -- confirmed unambiguously, unlike Italy/Spain where
  the monthly series was ambiguous or unconfirmed.
- debt_gdp / deficit: sourced via Eurostat (fetch_eurostat_govfinance),
  reusing the mechanism proven for the Eurozone aggregate and every
  other Eurozone country built so far, with geo="NL".
- trade_balance: via Eurostat's teiet010/teiet110 tables, same mechanism
  as debt_gdp/deficit -- with partner="WORLD" (total trade, including
  intra-EU) rather than the aggregate's "WRL_REST" (extra-area only).
  NOT confirmed to exist for this specific partner code before writing.
- cpi (CP0000NLM086NEST): guessed by extending the Eurozone aggregate's
  own FRED series naming pattern (CP0000EZ19M086NEST) with the
  Netherlands' country code -- NOT confirmed to exist, same caveat as
  every other Eurozone country built so far.
- business_confidence: OECD BCICP, area NLD, same fallback pattern as
  every other country.
- fx_to_usd (DEXUSEU): same series and direction as every other Eurozone
  country built so far -- the euro is worth more than a dollar, so
  converting a raw-USD-sourced series into local currency means dividing
  by the rate, not multiplying, rather than the "* fx_rate" pattern used
  for MXN/BRL/ZAR. Getting this backwards would produce a plausible-
  looking but ~15-20% wrong number, not an obviously-broken one.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# - participation_rate (LRAC64TTNLQ156S) / employment_rate (LREM64TTNLQ156S): OECD infra-annual labour-statistics FRED family, quarterly, ages 15-64. Same pattern confirmed live for Germany (pilot); inferred-by-pattern for Netherlands -- not individually confirmed, check the first Actions log.
FRED_SERIES = {
    "trade_balance": ("XTNTVA01NLM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
    "gdp_level": ("CPMNACSCAB1GQNL", "q", "GDP nominal, SA", "\u20acm", None, 1.0),
    "gdp_real": ("CLVMNACSCAB1GQNL", "q", "Real GDP, chain-linked volume, SA", "\u20acm", None, 1.0),
    "unemployment": ("LRHUTTTTNLM156N", "m", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "participation_rate": ("LRAC64TTNLQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTNLQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01NLM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "cpi": ("CP0000NLM086NEST", "m", "HICP, all items, YoY", "%", "yoy", 1.0),
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


# ---- OECD business confidence (Netherlands) ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
NL_AREAS = ("NLD",)
OECD_QUERIES = [
    f"{OECD_BASE}/NLD.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/NLD.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "NLD") not in NL_AREAS:
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


# ---- Eurostat, reusing the exact mechanism proven for the Eurozone
# aggregate, parameterized by geo="NL" instead of the bloc codes ----
EUROSTAT_STATS_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _parse_jsonstat(text: str, tag: str) -> list | None:
    import json as jsonlib
    data = jsonlib.loads(text)
    if "dimension" not in data or "time" not in data.get("dimension", {}):
        print(f"  [{tag}] response has no time dimension; top-level keys: "
              f"{list(data.keys())}")
        return None
    for dname, dim in data["dimension"].items():
        if dname == "time" or not isinstance(dim, dict):
            continue
        idx = dim.get("category", {}).get("index", {})
        if isinstance(idx, dict) and len(idx) > 1:
            print(f"  [{tag}] dimension {dname!r} has {len(idx)} categories "
                  f"({list(idx)[:5]}...) -- query is under-filtered, refusing "
                  f"to parse a multi-series response")
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
              f"value type={type(value)}, size={data.get('size')}, "
              f"dim order={data.get('id')}")
        return None
    pts = sorted([[p, v] for p, v in points.items()], key=lambda x: x[0])
    print(f"  [{tag}] SUCCESS: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return pts


def fetch_eurostat_unemployment() -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/une_rt_m?format=JSON&lang=EN"
          f"&geo=NL&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-unemp] NL status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-unemp] NL request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, "eurostat-unemp-NL")
    except Exception as exc:
        print(f"  [eurostat-unemp] NL parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=NL&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] NL status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] NL request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-NL")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] NL parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


def _fetch_eurostat_teiet(dataset: str, stk_flow: str) -> list | None:
    """Same table family as the Eurozone aggregate, but partner=WORLD
    (total trade) instead of WRL_REST (extra-area only) -- see the
    module docstring for why. Unconfirmed until the first live run."""
    params = {"geo": "NL", "partner": "WORLD", "unit": "TVAL_SA",
              "stk_flow": stk_flow, "sitc06": "TOTAL"}
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{EUROSTAT_STATS_BASE}/{dataset}?format=JSON&lang=EN&{qs}&sinceTimePeriod=1999"
    tag = f"eurostat-trade-{stk_flow}-{dataset}-NL"
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-trade] {stk_flow} {dataset} NL status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-trade] {stk_flow} {dataset} NL request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, tag)
    except Exception as exc:
        print(f"  [eurostat-trade] {stk_flow} {dataset} NL parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


def fetch_eurostat_trade_pair() -> tuple[list | None, list | None]:
    exports = _fetch_eurostat_teiet("teiet010", "EXP")
    imports = _fetch_eurostat_teiet("teiet110", "IMP")
    return exports, imports


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
                        "label": "Nominal GDP growth, QoQ (derived)", "unit": "%",
                        "freq": "quarters", "points": growth}
                    print(f"  ok  gdp_growth       {len(growth):>5} observations (derived)")
            except Exception as exc:
                print(f"FAIL  gdp_growth       {exc}")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("debt_gdp", lambda: fetch_eurostat_govfinance("GD"),
         "General government gross debt, % of GDP (Eurostat)", "%", "years"),
        ("deficit", lambda: fetch_eurostat_govfinance("B9"),
         "General government net lending/borrowing, % of GDP (Eurostat)", "%", "years"),
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

    # unemployment: prefer the directly-confirmed FRED series (already
    # fetched above); if that failed for some reason, fall back to Eurostat.
    if "unemployment" not in out["series"]:
        try:
            pts = fetch_eurostat_unemployment()
            if pts:
                out["series"]["unemployment"] = {
                    "label": "Unemployment rate, SA (Eurostat)", "unit": "%",
                    "freq": "months", "points": pts}
                print(f"  ok  unemployment (eurostat fallback) {len(pts)} observations")
                if "unemployment" in failures:
                    failures.remove("unemployment")
        except Exception as exc:
            print(f"FAIL  unemployment (eurostat fallback) {exc}")

    # trade_balance now sourced via the FRED OECD '667S' series above
    # (same proven pattern as Canada/Australia/South Korea) and converted
    # from USD to EUR below -- the old Eurostat teiet010/teiet110 approach
    # was removed: that dataset only supports EA-aggregate geo codes and a
    # WRL_REST partner, never individual member states or a WORLD partner,
    # so it could never have worked (confirmed empty on every live run).

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-nl.json") as f:
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

    # Netherlands' own trade data is already sourced in EUR (via Eurostat)
    # directly above, so unlike Mexico/Brazil/South Africa there is NO
    # USD-to-local conversion needed for trade_balance/exports/imports --
    # they're already in the right currency. fx_to_usd exists purely so
    # the Dollarise toggle can convert EUR -> USD when switched on.
    try:
        if key:
            fx_pts = fetch_fred("DEXUSEU", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "EUR/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "multiply",
                                     "history": fx_pts}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                      f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points)")

                # DEXUSEU is USD per EUR, so USD -> EUR is a divide, not a
                # multiply (the opposite direction from the Mexico/Brazil/
                # South Africa pattern, where the FX series is local-per-USD).
                if "trade_balance" in out["series"]:
                    ser = out["series"]["trade_balance"]
                    if ser["unit"].strip().startswith("$"):
                        ser["points"] = [[p, round(v / fx_rate, 1)] for p, v in ser["points"]]
                        ser["unit"] = "\u20acm"
                        ser["label"] = ser["label"].replace(
                            "Trade balance, goods, $", "Trade balance, goods, total")
                        ser["label"] += " (OECD via FRED, converted to EUR)"
                        print(f"  ok  trade_balance    converted $->\u20ac using {fx_rate}")
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) -- "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-nl.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-nl.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
