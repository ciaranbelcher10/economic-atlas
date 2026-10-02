"""Fetch Japan economic series and write data-jp.json.

Run:  FRED_API_KEY=yourkey python3 fetch_jp.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

FIXED IN 7.6.4: cpi was previously wired to JPNCPIALLMINMEI, a FRED mirror
that stopped updating in June 2021 -- confirmed dead via its own FRED page
("from Jan 1955 to Jun 2021"). Removed from FRED_SERIES entirely (so a
future fetch failure can't silently fall back to serving 2021 data as if
current) and replaced with a live query against OECD's own SDMX prices
system (DSD_PRICES@DF_PRICES_ALL), the same underlying platform that
publishes OECD's monthly inflation press releases citing current Japan
CPI. The query structure (REF_AREA.FREQ.METHODOLOGY.MEASURE.UNIT_MEASURE.
EXPENDITURE.ADJUSTMENT.TRANSFORMATION) is sourced from OECD's own
generated example query, not guessed from nothing -- but hasn't been
personally executed end-to-end (no way to test sdmx.oecd.org from the
build sandbox), so treat the first live run as the real verification step
and check the Actions log for "ok  cpi" vs "FAIL  cpi".
"""

from __future__ import annotations

import json
import oecd_turn
import time
import os
import re
import sys
from datetime import datetime, timezone

import requests
import imf_weo
import series_guard

# Series this script is deliberately allowed to replace with a shorter or
# lower-frequency one. Without an entry here, series_guard keeps the previous
# series whenever the incoming one has less history, coarser frequency, or an
# older last period, which is what stops a rate-limited partial response from
# overwriting good data.
#
# Add an entry ONLY when intentionally swapping source, and say why, e.g.
#     ALLOW_SHRINK = {"ppi": "PPIACO -> PPIFID, final demand is the BLS headline"}
# Remove it once the new series has landed.
ALLOW_SHRINK = {}

