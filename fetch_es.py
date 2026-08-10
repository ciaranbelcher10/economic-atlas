"""Fetch Spain economic series and write data-es.json.

Run:  FRED_API_KEY=yourkey python3 fetch_es.py
Sources: FRED (free key required), OECD, Eurostat, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Fourth individual Eurozone-member country page (Tier 2), derived from
Italy's (the third). Unlike Germany/France/Italy, Spain is NOT a G7
country (though it is a founding OECD member), and its GDP data turned
out to be a genuinely different, thinner situation worth reading before
touching anything:

- The "obvious" guess for a live nominal/real GDP LEVEL series
  (NGDPSAXDCESQ / NGDPRSAXDCESQ, following the exact pattern that worked
  for Germany/France/Italy) does NOT belong to Spain -- FRED's own "ES"
  slot in that specific IMF IFS naming family is already Estonia's.
  Checked directly and confirmed.
- The OECD MEI mirror has the same split-freshness problem seen
  elsewhere on this site: the REAL GDP growth-rate series
  (ESPGDPRQPSMEI) is confirmed live through Q3 2025, but the sibling
  NOMINAL GDP level series (ESPGDPNQDSMEI) is stale, stuck at Q3 2023.
- Net result: no confirmed-live GDP LEVEL series in euros exists for
  Spain via either of the two FRED/OECD patterns that worked for every
  other Eurozone country built so far. FIX (9.15.4): rather than accept
  World Bank's annual USD data as the primary source (which shipped in
  9.15.2 and left Spain's GDP in $ instead of € -- inconsistent with
  every other Eurozone-member page and making the Dollarise toggle a
  no-op), gdp_level and gdp_real now query Eurostat's namq_10_gdp table
  directly for genuine EUR-denominated quarterly data, since Eurostat is
  the origin these FRED/OECD mirrors are built from in the first place.
  World Bank annual USD remains as a documented fallback only if that
  Eurostat query fails on a given run. gdp_growth is still NOT derived
  from a level series here -- it's fetched DIRECTLY from the
  confirmed-live OECD quarterly series (ESPGDPRQPSMEI), which is already
  a YoY growth rate, not a level. This means Spain's "GDP growth" tile
  is YoY, not QoQ like every other country's -- labelled accordingly
  rather than presented as if it were the same metric.

VERIFICATION NOTES for the rest:

- unemployment (LRHUTTTTESM156S): checked directly, live monthly through
  Apr 2026, standard naming convention.
- bond_yield_10y: uses the QUARTERLY series (IRLTLT01ESQ156N), confirmed
  live through Q4 2025. The monthly sibling wasn't directly confirmed
  either way in search results, so the quarterly one was used, same
  reasoning as Italy's build.
- debt_gdp / deficit: sourced via Eurostat (fetch_eurostat_govfinance),
  reusing the mechanism proven for the Eurozone aggregate, Germany,
  France and Italy, with geo="ES".
- trade_balance: via Eurostat's teiet010/teiet110 tables, same mechanism
  as debt_gdp/deficit -- with partner="WORLD" (total trade, including
  intra-EU) rather than the aggregate's "WRL_REST" (extra-area only).
  NOT confirmed to exist for this specific partner code before writing.
- cpi (CP0000ESM086NEST): guessed by extending the Eurozone aggregate's
  own FRED series naming pattern (CP0000EZ19M086NEST) with Spain's
  country code -- NOT confirmed to exist, same caveat as every other
  Eurozone member built so far.
- business_confidence: OECD BCICP, area ESP, same fallback pattern as
  every other country.
- fx_to_usd (DEXUSEU): same series and direction as the Eurozone
  aggregate, Germany and France -- the euro is worth more than a dollar,
  so converting a EUR-denominated value into USD means multiplying by
  the rate, not dividing (opposite of weaker-currency countries like
  Mexico/Brazil/South Africa, where the pair is quoted the other way
  round and conversion divides). FIX (9.15.1): this note previously said
  "dividing", which was stale/backwards -- the code below has always
  correctly set direction="multiply"; only the comment was wrong.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

FRED_SERIES = {
    "trade_balance": ("XTNTVA01ESM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
    "unemployment": ("LRHUTTTTESM156S", "m", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01ESQ156N", "q", "10-year government bond yield", "%", None, 1.0),
    "cpi": ("CP0000ESM086NEST", "m", "HICP, all items, YoY", "%", "yoy", 1.0),
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


# ---- World Bank (Spain) -- free API, no key. FIX (9.15.1): this function
# and WB_URL were referenced by the extras list below (gdp_level, gdp_real)
# but never actually defined in this file -- every run silently raised
# NameError, caught by the generic except-Exception in the extras loop, so
# Spain has never had a GDP figure since this page was built. Copied from
# the same pattern already proven for Morocco/Israel, with Spain's ISO3
# code. ----
WB_URL = ("https://api.worldbank.org/v2/country/ESP/indicator/"
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


# ---- OECD business confidence (Spain) ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
ES_AREAS = ("ESP",)
OECD_QUERIES = [
    f"{OECD_BASE}/ESP.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/ESP.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "ESP") not in ES_AREAS:
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
# aggregate, parameterized by geo="ES" instead of the bloc codes ----
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


def fetch_eurostat_gdp(unit: str, s_adj: str = "SCA") -> list | None:
    """FIX (9.15.4): GDP at market prices for Spain, direct from Eurostat's
    national accounts table (namq_10_gdp) -- quarterly, genuinely
    EUR-denominated, unlike the World Bank annual USD fallback this
    replaces as the primary source. Neither FRED nor OECD have a working
    EUR level series for Spain (see module docstring), but Eurostat is
    the origin of the data those mirrors are themselves built from, so
    querying it directly was always the more correct fix.

    unit="CP_MEUR" -> nominal, current prices, million EUR (gdp_level).
    unit="CLV20_MEUR" -> real, chain-linked volumes, 2020 reference year,
    million EUR (gdp_real). Eurostat periodically rebases the CLV
    reference year (e.g. CLV15_MEUR before a prior rebase) -- if this
    specific unit code returns 0 points, that rebase is the first thing
    to check against Eurostat's current namq_10_gdp metadata before
    assuming the whole approach is wrong.
    """
    url = (f"{EUROSTAT_STATS_BASE}/namq_10_gdp?format=JSON&lang=EN"
          f"&geo=ES&na_item=B1GQ&unit={unit}&s_adj={s_adj}"
          f"&sinceTimePeriod=1995")
    tag = f"eurostat-gdp-{unit}-ES"
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [{tag}] status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [{tag}] request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, tag)
    except Exception as exc:
        print(f"  [{tag}] parsing failed: {exc}; first 300 chars: {r.text[:300]!r}")
        return None


def fetch_eurostat_unemployment() -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/une_rt_m?format=JSON&lang=EN"
          f"&geo=ES&sex=T&age=TOTAL&unit=PC_ACT&s_adj=SA"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-unemp] ES status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-unemp] ES request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, "eurostat-unemp-ES")
    except Exception as exc:
        print(f"  [eurostat-unemp] ES parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=ES&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] ES status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] ES request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-ES")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] ES parsing failed: {exc}; "
              f"first 300 chars: {r.text[:300]!r}")
        return None


def _fetch_eurostat_teiet(dataset: str, stk_flow: str) -> list | None:
    """Same table family as the Eurozone aggregate, but partner=WORLD
    (total trade) instead of WRL_REST (extra-area only) -- see the
    module docstring for why. Unconfirmed until the first live run."""
    params = {"geo": "ES", "partner": "WORLD", "unit": "TVAL_SA",
              "stk_flow": stk_flow, "sitc06": "TOTAL"}
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{EUROSTAT_STATS_BASE}/{dataset}?format=JSON&lang=EN&{qs}&sinceTimePeriod=1999"
    tag = f"eurostat-trade-{stk_flow}-{dataset}-ES"
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-trade] {stk_flow} {dataset} ES status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-trade] {stk_flow} {dataset} ES request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, tag)
    except Exception as exc:
        print(f"  [eurostat-trade] {stk_flow} {dataset} ES parsing failed: {exc}; "
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

        try:
            raw = fetch_fred("ESPGDPRQPSMEI", "q", key)
            if raw:
                out["series"]["gdp_growth"] = {
                    "label": "Real GDP growth, YoY (OECD, ESPGDPRQPSMEI -- already a "
                             "growth rate, not derived from a level series like most "
                             "other countries)",
                    "unit": "%", "freq": "quarters", "points": raw}
                print(f"  ok  gdp_growth       {len(raw):>5} observations "
                      f"({raw[0][0]} to {raw[-1][0]}, quarters, fetched directly)")
            else:
                raise ValueError("no observations")
        except Exception as exc:
            failures.append("gdp_growth")
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

    # gdp_level / gdp_real: FIX (9.15.4) -- prefer genuine EUR-denominated
    # quarterly data direct from Eurostat (consistent with every other
    # Eurozone-member page); fall back to World Bank annual USD only if
    # Eurostat's namq_10_gdp doesn't resolve. The World Bank fallback is
    # what shipped in 9.15.2 and is why GDP showed in $ instead of €,
    # making Dollarise a no-op -- this makes the € source primary.
    try:
        pts = fetch_eurostat_gdp("CP_MEUR")
        if pts:
            out["series"]["gdp_level"] = {
                "label": "GDP, nominal, SA (Eurostat namq_10_gdp, CP_MEUR)",
                "unit": "\u20acm", "freq": "quarters", "points": pts}
            print(f"  ok  gdp_level (eurostat) {len(pts)} observations")
        else:
            raise ValueError("no observations from Eurostat namq_10_gdp")
    except Exception as exc:
        print(f"FAIL  gdp_level (eurostat) {exc} -- falling back to World Bank USD")
        try:
            pts = fetch_worldbank("NY.GDP.MKTP.CD")
            if not pts:
                raise ValueError("no usable response")
            out["series"]["gdp_level"] = {
                "label": "GDP, nominal, current US$ (World Bank, annual -- "
                         "Eurostat EUR series unavailable this run)",
                "unit": "$", "freq": "years", "points": pts}
            print(f"  ok  gdp_level (world bank fallback) {len(pts)} observations")
        except Exception as exc2:
            failures.append("gdp_level")
            print(f"FAIL  gdp_level (world bank fallback) {exc2}")

    try:
        pts = fetch_eurostat_gdp("CLV20_MEUR")
        if pts:
            out["series"]["gdp_real"] = {
                "label": "Real GDP, chain-linked volume, SA (Eurostat "
                         "namq_10_gdp, CLV20_MEUR)",
                "unit": "\u20acm", "freq": "quarters", "points": pts}
            print(f"  ok  gdp_real (eurostat) {len(pts)} observations")
        else:
            raise ValueError("no observations from Eurostat namq_10_gdp")
    except Exception as exc:
        print(f"FAIL  gdp_real (eurostat) {exc} -- falling back to World Bank USD")
        try:
            pts = fetch_worldbank("NY.GDP.MKTP.KD")
            if not pts:
                raise ValueError("no usable response")
            out["series"]["gdp_real"] = {
                "label": "GDP, real, constant 2015 US$ (World Bank, annual -- "
                         "Eurostat EUR series unavailable this run)",
                "unit": "$", "freq": "years", "points": pts}
            print(f"  ok  gdp_real (world bank fallback) {len(pts)} observations")
        except Exception as exc2:
            failures.append("gdp_real")
            print(f"FAIL  gdp_real (world bank fallback) {exc2}")

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
        with open("data-es.json") as f:
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

    # Spain's own trade data is already sourced in EUR (via Eurostat)
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
                                     "as_of": fx_period, "direction": "multiply"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

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

    with open("data-es.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-es.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
