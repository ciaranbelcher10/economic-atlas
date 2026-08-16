"""Fetch Norway economic series and write data-no.json.

Run:  FRED_API_KEY=yourkey python3 fetch_no.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
Eurostat (best-effort, see debt_gdp/deficit caveat below).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Norway build note: derived from fetch_dk.py (most recent own-currency,
non-Eurozone page at build time) per the v2 country-build framework.
Norway is a full OECD member but NOT an EU member (EEA/EFTA only) --
this matters specifically for the Eurostat-sourced series below.

VERIFICATION NOTES (checked against each series' own FRED/OECD page
via web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org/sdmx.oecd.org directly, so these are page-content
confirmations, not live API test calls; the first real Actions run is
still the genuine test):
- bond_yield_10y (IRLTLT01NOM156N): CONFIRMED live (page showed data
  through May 2026), OECD Main Economic Indicators, monthly.
- unemployment (LRHUTTTTNOQ156S): CONFIRMED live (through Q4 2025,
  updated Mar 2026), OECD-harmonized, seasonally adjusted -- but
  QUARTERLY, not monthly like most other countries. Norway's monthly
  OECD mirror (LRHUTTTTNOM156N) is NSA-only; the SA version only
  exists at quarterly frequency. Used the quarterly SA series
  deliberately rather than a monthly NSA series, matching how Mexico
  substitutes a quarterly series for the same reason elsewhere on
  this site. Freq set to "q" in FRED_SERIES accordingly.
- participation_rate (LRAC64TTNOQ156S) / employment_rate
  (LREM64TTNOQ156S): OECD infra-annual labour-statistics FRED family,
  quarterly, ages 15-64. Same pattern confirmed live for Germany
  (pilot) and rolled out across the rest of the OECD-member roster;
  INFERRED BY PATTERN for Norway specifically -- not individually
  confirmed, check the first Actions log.
- gdp_growth (NORGDPRQPSMEI): CONFIRMED live (through Q4 2025, updated
  Mar 2026), OECD Main Economic Indicators, "growth rate same period
  previous year", quarterly. Already a YoY growth rate as published --
  no transform needed. NOTE: Norway's OECD-mirrored NOMINAL GDP LEVEL
  series (NORGDPNQDSMEI) is DEAD -- stopped at Q3 2023 (confirmed via
  its own FRED page, last updated Dec 2023) -- exactly the failure mode
  the v2 framework flags to check for before committing. Used the
  Denmark-pattern workaround instead: World Bank annual USD for
  gdp_level, Penn World Table annual for gdp_real, and this OECD
  growth-rate series (which is NOT dead) for gdp_growth.
- gdp_level / gdp_real: BUG FIX (Aug 2026 session). The original build's
  notes above claimed gdp_level had to fall back to World Bank USD
  (NY.GDP.MKTP.CD) because Norway's OECD nominal-GDP mirror is dead, and
  left gdp_real on Penn World Table (RGDPNANOA666NRUG). This was the same
  "confidently-wrong disclosed gap" failure mode already caught for
  Thailand/Singapore/Ireland this session -- checked directly against
  World Bank's own indicator pages and NY.GDP.MKTP.CN (GDP, current LCU)
  genuinely exists for Norway, same as NY.GDP.MKTP.KN (GDP, constant
  LCU). No real need to fall back to USD-only, nor to Penn World Table's
  PPP-benchmarked, publication-lagged series. Swapped both to genuine
  NOK-denominated World Bank series, on the same current/constant-LCU
  basis used for Austria/Thailand/Singapore:
    gdp_level -> NY.GDP.MKTP.CN (current LCU, NOK) via fetch_worldbank(),
      same raw-value-not-millions scale correction (scale 1e-6) as the
      NY.GDP.MKTP.CD family.
    gdp_real  -> NY.GDP.MKTP.KN (constant LCU, NOK) via fetch_worldbank(),
      same scale correction. This retires the PWT dependency entirely for
      Norway -- no more PPP/nominal mismatch under "Make it real", and no
      more stale-year Penn World Table citation.
  Both handled in a dedicated block below (not the generic FRED_SERIES
  loop) since they share a scale correction and a NOK label, matching
  the Colombia/Chile/Thailand/Singapore pattern. NOT yet confirmed via
  an actual live API call (same sandbox network limitation as
  everything else in this file) -- check the first real Actions log.
- trade_balance (XTNTVA01NOM667S): CONFIRMED live (through Dec 2025,
  updated Feb 2026), OECD merchandise trade, monthly, USD. Unlike
  Denmark (which left trade_balance out as an unverified gap), this
  was individually confirmed for Norway during this build -- included
  directly in FRED_SERIES with the same scale=1e-6 raw-USD-to-$m
  correction as Germany/South Korea's equivalent series.
- cpi: wired in via OECD's live SDMX prices system (same proven query
  structure used for Denmark/Japan/India/Canada/Australia/South
  Korea), REF_AREA=NOR. Cross-checked against FRED's separate HICP
  mirror (CP0000NOM086NEST, confirmed live through Dec 2025) as
  supporting evidence that Norway genuinely has current CPI data
  flowing through these systems, but the actual fetch path is the
  OECD SDMX query, not that FRED series directly. Not individually
  executed end-to-end for Norway before this build -- check the
  Actions log on first real run.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=NOR. Best-effort,
  not individually confirmed.
- fx_to_usd (DEXNOUS): CONFIRMED live, daily H.10 series, through
  March 2026 as of this build. Direction "divide" (NOK-per-USD, same
  convention as DEXDNUS/DKK) -- Norway's krone floats independently
  (unlike Denmark's EUR peg), so this rate moves on its own, not in
  lockstep with EUR/USD.
- fdi / current_account: World Bank, same indicator codes used for
  every other country (BX.KLT.DINV.WD.GD.ZS / BN.CAB.XOKA.GD.ZS),
  country=NOR. Not individually confirmed for Norway's specific data
  availability -- standard World Bank annual lag applies.
- debt_gdp / deficit (Eurostat gov_10dd_edpt1, geo=NO): GENUINE RISK,
  HIGHER THAN ANY OTHER SERIES IN THIS FILE. Eurostat's own EDP-dataset
  documentation states this table covers "EU Member States, the euro
  area and the European Union" -- Norway is EEA/EFTA, NOT an EU member,
  so this table may simply not return Norway data at all (unlike
  Denmark/Ireland, where this exact query IS confirmed working because
  they are EU members). Attempted anyway because it's zero-cost to try
  and the existing fetch_eurostat_govfinance() function needed no
  changes -- if it fails, debt_gdp/deficit will legitimately be absent
  from data-no.json and the page will render fine without them (same
  graceful-fallback behaviour as any other missing series). Do NOT
  silently swap in a guessed alternative (e.g. IMF WEO's
  GGGDTANOA188N/GGNLBANOA188N) without individually confirming it --
  the IMF WEO FRED family has already been shown NOT to exist for
  every country (400 Bad Request for Denmark and Ireland during the
  v1.1.6 build). CHECK THE FIRST REAL ACTIONS LOG: if this fails for
  Norway as expected, it's a genuine gap to flag to Ciaran for a
  follow-up session (Statistics Norway / SSB direct scraping is the
  likely eventual fix), not a bug to silently patch over.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_growth": ("NORGDPRQPSMEI", "q", "Real GDP growth, YoY (OECD, as published)", "%", None, 1.0),
    "unemployment": ("LRHUTTTTNOQ156S", "q", "Unemployment rate, 15+, SA (OECD)", "%", None, 1.0),
    "participation_rate": ("LRAC64TTNOQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTNOQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01NOM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "trade_balance": ("XTNTVA01NOM667S", "m", "Trade balance, goods, $", "$m", None, 1e-6),
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


# ---- debt_gdp / deficit (Norway) -- SECOND FIX. The v1.1.6-era build used
# gov_10dd_edpt1 (the EDP notification table), which Eurostat's own docs
# say covers "EU Member States, the euro area and the European Union"
# only -- Norway is EEA/EFTA, not an EU member, and this genuinely
# returned nothing for Norway on the first real Actions run (confirmed
# in the freshness log: "fetch_no.py / debt_gdp: no usable response",
# same for deficit). Root-caused via web_search (sandbox network still
# can't reach Eurostat directly) to two DIFFERENT Eurostat datasets that
# explicitly document EFTA coverage:
#   - gov_10q_ggdebt ("Quarterly government debt"): Eurostat's own ESMS
#     metadata states "Data cover EU Member States, Iceland and Norway."
#     Used for debt_gdp (na_item=GD). Confirmed elsewhere on Eurostat's
#     own Statistics Explained site, which cites Norway's debt-to-GDP
#     figures with this exact dataset as the source.
#   - gov_10q_ggnfa ("Quarterly non-financial accounts for general
#     government"): Eurostat's Statistics Explained states this "cover[s]
#     all EU countries as well as the EFTA countries Iceland, Norway and
#     Switzerland." Used for deficit (na_item=B9, net lending/borrowing).
# Both are QUARTERLY (unlike gov_10dd_edpt1's annual EDP notifications),
# so debt_gdp/deficit switch from "years" to "quarters" freq for Norway
# specifically -- matches the "q" freq already used for Norway's
# unemployment/participation/employment series. gov_10q_ggnfa also has an
# s_adj (seasonal adjustment) dimension gov_10dd_edpt1 doesn't have --
# NSA used deliberately (raw, not seasonally adjusted) to match how
# deficit/surplus is reported elsewhere on the site. NOT yet confirmed
# via an actual live API call from this build (same sandbox network
# limitation as everything else in this file) -- check the next real
# Actions log for "eurostat-gov_10q_ggdebt-GD-NO" / "eurostat-gov_10q_ggnfa-B9-NO"
# SUCCESS/FAIL lines to confirm this genuinely resolved the gap.
def fetch_eurostat_govfinance(dataset: str, na_item: str, freq: str = "A",
                               s_adj: str | None = None) -> list | None:
    extra = f"&freq={freq}"
    if s_adj:
        extra += f"&s_adj={s_adj}"
    url = (f"{EUROSTAT_STATS_BASE}/{dataset}?format=JSON&lang=EN"
          f"&geo=NO&sector=S13&unit=PC_GDP&na_item={na_item}{extra}"
          f"&sinceTimePeriod=2000")
    tag = f"eurostat-{dataset}-{na_item}"
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [{tag}] NO status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [{tag}] NO request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, f"{tag}-NO")
    except Exception as exc:
        print(f"  [{tag}] NO parsing failed: {exc}; "
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


# ---- OECD business confidence (Norway) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
NO_AREAS = ("NOR",)
OECD_QUERIES = [
    f"{OECD_BASE}/NOR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/NOR.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "NOR") not in NO_AREAS:
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
# Japan/India/Canada/Australia/South Korea, just pointed at Norway.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


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

# ---- World Bank (Norway) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/NOR/indicator/"
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
        ("cpi", lambda: fetch_oecd_cpi(("NOR",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
        ("debt_gdp", lambda: fetch_eurostat_govfinance("gov_10q_ggdebt", "GD", freq="Q"),
         "General government gross debt, % of GDP (Eurostat, quarterly)", "%", "quarters"),
        ("deficit", lambda: fetch_eurostat_govfinance("gov_10q_ggnfa", "B9", freq="Q", s_adj="NSA"),
         "General government net lending/borrowing, % of GDP (Eurostat, quarterly)", "%", "quarters"),
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

    # gdp_level / gdp_real: World Bank current-LCU and constant-LCU annual
    # GDP (NOK), handled separately (not in the generic extras loop above)
    # because both need the same scale correction the others don't --
    # these World Bank series report RAW kroner, not millions (same
    # scale-bug class as the NY.GDP.MKTP.CD/667-family series seen
    # elsewhere in this codebase). Divide by 1e6 so the site's "NOKm"
    # unit label is accurate, not off by a factor of a million. Retires
    # the old USD-fallback gdp_level and the Penn World Table gdp_real --
    # see BUG FIX note above.
    for name, code, kind in (
        ("gdp_level", "NY.GDP.MKTP.CN", "current"),
        ("gdp_real", "NY.GDP.MKTP.KN", "constant"),
    ):
        try:
            raw_gdp = fetch_worldbank(code)
            if not raw_gdp:
                raise ValueError("no usable response")
            scaled_gdp = [[p, round(v / 1e6, 1)] for p, v in raw_gdp]
            out["series"][name] = {
                "label": f"GDP, {kind} prices, NOK (World Bank, {code})",
                "unit": "NOKm", "freq": "years", "points": scaled_gdp,
            }
            print(f"  ok  {name:<16} {len(scaled_gdp):>5} observations "
                  f"({scaled_gdp[0][0]} to {scaled_gdp[-1][0]}, years) -- "
                  f"scaled from raw NOK to NOKm")
        except Exception as exc:
            failures.append(name)
            print(f"FAIL  {name:<16} {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-no.json") as f:
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
            fx_pts = fetch_fred("DEXNOUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "NOK/USD", "rate": fx_rate,
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

    with open("data-no.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-no.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