# key: (fred_id, freq 'm'|'q', label, unit, transform None|'yoy'|'mom', scale)
# scale multiplies the raw FRED value before any transform. Use this to correct
# unit mismatches at the source rather than patching displayed numbers downstream.
# The OECD '667S' goods-trade family (exports/imports) reports PLAIN US DOLLARS,
# not millions -- verified against FRED's own "Units" field on the series page --
# so scale=1e-6 converts it to $m to match the declared unit and the bnD/bnD0
# chart formatters (which assume $m and divide by 1000 for $bn).
FRED_SERIES = {
    "gdp_level": ("JPNNGDP", "q", "GDP, nominal, SAAR", "\u00a5bn", None, 1.0),
    "gdp_real": ("JPNRGDPEXP", "q", "Real GDP, chained 2015 yen, SAAR", "\u00a5bn", None, 1.0),
    "gdp_growth": ("JPNRGDPEXP", "q", "Real GDP growth, QoQ", "%", "qoq", 1.0),
    "unemployment": ("LRHUTTTTJPM156S", "m", "Unemployment rate, SA", "%", None, 1.0),
    "boj_rate": ("IRSTCI01JPM156N", "m", "Call money rate (overnight)", "%", None, 1.0),
    "exports": ("XTEXVA01JPM667S", "m", "Exports of goods, $", "$m", None, 1e-6),
    "imports": ("XTIMVA01JPM667S", "m", "Imports of goods, $", "$m", None, 1e-6),
    "bond_yield_10y": ("IRLTLT01JPM156N", "m", "10-year government bond yield (JGB)", "%", None, 1.0),
}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def _period_back_n(per, n: int):
    """The period label n periods earlier, in the period's own unit."""
    s = str(per)
    if re.fullmatch(r"\d{4}-\d{2}", s):
        t = int(s[:4]) * 12 + (int(s[5:]) - 1) - n
        return "{}-{:02d}".format(t // 12, t % 12 + 1)
    if re.fullmatch(r"\d{4}-Q[1-4]", s):
        t = int(s[:4]) * 4 + (int(s[6]) - 1) - n
        return "{}-Q{}".format(t // 4, t % 4 + 1)
    if re.fullmatch(r"\d{4}", s):
        return str(int(s) - n)
    return None


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


def _period_back(per, months: int):
    """The period label `months` earlier. Handles YYYY-MM, YYYY-Qn and YYYY."""
    s = str(per)
    if re.fullmatch(r"\d{4}-\d{2}", s):
        t = int(s[:4]) * 12 + (int(s[5:]) - 1) - months
        return "{}-{:02d}".format(t // 12, t % 12 + 1)
    if re.fullmatch(r"\d{4}-Q[1-4]", s):
        steps = max(1, months // 3)
        t = int(s[:4]) * 4 + (int(s[6]) - 1) - steps
        return "{}-Q{}".format(t // 4, t % 4 + 1)
    if re.fullmatch(r"\d{4}", s):
        return str(int(s) - max(1, months // 12))
    return None


def transform(points: list, kind: str | None) -> list:
    """Rate of change matched BY PERIOD rather than by list position.

    This used to index backwards a fixed number of list slots
    (points[i - 12]), which compares the wrong periods whenever the source
    series has a hole in it. BLS published no October 2025 CPI during the
    shutdown, so every US CPI point from November 2025 onward was compared
    against the month before the one it should have been: August 2026 read
    3.71 where BLS published 3.4.

    Looking the counterpart up by period label means a gap yields no point
    rather than a wrong one, which is correct: the rate genuinely is not
    computable for that period.
    """
    if kind not in ("yoy", "mom", "qoq"):
        return points
    back = 12 if kind == "yoy" else 1
    by_period = {p[0]: p[1] for p in points}
    out = []
    for per, val in points:
        prev = _period_back(per, back)
        base = by_period.get(prev) if prev else None
        if not base:
            continue
        out.append([per, round((val / base - 1) * 100, 2)])
    return out


# ---- OECD business confidence (USA) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
JP_AREAS = ("JPN",)
OECD_QUERIES = [
    f"{OECD_BASE}/JPN.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/JPN.M.BCICP......?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=1990",
]


def fetch_oecd_bci() -> list | None:
    oecd_turn.check()  # rotate OECD requests across groups; see oecd_turn.py
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
                if low.get("REF_AREA", "JPN") not in JP_AREAS:
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


# ---- e-Stat (Statistics Bureau of Japan) live CPI ----
# OECD's DF_PRICES_ALL has no current Japan CPI (every JPN variant ends at
# the retired 2015 base), so this queries Japan's own statistics bureau via
# the e-Stat API with the ESTAT_APP_ID repository secret.
ESTAT_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
# 2025-base national CPI (消費者物価指数（2025年基準）), the Statistics Bureau's
# headline series since 28 Aug 2026. Confirmed by a live probe on 2 Oct 2026:
# table updated 2026-10-02; class "tab" holds 1=index, 2=change on the
# previous month (for monthly periods), 3=change on the same month a year
# earlier; all-items is cat01 0001; national is area 00000; index runs
# 1970-01 to 2026-08 (Aug 2026 = 102.2). The previous table, 0003427113
# (2020 base), is published alongside until December 2026 only.
#
# The rates are taken as PUBLISHED (tab 2 and 3), not recalculated from the
# index: across a rebasing the Bureau's official rates are not the same as
# rates recalculated from the linked index (June 2026: 1.6% official, 1.70%
# recalculated). If the published rates are missing, the rates are derived
# from the index as before, and the log says so.
ESTAT_CPI_STATS_DATA_ID = "0004052037"
ESTAT_ALL_ITEMS = "0001"
ESTAT_NATIONAL = "00000"

# Cached parse for this process: {"index": [...], "yoy": [...], "mom": [...]}
_ESTAT_CACHE: dict = {}


def _estat_cpi_parse(payload: dict):
    """Split one getStatsData reply into index / MoM / YoY series, each a
    sorted [[YYYY-MM, value], ...] list for all items, national, monthly."""
    root = payload.get("GET_STATS_DATA", {})
    result = root.get("RESULT", {})
    if str(result.get("STATUS", "0")) != "0":
        print(f"  [estat-cpi] API error status={result.get('STATUS')} "
              f"msg={result.get('ERROR_MSG')!r}")
        return None
    sd = root.get("STATISTICAL_DATA", {})
    objs = sd.get("CLASS_INF", {}).get("CLASS_OBJ", [])
    objs = [objs] if isinstance(objs, dict) else objs

    def classes(cid):
        for co in objs:
            if co.get("@id") == cid:
                items = co.get("CLASS", [])
                return [items] if isinstance(items, dict) else items
        return []

    names = {c.get("@code"): (c.get("@name") or "") for c in classes("cat01")}
    if "総合" not in names.get(ESTAT_ALL_ITEMS, ""):
        print(f"  [estat-cpi] cat01 {ESTAT_ALL_ITEMS} is {names.get(ESTAT_ALL_ITEMS)!r}, "
              f"not all items; refusing to guess")
        return None
    period_of = {}
    for tm in classes("time"):
        m = re.match(r"(\d{4})年(\d{1,2})月$", (tm.get("@name") or "").strip())
        if m:
            period_of[tm.get("@code")] = f"{m.group(1)}-{int(m.group(2)):02d}"
    tab_kind = {"1": "index", "2": "mom", "3": "yoy"}
    out = {"index": {}, "mom": {}, "yoy": {}}
    vals = sd.get("DATA_INF", {}).get("VALUE", [])
    vals = [vals] if isinstance(vals, dict) else vals
    for v in vals:
        if v.get("@cat01") != ESTAT_ALL_ITEMS or v.get("@area", ESTAT_NATIONAL) != ESTAT_NATIONAL:
            continue
        kind = tab_kind.get(v.get("@tab", "1"))
        period = period_of.get(v.get("@time"))
        if not kind or not period:
            continue
        try:
            out[kind][period] = float(v.get("$"))
        except (TypeError, ValueError):
            continue
    return {k: sorted([[p, x] for p, x in d.items()]) for k, d in out.items()}


def _estat_cpi() -> dict | None:
    if "parsed" in _ESTAT_CACHE:
        return _ESTAT_CACHE["parsed"]
    _ESTAT_CACHE["parsed"] = None
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        print("  [estat-cpi] no ESTAT_APP_ID set — skipping")
        return None
    # Narrowed to all items, national: the whole table is far past the
    # 100,000-value reply limit and would come back silently truncated.
    url = (f"{ESTAT_BASE}?appId={app_id}&statsDataId={ESTAT_CPI_STATS_DATA_ID}"
           f"&cdArea={ESTAT_NATIONAL}&cdCat01={ESTAT_ALL_ITEMS}"
           f"&metaGetFlg=Y&cntGetFlg=N&limit=100000")
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [estat-cpi] status={r.status_code}")
        r.raise_for_status()
        parsed = _estat_cpi_parse(r.json())
    except Exception as exc:
        print(f"  [estat-cpi] request failed: {exc}")
        return None
    if not parsed or not parsed["index"]:
        print("  [estat-cpi] no all-items national index in the reply")
        return None
    i = parsed["index"]
    print(f"  [estat-cpi] SUCCESS (2025 base): {len(i)} index points, {i[0][0]} to {i[-1][0]}; "
          f"published rates: {len(parsed['yoy'])} YoY, {len(parsed['mom'])} MoM")
    _ESTAT_CACHE["parsed"] = parsed
    return parsed


def fetch_estat_cpi_index() -> list | None:
    p = _estat_cpi()
    return p["index"] if p else None


def _published_or_derived(kind: str, how: str):
    """Published rates wherever the Bureau publishes them; rates derived from
    the index only for periods it does not (or for everything, if published
    rates are missing or behind the index). Never shorter than the index can
    support, so the shrink guard cannot hold on to the old table's series
    just because the published rates start later than the index."""
    p = _estat_cpi()
    if not p:
        return None
    derived = dict(transform(p["index"], how) or [])
    pub = dict(p[kind])
    if not pub or max(pub) != p["index"][-1][0]:
        print(f"  [estat-cpi] published {kind} rates missing or behind the index; "
              f"derived {len(derived)} from the index instead")
        return sorted([[k, v] for k, v in derived.items()]) or None
    filled = [k for k in derived if k not in pub]
    if filled:
        print(f"  [estat-cpi] {kind}: {len(pub)} published, {len(filled)} earlier "
              f"periods derived from the index ({min(filled)} to {max(filled)})")
    merged = {**derived, **pub}
    return sorted([[k, v] for k, v in merged.items()])


def fetch_estat_cpi() -> list | None:
    return _published_or_derived("yoy", "yoy")


def fetch_estat_cpi_mom() -> list | None:
    return _published_or_derived("mom", "mom")



# DSD_PRICES@DF_PRICES_ALL confirmed via OECD's own generated example query
# (dimension order REF_AREA.FREQ.METHODOLOGY.MEASURE.UNIT_MEASURE.EXPENDITURE.
# ADJUSTMENT.TRANSFORMATION). Not personally executed end-to-end -- the query
# structure is sourced from OECD's own documentation, not guessed from
# nothing, but treat the first live run as the real verification step and
# check the Actions log, same caveat as MoSPI.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"
# OECD is progressively migrating countries from the COICOP 1999 CPI
# classification (above) to COICOP 2018. Once a country's national
# statistics office migrates, new observations stop landing in the old
# dataflow: it keeps returning 200 OK with the last pre-migration data
# forever, so nothing here ever "fails" until it crosses max_age_days
# and the World Bank annual fallback quietly takes over. That is what
# stalled CPI for MX/CL/ZA/MA. This COICOP 2018 tier is the same fix
# already live in fetch_ch/dk/ie/no/pl/se/tr.py, where it is CONFIRMED
# WORKING in production: all seven of those countries now carry fresh
# monthly CPI, having previously stalled the same way.
OECD_PRICES_BASE_COICOP2018 = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
    oecd_turn.check()  # rotate OECD requests across groups; see oecd_turn.py
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
        # Matched by period, not by list position. A hole in the source
        # series would otherwise shift every later comparison by the size
        # of the hole, silently.
        by_period = {p[0]: p[1] for p in pts}
        out = []
        for per, val in pts:
            prev = _period_back_n(per, lag)
            base = by_period.get(prev) if prev else None
            if base:
                out.append([per, round((val / base - 1) * 100, 2)])
        return out or None

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

    # Candidate selection runs across EVERY dataflow/variant combo below,
    # rather than returning on the first combo that answers. Returning early
    # meant a newly migrated dataflow answering with a handful of recent
    # points beat the legacy dataflow holding a decade of history, and the
    # short series silently replaced the long one on the live page.
    # A series is only accepted on length grounds if nothing with a usable
    # amount of history is available at all.
    MIN_USABLE_POINTS = 24
    viable = []

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
        # Try COICOP 2018 first (fresher, for countries that have
        # migrated), then fall back to the legacy COICOP 1999 dataflow
        # (still the only source for countries that haven't migrated
        # yet). A country not yet on COICOP 2018 just falls through with
        # 0 usable rows from those attempts and picks up its existing
        # COICOP 1999 result exactly as before.
        bases = ((OECD_PRICES_BASE_COICOP2018, "C2018"), (OECD_PRICES_BASE, "C1999"))
        combos = [(base_url, base_tag, um, tc, ny, me, ad)
                  for base_url, base_tag in bases
                  for um, tc, ny, me, ad in attempts]
        # Doubling the attempts doubles this function's request volume,
        # which can tip OECD into rate-limiting the whole run. A small
        # delay between requests plus bailing out after repeated 429s
        # cuts this country's request count fast once the host is
        # already throttling, rather than burning all 8 combos.
        consecutive_429s = 0
        for base_url, base_tag, unit_measure, trans_code, needs_yoy, meth, adj in combos:
            if any(len(c[1]) >= MIN_USABLE_POINTS for c in viable):
                # A candidate with enough history and a fresh enough last
                # period is already in hand. The remaining variants cannot
                # improve on it, and every extra request feeds the 429
                # cascade that starves the countries running later in the
                # same job. This is NOT the early return removed earlier:
                # that one let a handful of recent points beat a decade of
                # history by answering first. This stops only on a
                # candidate that has already cleared the length bar, and
                # the attempt order puts the direct year-on-year variant
                # ahead of the index-derived one, so the longer series is
                # tried first by construction.
                print(f"  [oecd-cpi] {area} stopping early, already hold "
                      f"{max(len(c[1]) for c in viable)} usable points")
                break
            if consecutive_429s >= 2:
                print(f"  [oecd-cpi] {area} bailing out after {consecutive_429s} "
                      f"consecutive 429s, host is rate-limiting this run")
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
                    viable.append((last_period, out))
                    continue
                print(f"  [oecd-cpi] {tag} all series variants stale or "
                      f"unusable -- trying next combo")
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
    if viable:
        long_enough = [c for c in viable if len(c[1]) >= MIN_USABLE_POINTS]
        pool = long_enough or viable
        pool.sort(key=lambda c: (c[0], len(c[1])), reverse=True)
        chosen = pool[0][1]
        print(f"  [oecd-cpi] CHOSEN: {len(chosen)} points, "
              f"{chosen[0][0]} to {chosen[-1][0]} "
              f"(best of {len(viable)} viable candidate(s))")
        return chosen
    return None


# ---- World Bank (USA) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/JPN/indicator/"
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


def load_previous() -> dict:
    try:
        with open("data-jp.json") as f:
            old = json.load(f)
        return {k: v["points"][-1][0]
                for k, v in old.get("series", {}).items() if v.get("points")}
    except Exception:
        return {}


def _fx_rate_for_period(fx_hist, period, fallback):
    """Exchange rate in effect during `period`, not today's spot rate.

    The OECD "667S" merchandise-trade series are USD-denominated, and are
    converted to the page's own currency below. Converting every historical
    point at the LATEST spot rate silently rewrites history: a 1990 trade
    balance would be expressed at this month's exchange rate. The site's
    Dollarise feature exists precisely to avoid that, so the pipeline must
    not reintroduce it. Each point is converted at the rate for its own
    period instead, falling back to the nearest earlier rate, and only to
    `fallback` when no history is available at all.

    `fx_hist` is the ascending [[YYYY-MM, rate], ...] list returned by
    fetch_fred for the daily DEX* series (reduced to one point per month).
    """
    if not fx_hist:
        return fallback
    if len(period) == 7 and period[4] == "-":
        key = period
    elif "Q" in period:
        y, q = period.split("-Q")
        key = f"{y}-{int(q) * 3:02d}"
    else:
        key = f"{period[:4]}-12"
    best = None
    for p, v in fx_hist:
        if p <= key:
            best = v
        else:
            break
    return best if best is not None else fx_hist[0][1]


def main() -> int:
    previous = load_previous()
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
        ("debt_gdp", lambda: imf_weo.fetch("JPN", imf_weo.DEBT),
         "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
        ("deficit", lambda: imf_weo.fetch("JPN", imf_weo.DEFICIT),
         "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_estat_cpi() or fetch_oecd_cpi(("JPN",), "M"),
         "CPI, all items, YoY (e-Stat, 2025 base, Statistics Bureau of Japan)", "%", "months"),
        ("cpi_mom", lambda: fetch_estat_cpi_mom(),
         "CPI, all items, MoM (e-Stat, 2025 base, Statistics Bureau of Japan)", "%", "months"),
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

    try:
        with open("data-jp.json") as f:
            _prev_full_early = json.load(f)
    except Exception:
        _prev_full_early = {}

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run (see fetch_it.py/fetch_es.py for the incident this
    # closes -- FRED 429-rate-limited mid-run and wiped most of a
    # country's series in one shot, with nothing to fall back on).
    # Placed before this exact bailout so a run where everything fails
    # still gets rescued rather than giving up entirely. A second,
    # separate prev_full read further below (for new_points_meta
    # tracking) is untouched by this -- redundant but harmless.
    _prev_series_early = _prev_full_early.get("series", {})
    # Trade conversion below must only touch series fetched fresh this run:
    # a carried-over series is already in local currency, and for countries
    # whose converted unit keeps a bare $ it would otherwise be converted a
    # second time. See tools/test_trade_fx.py.
    _fresh_keys = set(out["series"])
    _guard_verdicts = series_guard.apply_guard(
        out["series"], _prev_series_early, allow_shrink=ALLOW_SHRINK)
    if not out.get("fx_to_usd") and _prev_full_early.get("fx_to_usd"):
        out["fx_to_usd"] = _prev_full_early["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    if "exports" in out["series"] and "imports" in out["series"]:
        imp = dict(out["series"]["imports"]["points"])
        tb = [[p, round(x - imp[p], 1)]
              for p, x in out["series"]["exports"]["points"] if p in imp]
        if tb:
            # Unit from the flows it is built from: carried-over flows are
            # already in yen and must not be labelled or converted as dollars.
            out["series"]["trade_balance"] = {
                "label": "Trade balance, goods (exports minus imports)",
                "unit": out["series"]["exports"]["unit"],
                "freq": "months", "points": tb}
            if "exports" in _fresh_keys and "imports" in _fresh_keys:
                _fresh_keys.add("trade_balance")
            else:
                _fresh_keys.discard("trade_balance")
            print(f"  ok  {'trade_balance':<16} {len(tb):>5} observations (derived)")

    try:
        with open("data-jp.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_meta = prev_full.get("new_points_meta")
    # migrating from the old pipeline (or a corrupted/missing meta file): back-date
    # everything to the last known-good run instead of "now", so turning this
    # tracking on (or recovering from a bad file) doesn't falsely flag every
    # series as freshly released.
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

    _fx_ok = False
    try:
        if key:
            fx_pts = fetch_fred("DEXJPUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "JPY/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide",
                                     "history": fx_pts}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                      f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points)")

                to_local = lambda v, per: v * _fx_rate_for_period(fx_pts, per, fx_rate)
                _fx_ok = True
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"] and tk in _fresh_keys:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v, p), 1)] for p, v in ser["points"]]
                            ser["unit"] = ser["unit"].replace("$", "¥", 1)
                            ser["label"] = ser["label"].replace(", $ ", ", ¥ ") \
                                                        .replace(", $", ", ¥")
                            print(f"  ok  {tk:<16} converted {'$'}->{'¥'} using {fx_rate}")
            else:
                print("note  fx_to_usd: no observations returned")
        else:
            print("note  fx_to_usd not set (no FRED_API_KEY) — "
                  "Dollarise will be unavailable on this page until next run.")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    # No exchange rate this run: a freshly fetched USD trade series would be
    # published unconverted. Keep last run's converted figures instead (or
    # leave the key out), so a page never shows dollars as local currency.
    if not _fx_ok:
        for tk in ("trade_balance", "exports", "imports"):
            ser = out["series"].get(tk)
            if tk in _fresh_keys and ser and ser["unit"].strip().startswith("$"):
                if tk in _prev_series_early:
                    out["series"][tk] = _prev_series_early[tk]
                    print(f"CARRIED OVER {tk}: no exchange rate this run to convert it")
                else:
                    del out["series"][tk]
                    print(f"FAIL  {tk:<16} no exchange rate this run to convert it; left out")

    # fx_to_eur (Markets section, Sep 2026): JPY/EUR, triangulated the same
    # way as Canada's CAD/EUR -- Japan's own fx_to_usd is "divide"
    # convention (JPY per 1 USD, e.g. ~150), so JPY per EUR is a
    # multiply-through: JPY-per-USD * USD-per-EUR (DEXUSEU, already
    # USD-per-1-EUR). Getting this backwards (dividing instead of
    # multiplying) would silently produce a plausible-looking but wrong
    # number, not an obvious crash.
    try:
        if key and out.get("fx_to_usd", {}).get("history"):
            eur_usd_hist = dict(fetch_fred("DEXUSEU", "d", key))
            jpy_usd_hist = dict(out["fx_to_usd"]["history"])
            cross = sorted(
                (period, round(jpy_usd_hist[period] * eur_usd_hist[period], 2))
                for period in jpy_usd_hist
                if period in eur_usd_hist
            )
            if cross:
                out["fx_to_eur"] = {"pair": "JPY/EUR", "rate": cross[-1][1],
                                     "as_of": cross[-1][0], "direction": "divide",
                                     "history": cross}
                print(f"  ok  fx_to_eur       {len(cross):>5} observations "
                      f"({cross[0][0]} to {cross[-1][0]}, months, triangulated)")
            else:
                print("note  fx_to_eur: no overlapping months -- skipped")
        else:
            print("note  fx_to_eur not set (fx_to_usd history unavailable this run)")
    except Exception as exc:
        print(f"FAIL  fx_to_eur        {exc}")

    with open("data-jp.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-jp.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
