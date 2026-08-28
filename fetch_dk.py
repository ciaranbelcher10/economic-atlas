"""Fetch Denmark economic series and write data-dk.json.

Run:  FRED_API_KEY=yourkey python3 fetch_dk.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series' own FRED/OECD page before
wiring in -- v1.1.5 build):
- bond_yield_10y (IRLTLT01DKM156N): CONFIRMED live, OECD Main Economic
  Indicators, monthly, through Feb 2026 as of this build.
- unemployment (LRHUTTTTDKM156S): CONFIRMED live, OECD-harmonized, monthly,
  through Jan 2026. IMPORTANT CAVEAT, not yet resolved: this reads notably
  higher (~7-8%) than Denmark's commonly-cited national rate (~2.6-2.7%,
  per Trading Economics/Danmarks Statistik's own headline figure) -- almost
  certainly a definitional/methodology difference (OECD-harmonized survey
  basis vs. Denmark's own registered/national-survey basis), not a fetch
  bug, but this needs a real decision (which figure to show, and how to
  label it honestly) before this series should be treated as ready to
  display without a caveat on the page itself. Do not silently "fix" this
  by swapping to a different series without understanding why they diverge.
- debt_gdp (GGGDTADKA188N) / deficit (GGNLBADKA188N): IMF WEO annual, via
  FRED. INFERRED BY NAMING PATTERN, NOT INDIVIDUALLY CONFIRMED -- every
  other country on this site follows FRED's consistent
  GGGDTA{2-letter-code}A188N / GGNLBA{2-letter-code}A188N convention for
  IMF WEO gross debt / net lending-borrowing (verified directly for
  Canada, Germany, Italy, Greece, Euro Area during this build), and IMF
  WEO covers essentially every country including Denmark, so this is a
  well-evidenced inference -- but unlike every other series in this file,
  these two specific IDs were not individually pulled up and confirmed.
  CHECK THE FIRST REAL ACTIONS LOG CAREFULLY for these two specifically.
  Do NOT use World Bank's DEBTTLDKA188A as an alternative -- confirmed
  during this build to be dead, stopped at 1994 (30+ years stale), the
  exact same failure mode already fixed for Israel/Morocco elsewhere on
  this site.
- gdp_level (CPMNACSCAB1GQDK, Eurostat via FRED) / gdp_real (CLVMNACSCAB1GQDK,
  Eurostat via FRED): this docstring paragraph was stale -- it previously
  described gdp_level as World Bank USD and gdp_real as Penn World Table,
  but FRED_SERIES below has actually pointed both at genuine DKK-denominated
  Eurostat series (current-price and chained-2010-price national accounts,
  seasonally adjusted, quarterly) for some time. CONFIRMED live via each
  series' own FRED page. World Bank's NY.GDP.MKTP.CD remains as a fallback
  further down (only used if the Eurostat fetch fails this run), clearly
  labelled and scale-corrected the same way as every other country's USD
  fallback on this site.
- gdp_growth: BUG FIX (Aug 2026 session) -- this used to be fetched
  directly from DNKGDPRQPSMEI (OECD's own published YoY growth rate) and
  labelled "GDP growth (QoQ)" on the page. That series genuinely is YoY,
  not QoQ, as published -- the page was showing the same YoY figure twice
  under two different labels (QoQ tile and YoY tile), the exact Bug 6
  "duplicate tile" tell already fixed for other countries this session.
  Retired DNKGDPRQPSMEI entirely and derive genuine QoQ growth instead
  from gdp_real's own quarterly chained-volume level series
  (CLVMNACSCAB1GQDK) via a qoq transform, computed after the main
  FRED_SERIES loop below (see the dedicated block near the end of main()).
  This also fixes the growth citation, which had been citing "Penn World
  Table" even though neither series has used PWT for some time.
- trade_balance: NOT INCLUDED. No specific FRED series ID was verified
  for this build (unlike Korea's confirmed XTNTVA01KRQ667S) -- flagged as

  a genuine gap to fill in a follow-up session rather than guessing a
  series ID and risking a silent wrong-scale bug (the "667 family reports
  plain USD, not millions" pattern has bitten this codebase before).
- cpi: wired in directly via OECD's live SDMX prices system (same proven
  query structure already used for Japan/India/Canada/Australia/South
  Korea), REF_AREA=DNK. Not individually executed end-to-end for Denmark
  before this build -- check the Actions log on first real run, same
  caveat as every other country that uses this pattern.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for every other country, REF_AREA=DNK. Best-effort.
- fx_to_usd (DEXDNUS): CONFIRMED live, daily H.10 series, through late
  March 2026 as of this build. NOTE: DKK is tightly pegged to EUR (~7.46
  DKK/EUR per Danmarks Nationalbank's fixed exchange rate policy) -- its
  rate against USD will move roughly in lockstep with EUR/USD, not
  independently. This is expected, correct behaviour, not a data bug.
- fdi / current_account: World Bank, same indicator codes already used
  for every other country (BX.KLT.DINV.WD.GD.ZS / BN.CAB.XOKA.GD.ZS),
  country=DNK. Not individually confirmed for Denmark's specific data
  availability before this build -- standard World Bank annual lag
  applies, same as every other country using these indicators.
"""

