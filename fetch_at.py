"""Fetch Austria economic series and write data-at.json.

Run:  FRED_API_KEY=yourkey python3 fetch_at.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, Eurostat
(via free public API, for fiscal series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Austria build note: derived from fetch_de.py (most recent Eurozone-
member page at build time) per the v2 country-build framework. Austria
uses the euro like Germany, so no FX conversion step is needed (unlike
Turkey/Poland/Sweden/etc., which have their own currencies).

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (CLVMNACSCAB1GQAT): CONFIRMED live (Q1 1995 to Q1 2026),
  Eurostat, quarterly, seasonally adjusted. IMPORTANT: this is a
  DIFFERENT source family from Germany's gdp_real (NGDPRNSAXDCDEQ, IMF
  IFS) -- Austria's page was built around this Eurostat series
  specifically, matching Switzerland/Sweden's approach rather than
  Germany's. The exact unit convention (index vs. euro millions) was
  not independently re-confirmed against the live API -- check the
  first Actions run and reconcile the page's unit label if needed.
- gdp_level (CPMNACSCAB1GQAT or similar euro-denominated Eurostat
  series): NOT individually confirmed with a specific series ID during
  this build -- Germany's own gdp_level (NGDPSAXDCDEQ) is a different
  family again. Left as a genuine gap to verify on first real run;
  gdp_level will show sample data until this is resolved.
- unemployment (LRHUTTTTATM156S): CONFIRMED live (through Jan 2026),
  OECD harmonized, seasonally adjusted, monthly. Same LRHUTTTT family
  used successfully for Turkey/Indonesia/Poland/Sweden -- unlike
  Switzerland, where this exact family is discontinued, Austria's is
  live. Individually confirmed, not assumed.
- bond_yield_10y (IRLTLT01ATM156N): CONFIRMED live (through Feb 2026,
  updated Mar 2026), OECD, monthly.
- participation_rate (LRAC64TTATQ156S) / employment_rate
  (LREM64TTATQ156S): NOT individually re-confirmed against the live API
  during this build. Same naming pattern confirmed working for other
  OECD members (including Germany, this page's template), reused here
  on the strength of that consistency -- check the Actions log on first
  real run.
- debt_gdp / deficit (Eurostat gov_10dd_edpt1, geo=AT): same EDP
  notification table mechanism confirmed working for Germany (and
  Denmark/Sweden before that) -- covers all EU member states. Not
  individually re-executed against the live API for Austria
  specifically before this build.
- cpi (CP0000ATM086NEST): NOT individually confirmed with this exact
  series ID during this build -- Germany's equivalent
  (CP0000DEM086NEST) was reused as a naming-pattern guess. The page
  primarily relies on OECD's live CPI system (same convention as every
  other country here); this FRED series is only a fallback if that
  returns nothing. Check the Actions log on first real run.
- trade_balance (XTNTVA01ATM667S): NOT individually confirmed with this
  exact series ID during this build -- Germany's equivalent
  (XTNTVA01DEM667S) was reused as a naming-pattern guess, following the
  same '667S' OECD trade-balance family already proven for Canada/
  Australia/South Korea. Germany's own fetch script notes that an
  earlier Eurostat-direct trade approach (teiet010/teiet110) was
  removed because that dataset never supports individual member-state
  geo codes with a WORLD partner -- confirmed empty on every real run --
  so that approach was not attempted here either.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=AUT. Best-effort, not
  individually confirmed.
- fdi / current_account: NOT included via a dedicated fetch mechanism in
  this build -- Germany's own fetch_de.py doesn't fetch these either
  (they were not present in the reference script this was derived
  from). Genuine gap; the page's fdi/current_account panels will show
  sample data until a source is added.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "trade_balance": ("XTNTVA01ATM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
    "gdp_level": ("CPMNACSCAB1GQAT", "q", "Nominal GDP, current prices, SA (Eurostat)", "\u20acm", None, 1.0),
    "gdp_real": ("CLVMNACSCAB1GQAT", "q", "Real GDP, chain-linked volumes, SA (Eurostat)", "\u20acm", None, 1.0),
    "unemployment": ("LRHUTTTTATM156S", "m", "Unemployment rate, 15+, SA (OECD harmonized)", "%", None, 1.0),
    "participation_rate": ("LRAC64TTATQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTATQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01ATM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "cpi": ("CP0000ATM086NEST", "m", "HICP, all items, YoY", "%", "yoy", 1.0),
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


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=AT&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] AT status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] AT request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-AT")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] AT parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/AUT.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/AUT.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "AUT") != "AUT":
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

        # gdp_growth: derived from gdp_real (QoQ), since gdp_level has no
        # individually-confirmed series for Austria -- see build notes.
        if "gdp_real" in out["series"]:
            try:
                gpts = out["series"]["gdp_real"]["points"]
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

    # Austria uses the euro like Germany, so gdp_level/gdp_real/trade_balance
    # need no local-currency conversion -- fx_to_usd exists purely so the
    # Dollarise toggle can convert EUR -> USD when switched on. Mirrors
    # fetch_de.py's DEXUSEU pattern exactly (this was missing entirely
    # before -- Dollarise was permanently disabled on this page).
    try:
        if key:
            fx_pts = fetch_fred("DEXUSEU", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "EUR/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "multiply"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

                # DEXUSEU is USD per EUR. trade_balance above is sourced
                # from OECD's "667S" family, which is genuinely USD-
                # denominated regardless of the page's own currency (same
                # caveat documented in fetch_de.py) -- convert it to EUR
                # for consistency with every other currency figure on an
                # Austria page, rather than leaving it in USD.
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

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run, so a transient failure (e.g. FRED 429 rate-limiting)
    # doesn't permanently wipe good data from the live page. See the
    # Switzerland/Chile/Colombia Bug 7 writeup -- applied here to close
    # the same gap for Austria.
    try:
        with open("data-at.json") as f:
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
        with open("data-at.json") as f:
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

    with open("data-at.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-at.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
