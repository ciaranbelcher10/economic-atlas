"""Fetch Ireland economic series and write data-ie.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ie.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series' own FRED/OECD page before
wiring in -- v1.1.5 build):
- gdp_level (CPMNACNSAB1GQIE) / gdp_real (CLVMNACNSAB1GQIE): Eurostat via
  FRED, quarterly. CONFIRMED LIVE -- nominal through Q3 2025 (updated Dec
  2025), real through Q4 2025 (updated Mar 2026). Unlike Denmark, this
  build did NOT hit a dead-mirror problem -- Ireland's Eurostat-sourced
  quarterly national accounts are genuinely current. IMPORTANT CONTEXT,
  not a bug: Irish GDP is heavily distorted by multinational corporate
  activity (IP relocation, contract manufacturing) -- Eurostat's own
  release notes explicitly flag this. Most visibly, GDP jumped ~26% in a
  single quarter in Q4 2015 (widely nicknamed "leprechaun economics",
  driven by large firms redomiciling intellectual property assets to
  Ireland). This is real, correctly-reported data, not a fetch error --
  do not "smooth" or exclude it. Consider whether the page needs a visible
  caveat note near the GDP chart specifically, given how large and
  well-known this distortion is.
- bond_yield_10y (IRLTLT01IEM156N): CONFIRMED live, OECD Main Economic
  Indicators, monthly, through Feb 2026.
- unemployment (LRHUTTTTIEM156S): CONFIRMED live, OECD-harmonized,
  monthly, through Dec 2025. Unlike Denmark, no large divergence found
  between this and commonly-cited national figures during this build
  (~4.6-4.7% in both OECD and Trading Economics sources checked) -- but
  worth a spot-check against Ireland's CSO if this ever looks off.
- debt_gdp (GGGDTAIEA188N) / deficit (GGNLBAIEA188N): IMF WEO annual, via
  FRED. INFERRED BY NAMING PATTERN, NOT INDIVIDUALLY CONFIRMED -- same
  caveat as Denmark's build: this consistent naming convention
  (GGGDTA{cc}A188N / GGNLBA{cc}A188N) has been verified directly for
  Canada, Germany, Italy, Greece, Euro Area, and Denmark, and IMF WEO
  covers essentially every country, so this is well-evidenced -- but
  these two specific IDs were not individually pulled up for Ireland.
  CHECK THE FIRST REAL ACTIONS LOG for these two specifically. Do NOT be
  surprised by a large, real swing in this data around 2011-2015 --
  Ireland's debt/GDP genuinely peaked near 120% during the banking
  crisis/bailout period (2010-2013) and then fell sharply, partly from
  real fiscal consolidation and partly from the same GDP-denominator
  inflation described above (a lower debt/GDP ratio can reflect a bigger
  GDP number, not just less debt) -- both are real, this is not a bug.
- cpi: wired in directly via OECD's live SDMX prices system (same proven
  query structure already used for Japan/India/Canada/Australia/South
  Korea/Denmark), REF_AREA=IRL. Not individually executed end-to-end for
  Ireland before this build -- check the Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for every other country, REF_AREA=IRL.
  Best-effort.
- fx_to_usd (DEXUSEU): Ireland is a Eurozone member -- fetched directly,
  same pattern as Germany/France/Italy/Spain/Netherlands. (A prior build
  note here claimed this page instead shared a "pooled" rate fetched
  elsewhere in the pipeline; that claim was checked and found false --
  no such shared mechanism exists, and Dollarise was permanently
  disabled as a result. Fixed to fetch its own rate like every other
  Eurozone page actually does.)
- fdi / current_account: World Bank, same indicator codes already used
  for every other country (BX.KLT.DINV.WD.GD.ZS / BN.CAB.XOKA.GD.ZS),
  country=IRL. NOTE: Ireland's FDI figures can show extreme outlier
  values in some years (the same multinational-relocation effect that
  distorts GDP also shows up here, sometimes as triple-digit % of GDP
  swings) -- this is real, documented volatility specific to Ireland,
  not a fetch bug, but worth a sanity glance on first run given how
  unusual the magnitude can look compared to every other country on
  this site.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
# - participation_rate (LRAC64TTIEQ156S) / employment_rate (LREM64TTIEQ156S): OECD infra-annual labour-statistics FRED family, quarterly, ages 15-64. Same pattern confirmed live for Germany (pilot); inferred-by-pattern for Ireland -- not individually confirmed, check the first Actions log.
FRED_SERIES = {
    "gdp_level": ("CPMNACNSAB1GQIE", "q", "GDP, current prices (Eurostat)", "\u20acm", None, 1.0),
    "gdp_real": ("CLVMNACNSAB1GQIE", "q", "Real GDP, chained 2010 prices (Eurostat)", "\u20acm", None, 1.0),
    "unemployment": ("LRHUTTTTIEM156S", "m", "Unemployment rate, 15+, OECD-harmonized", "%", None, 1.0),
    "participation_rate": ("LRAC64TTIEQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTIEQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01IEM156N", "m", "10-year government bond yield", "%", None, 1.0),
}

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


# ---- debt_gdp / deficit (Ireland) -- FIX applied after the v1.1.5 real
# run: the inferred IMF WEO FRED series (GGGDTAIEA188N / GGNLBAIEA188N)
# returned a 400 Bad Request -- those IDs don't exist on FRED at all for
# Ireland. Replaced with the same live Eurostat query already CONFIRMED
# WORKING in that same run for Germany/France/Italy/Spain/Netherlands
# (gov_10dd_edpt1, geo=IE) -- the correct source for a Eurozone member
# anyway, not a fallback.
def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=IE&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] IE status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] IE request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-IE")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] IE parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None

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


# ---- OECD business confidence (Ireland) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
IE_AREAS = ("IRL",)
OECD_QUERIES = [
    f"{OECD_BASE}/IRL.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/IRL.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "IRL") not in IE_AREAS:
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
# Japan/India/Canada/Australia/South Korea/Denmark, pointed at Ireland.
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
                    print(f"  [oecd-cpi] {tag} 0 usable rows after filtering")
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
                        print(f"  [oecd-cpi] {tag} {gkey} YoY transform produced no points")
                        continue
                    print(f"  [oecd-cpi] {tag} {gkey} SUCCESS: {len(out)} "
                          f"points, {out[0][0]} to {out[-1][0]}")
                    return out
                print(f"  [oecd-cpi] {tag} all series variants stale or unusable")
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    return None

# ---- World Bank (Ireland) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/IRL/indicator/"
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
        ("cpi", lambda: fetch_oecd_cpi(("IRL",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
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

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-ie.json") as f:
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

    # fx_to_usd: Ireland is a Eurozone member. A prior build note here
    # claimed this page shared a "pooled" DEXUSEU rate fetched elsewhere
    # in the pipeline -- that claim was checked and is false: there is no
    # shared/pooled fx mechanism anywhere in the pipeline, and every other
    # Eurozone page (Germany/France/Italy/Spain/Netherlands) independently
    # fetches its own DEXUSEU-based rate into its own data-XX.json. This
    # was why Dollarise was permanently disabled on Ireland's page --
    # fx_to_usd was never actually being written. Fixed to match the
    # existing, verified pattern used everywhere else.
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
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) -- "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-ie.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ie.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