from __future__ import annotations

import json
import time
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
# - participation_rate (LRAC64TTDKQ156S) / employment_rate (LREM64TTDKQ156S): OECD infra-annual labour-statistics FRED family, quarterly, ages 15-64. Same pattern confirmed live for Germany (pilot); inferred-by-pattern for Denmark -- not individually confirmed, check the first Actions log.
FRED_SERIES = {
    "gdp_real": ("CLVMNACSCAB1GQDK", "q", "Real GDP, chained 2010 prices, SA (Eurostat)", "DKKm", None, 1.0),
    "gdp_level": ("CPMNACSCAB1GQDK", "q", "Nominal GDP, current prices, SA (Eurostat)", "DKKm", None, 1.0),
    "unemployment": ("LRHUTTTTDKM156S", "m", "Unemployment rate, 15+, OECD-harmonized", "%", None, 1.0),
    "participation_rate": ("LRAC64TTDKQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTDKQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01DKM156N", "m", "10-year government bond yield", "%", None, 1.0),
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


# ---- debt_gdp / deficit (Denmark) -- FIX applied after the v1.1.5 real
# run: the inferred IMF WEO FRED series (GGGDTADKA188N / GGNLBADKA188N)
# returned a 400 Bad Request -- those IDs don't exist on FRED at all for
# Denmark. Replaced with the same live Eurostat query CONFIRMED WORKING
# in that same run for Germany/France/Italy/Spain/Netherlands
# (gov_10dd_edpt1). Denmark is an EU member (not Eurozone), and Eurostat's
# EDP notification table covers all EU member states, not just euro-area
# ones -- geo=DK, otherwise identical to the Eurozone-member pattern.
def fetch_eurostat_govfinance(na_item: str) -> list | None:
    url = (f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
          f"&geo=DK&sector=S13&unit=PC_GDP&na_item={na_item}"
          f"&sinceTimePeriod=2000")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [eurostat-gov-{na_item}] DK status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] DK request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"eurostat-gov-{na_item}-DK")
    except Exception as exc:
        print(f"  [eurostat-gov-{na_item}] DK parsing failed: {exc}; "
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


# ---- OECD business confidence (Denmark) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
DK_AREAS = ("DNK",)
OECD_QUERIES = [
    f"{OECD_BASE}/DNK.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/DNK.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "DNK") not in DK_AREAS:
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
# Japan/India/Canada/Australia/South Korea, just pointed at Denmark.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
# OECD is progressively migrating countries from the COICOP 1999 CPI
# classification (above) to COICOP 2018. Once a country's national
# statistics office migrates, new observations stop landing in the old
# dataflow -- it keeps returning 200 OK with the last pre-migration
# data forever, so nothing here ever "fails" or gets rejected by the
# staleness guard until it crosses max_age_days. This is what silently
# stalled CPI for DK/IE/NO/PL/CH/TR (all last-updated 2025-12, found
# via the Aug 2026 data-quality sweep once operator-side monitoring
# was extended to cover them). Confirmed via OECD's own dataflow
# description (COICOP 1999 dataflow page explicitly says migrated
# countries' data now lives in the COICOP 2018 dataflow instead) --
# not verified yet against a live response from this exact sandbox
# (sdmx.oecd.org is outside the network allowlist here), so treat as
# unconfirmed until the next real Actions run log shows COICOP2018
# attempts actually returning data for these countries.
OECD_PRICES_BASE_COICOP2018 = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    import csv
    import io

    lag = 4 if freq == "Q" else 12
    # Staleness guard, same as every other country on this site: a fetch
    # that "succeeds" but returns a discontinued series must be REJECTED,
    # not shipped (see Japan's 2015=100-base incident elsewhere in this
    # codebase for why this matters).
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
        # Try COICOP 2018 first (fresher, for countries that have
        # migrated), then fall back to the legacy COICOP 1999 dataflow
        # (still the only source for countries that haven't migrated
        # yet) -- same attempt variants against each base, so a country
        # not yet on COICOP 2018 just falls through with 0 usable rows
        # from those attempts and picks up its existing COICOP 1999
        # result exactly as before.
        bases = ((OECD_PRICES_BASE_COICOP2018, "C2018"), (OECD_PRICES_BASE, "C1999"))
        combos = [(base_url, base_tag, um, tc, ny, me, ad)
                  for base_url, base_tag in bases
                  for um, tc, ny, me, ad in attempts]
        # Consecutive-429 tracking: doubling the attempts (COICOP2018 +
        # COICOP1999) doubled this function's request volume, which
        # contributed to a wider 429 cascade across OECD AND FRED calls
        # elsewhere in this same run (Aug 2026 data-quality sweep --
        # confirmed via the Actions log, not guessed). A small delay
        # between requests plus bailing out after repeated 429s cuts
        # this country's total request count fast once the host is
        # already rate-limiting it, rather than burning through all 8
        # combos when the first two already came back 429.
        consecutive_429s = 0
        for base_url, base_tag, unit_measure, trans_code, needs_yoy, meth, adj in combos:
            if consecutive_429s >= 2:
                print(f"  [oecd-cpi] {area} bailing out after {consecutive_429s} "
                      f"consecutive 429s -- host is rate-limiting this run, "
                      f"further attempts here just add to that")
                break
            time.sleep(0.4)
            tag = f"{base_tag}.{area}.{meth or '*'}.{unit_measure}.{trans_code}"
            url = (f"{base_url}/{area}.{freq}.{meth}.CPI."
                   f"{unit_measure}._T.{adj}.{trans_code}"
                   f"?format=csvfile&startPeriod=2015")
            try:
                r = requests.get(url, timeout=60,
                                 headers={"User-Agent": "economic-atlas/0.1"})
                print(f"  [oecd-cpi] {tag} status={r.status_code}")
                if r.status_code == 429:
                    consecutive_429s += 1
                    time.sleep(2.0)
                else:
                    consecutive_429s = 0
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

# ---- World Bank (Denmark) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/DNK/indicator/"
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

    # gdp_growth: BUG FIX (Aug 2026 session) -- derive genuine QoQ growth
    # from gdp_real's own quarterly chained-volume level series
    # (CLVMNACSCAB1GQDK) rather than fetching DNKGDPRQPSMEI (OECD's
    # already-YoY series, previously mislabelled "QoQ" on the page and
    # duplicating the separately-computed YoY tile -- Bug 6). See docstring
    # note above.
    if "gdp_real" in out["series"]:
        try:
            real_points = out["series"]["gdp_real"]["points"]
            growth_points = transform(real_points, "qoq")
            if not growth_points:
                raise ValueError("qoq transform produced no points")
            out["series"]["gdp_growth"] = {
                "label": "Real GDP growth, QoQ (derived from CLVMNACSCAB1GQDK)",
                "unit": "%", "freq": "quarters", "points": growth_points,
            }
            print(f"  ok  gdp_growth      {len(growth_points):>5} observations "
                  f"({growth_points[0][0]} to {growth_points[-1][0]}, quarters) "
                  f"-- derived QoQ from gdp_real")
        except Exception as exc:
            failures.append("gdp_growth")
            print(f"FAIL  gdp_growth       {exc}")
    else:
        failures.append("gdp_growth")
        print("FAIL  gdp_growth       gdp_real unavailable, cannot derive QoQ")

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),

         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("DNK",), "M"),
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

    # gdp_level: CPMNACSCAB1GQDK above (via FRED_SERIES) is now the
    # primary source, genuinely denominated in DKK, quarterly, matching
    # gdp_real -- upgrading from the old annual, constant-USD Penn World
    # Table figure to something genuinely local-currency and on the same
    # cadence as gdp_growth. This World Bank USD series is now only a
    # fallback, clearly labeled as USD so the frontend's isAlreadyUSD()
    # guard (added this session) correctly skips re-converting it if this
    # fallback ever gets used. It also has its own scale quirk worth
    # preserving in the fallback path: this specific World Bank series
    # reports RAW dollars, not millions (confirmed during the original
    # build by checking the actual 2024 figure), hence the /1e6.
    if "gdp_level" not in out["series"]:
        try:
            raw_gdp = fetch_worldbank("NY.GDP.MKTP.CD")
            if not raw_gdp:
                raise ValueError("no usable response")
            scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
            out["series"]["gdp_level"] = {
                "label": "GDP, current prices (World Bank, NY.GDP.MKTP.CD -- USD, "
                         "fallback: CPMNACSCAB1GQDK unavailable this run)",
                "unit": "$m", "freq": "years", "points": scaled_gdp,
            }
            print(f"  ok  gdp_level (WB USD fallback) {len(scaled_gdp):>5} observations "
                  f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years) -- "
                  f"scaled from raw USD to $m")
            if "gdp_level" in failures:
                failures.remove("gdp_level")
        except Exception as exc:
            failures.append("gdp_level")
            print(f"FAIL  gdp_level (WB USD fallback) {exc}")

    try:
        with open("data-dk.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run, so a transient failure (e.g. OECD 429 rate-limiting --
    # this exact thing happened to Denmark's cpi and business_confidence
    # in the Aug 2026 data-quality sweep) doesn't wipe good data from the
    # live page and leave it with nothing at all instead of a disclosed-
    # stale reading. Same pattern already used for Turkey/Poland/
    # Switzerland/Chile/Colombia/Indonesia -- Denmark was missing it.
    # Placed BEFORE the "nothing fetched" bailout below (matching
    # Turkey's ordering) so a run where every single series fails still
    # gets rescued by carried-over data rather than giving up entirely.
    _prev_series = prev_full.get("series", {})
    carried_over = []
    for k, v in _prev_series.items():
        if k not in out["series"]:
            out["series"][k] = v
            carried_over.append(k)
    if carried_over:
        print(f"CARRIED OVER from previous run (failed this run, kept prior data rather than deleting it): {', '.join(carried_over)}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

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
            fx_pts = fetch_fred("DEXDNUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "DKK/USD", "rate": fx_rate,
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
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) — "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-dk.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-dk.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
