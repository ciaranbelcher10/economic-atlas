"""Fetch Sweden economic series and write data-se.json.

Run:  FRED_API_KEY=yourkey python3 fetch_se.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
Eurostat (via free public API, for fiscal series and the real-GDP series).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sweden build note: derived from fetch_dk.py (most recent EU-member,
own-currency, Eurostat-fiscal page at build time) per the v2
country-build framework. Sweden is an EU member but not Eurozone (own
currency, the krona) -- same Eurostat EDP-notification-table mechanism
used for Denmark applies, just geo=SE instead of geo=DK.

VERIFICATION NOTES (checked against each series' own FRED/OECD page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- gdp_real (CLVMNACSCAB1GQSE): CONFIRMED existing on FRED, Eurostat
  (Statistical Office of the European Communities)-sourced, quarterly,
  seasonally adjusted. Uses the same Eurostat-via-FRED family as
  Switzerland's gdp_real, NOT Denmark's split
  gdp_growth(OECD)+gdp_real(Penn World Table annual) approach -- Sweden's
  page was built around a single quarterly real-GDP series with
  gdp_growth derived from it via YoY transform, matching the
  Turkey/Indonesia/Poland/Argentina pattern more closely than Denmark's.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=SWE): standard
  fetch_worldbank() mechanism, same raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family.
- unemployment (LRHUTTTTSEM156S): CONFIRMED live (through Apr 2026,
  updated Jun 2026), OECD harmonized, seasonally adjusted, monthly.
  Unlike Switzerland, Sweden's LRHUTTTT-prefixed series is NOT
  discontinued -- individually confirmed live, not assumed.
- bond_yield_10y (IRLTLT01SEM156N): CONFIRMED live (through Feb 2026,
  updated Mar 2026), OECD, monthly.
- debt_gdp / deficit (Eurostat gov_10dd_edpt1, geo=SE): same EDP
  notification table mechanism CONFIRMED working for Denmark (and
  Germany/France/Italy/Spain/Netherlands before that) -- Eurostat's EDP
  table covers all EU member states, and Sweden is an EU member, so this
  is a low-risk reuse of an already-proven query shape with geo swapped.
  Not individually re-executed against the live API for Sweden
  specifically before this build -- check the Actions log on first
  real run.
- participation_rate / employment_rate: NOT included. No clean live
  series individually confirmed for Sweden specifically during this
  build -- genuine, disclosed gap here, not a guess.
- policy_rate: NOT included. No clean live source individually
  confirmed during this build.
- fx_to_usd (DEXSDUS): CONFIRMED live (through Aug 2026, 5 days old at
  time of search), a real Fed H.10 daily series -- same quality tier as
  Norway/Denmark's own FX series, better than the OECD monthly-average
  fallback used for Turkey/Indonesia/Poland/Argentina/Switzerland.
- current_account (World Bank BN.CAB.XOKA.GD.ZS): same mechanism used
  for Denmark. Not individually confirmed for Sweden's specific data
  availability -- standard World Bank annual lag applies.
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for every other country on this site), REF_AREA=SWE.
  Not individually executed end-to-end for Sweden before this build --
  check the Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=SWE. Best-effort, not
  individually confirmed.
- trade_balance: NOT INCLUDED. Same as Denmark's own fetch script --
  no verified live source was wired in for either country; the page's
  trade_balance panel will show sample data until this gap is closed.
  Genuine, disclosed gap, matching Denmark's actual current behavior,
  not a new regression introduced here.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=SWE. Not individually confirmed for
  Sweden's specific data availability -- standard World Bank annual lag
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
    "gdp_real": ("CLVMNACSCAB1GQSE", "q", "Real GDP, chain-linked volumes, SA (Eurostat)", "index", None, 1.0),
    "unemployment": ("LRHUTTTTSEM156S", "m", "Unemployment rate, 15+, OECD-harmonized, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01SEM156N", "m", "10-year government bond yield (OECD)", "%", None, 1.0),
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


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=SE&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] SE status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] SE request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-SE")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] SE parsing failed: {exc}; "
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


def yoy_from_level(points: list, lag: int) -> list:
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/SWE.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/SWE.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "SWE") != "SWE":
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

WB_URL = ("https://api.worldbank.org/v2/country/SWE/indicator/"
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

        if "gdp_real" in out["series"]:
            level_pts = out["series"]["gdp_real"]["points"]
            growth_pts = yoy_from_level(level_pts, 4)
            if growth_pts:
                out["series"]["gdp_growth"] = {
                    "label": "Real GDP growth, YoY (derived from CLVMNACSCAB1GQSE)",
                    "unit": "%", "freq": "quarters", "points": growth_pts,
                }
                print(f"  ok  gdp_growth      {len(growth_pts):>5} observations (derived YoY)")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("SWE",), "M"),
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

    try:
        raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
        if not raw_gdp:
            raise ValueError("no usable response")
        scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
        out["series"]["gdp_level"] = {
            "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD)",
            "unit": "$m", "freq": "years", "points": scaled_gdp,
        }
        print(f"  ok  gdp_level        {len(scaled_gdp):>5} observations "
              f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years)")
    except Exception as exc:
        failures.append("gdp_level")
        print(f"FAIL  gdp_level        {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-se.json") as f:
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
            fx_pts = fetch_fred("DEXSDUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "SEK/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

                to_local = lambda v: v * fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                            ser["unit"] = ser["unit"].replace("$", "kr", 1)
                            ser["label"] = ser["label"].replace(", $ ", ", kr ") \
                                                        .replace(", $", ", kr")
                            print(f"  ok  {tk:<16} converted $->kr using {fx_rate}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-se.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-se.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
