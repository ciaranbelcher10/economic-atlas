"""Fetch Morocco economic series and write data-ma.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ma.py
Sources: FRED (free key required), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

WHY THIS PAGE WILL LOOK THINNER THAN ISRAEL/MEXICO/BRAZIL/SOUTH AFRICA
(read this before "fixing" a missing tile -- these are documented,
deliberate gaps, not bugs):

Morocco is not an OECD member and not one of the OECD's "key partner"
countries (Brazil, China, India, Indonesia, South Africa) either -- it
simply has much thinner free/live data coverage on FRED than any country
built so far. Desk research (not a live run) found:

- NO live FX series. The only two FRED series for the dirham
  (XRNCUSMAA618NRUG, FXRATEMAA618NUPN) are both long dead -- the most
  recent stopped in 2019, the other in 2010. No daily H.10-style mirror
  exists like DEXMXUS/DEXBZUS/DEXSFUS did for the last three countries.
  A last-resort OECD quarterly-average-rate attempt is included below
  (the same fallback pattern that worked for Israel), but it may well
  fail too -- if it does, Dollarise will simply have nothing to convert,
  same graceful handling as every other missing-data case on this site.
- NO quarterly GDP mirror found. Unlike every country built so far,
  there's no IMF IFS quarterly nominal/real GDP series for Morocco on
  FRED. gdp_level and gdp_real both come from World Bank ANNUAL data
  instead (current US$ and constant US$ respectively) -- this actually
  means Morocco gets a working "Make it real" toggle despite being
  annual-only, which Israel never got at all.
- NO unemployment series beyond a youth-specific one. Total unemployment
  comes from World Bank's annual indicator instead.
- NO bond yield series found at all. Not included; this is a genuine
  gap, not a guessed-and-failed ID (the Brazil/Israel lesson: don't
  guess repeatedly at IDs that don't exist, document the gap instead).
- debt_gdp/deficit and trade_balance/business_confidence/cpi all follow
  the same FRED/OECD patterns already proven for other countries, but
  NONE of these were individually confirmed to exist for Morocco before
  writing this -- treat every "ok" or "FAIL" in the first Actions log
  as the real answer, not this docstring.
"""

from __future__ import annotations

import re
import json
import time
import os
import sys
from datetime import datetime, timezone

import requests
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

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
# debt_gdp, deficit and trade_balance were removed from here after being
# confirmed genuinely dead on FRED (400 Bad Request on every live run, not
# a transient failure) -- GGGDTAMAA188N, GGNLBAMAA188N and XTNTVA01MAQ667S
# do not exist as FRED series. debt_gdp/deficit are now sourced from World
# Bank instead (see the extras list below); trade_balance has no clean
# World Bank $ equivalent (only a %-of-GDP balance exists, which would be
# a unit mismatch against every other country's $m-labeled trade_balance),
# so it remains a documented gap rather than a guessed-at replacement.
FRED_SERIES = {}

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
    return f"{y}-{m:02d}"


def _is_future_period(period: str, freq: str = "m") -> bool:
    """True if `period` covers time that has not finished yet, so the value
    cannot be a real observation.

    Some IMF REO/WEO-derived FRED mirrors (e.g. the annual *PPPT /
    GGXWDGGDP / GGXCNLGDP series) bundle several years of forward
    projections into the same series as real observations, with no flag
    distinguishing actual from forecast. Anything dated beyond the current
    year is always a projection.

    For ANNUAL series the current year is a projection too: the year has
    not finished, so the IMF's figure for it is a forecast, not an outturn.
    Publishing it would put a forecast on the site with a green
    "updated on schedule" freshness light, which contradicts the site's
    data-only promise. Monthly and quarterly series are trimmed only
    beyond the current year, since a completed month or quarter inside the
    current year is a genuine observation.
    """
    try:
        year = int(period[:4])
    except (ValueError, TypeError):
        return False
    this_year = datetime.now(timezone.utc).year
    if freq == "a":
        return year >= this_year
    return year > this_year


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
    points = sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])
    points = [p for p in points if not _is_future_period(p[0], freq)]
    return points


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


# ---- OECD business confidence (Morocco) -- free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
MA_AREAS = ("MAR",)
OECD_QUERIES = [
    f"{OECD_BASE}/MAR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/MAR.M.BCICP......?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "MAR") not in MA_AREAS:
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

# ---- OECD live CPI -- same fix proven for six other countries, worth
# trying even for a non-member/non-partner country ----
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

# ---- World Bank (Morocco) -- free API, no key. Carries more weight
# here than for other countries: GDP, real GDP, unemployment and CPI
# fallback all come from here rather than FRED/OECD. ----
WB_URL = ("https://api.worldbank.org/v2/country/MAR/indicator/"
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


IMF_CPI_URLS = (
    # IMF retired the legacy Data Services host on 5 November 2025. The
    # pipeline log for 2026-09-14 shows dataservices.imf.org failing DNS
    # resolution outright, not returning 404, so that route is gone rather
    # than merely changed.
    #
    # Current portal is data.imf.org, served by an SDMX 3.0 REST API at
    # api.imf.org. URL shape:
    #   /external/sdmx/3.0/data/dataflow/{agency}/{dataflow}/{version}/{key}
    # Key is COUNTRY.INDICATOR.COVERAGE.MEASURE.FREQ, so MAR.CPI._T.IX.M is
    # Morocco, consumer prices, all items, index, monthly. Asking for CSV
    # gives COUNTRY, TIME_PERIOD, OBS_VALUE with periods as 2026-M07.
    #
    # Note IFS itself was split across thematic dataflows with no official
    # crosswalk, so the old PCPI_IX code does not resolve anywhere. CPI is
    # its own dataflow now and is the right one for this.
    "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/"
    "{area}.CPI._T.IX.M?c[TIME_PERIOD]=ge:2010-M01",
)

# A monthly CPI more than this far past its last period is a dead mirror,
# not a slow publisher. Rejecting here rather than relying on series_guard
# keeps the reason visible in the pipeline log.
IMF_MAX_AGE_DAYS = 400


def _imf_age_days(period: str) -> float:
    try:
        y, m = str(period).replace("M", "-").split("-")[:2]
        dt = datetime(int(y), int(m), 1, tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except Exception:
        return 1e9


def fetch_imf_cpi(area: str) -> list | None:
    """Monthly all-items CPI index from the IMF data portal, as a YoY rate.

    Returns None on any failure, which leaves the caller's next fallback to
    take over. That matters: this endpoint has not been reachable from the
    build environment to confirm Morocco is present in the dataflow, so a
    silent, harmless failure is the designed outcome if it is not.
    """
    import csv
    import io
    for template in IMF_CPI_URLS:
        url = template.format(area=area)
        tag = "CPI/" + area
        try:
            r = requests.get(url, timeout=60,
                             headers={"Accept": "text/csv",
                                      "User-Agent": "economic-atlas/0.1"})
            print(f"  [imf-cpi] {tag} status={r.status_code}")
            r.raise_for_status()
            text = r.text
        except Exception as exc:
            print(f"  [imf-cpi] {tag} request failed: {exc}")
            continue

        try:
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception as exc:
            print(f"  [imf-cpi] {tag} CSV parse failed: {exc}")
            continue
        if not rows:
            print(f"  [imf-cpi] {tag} no rows returned")
            continue

        index = []
        for row in rows:
            per = (row.get("TIME_PERIOD") or "").strip()
            val = (row.get("OBS_VALUE") or "").strip()
            if not per or not val:
                continue
            per = per.replace("-M", "-")          # 2026-M07 -> 2026-07
            if not re.fullmatch(r"\d{4}-\d{2}", per):
                continue
            try:
                index.append([per, float(val)])
            except ValueError:
                continue
        index.sort(key=lambda p: p[0])
        if len(index) < 24:
            print(f"  [imf-cpi] {tag} only {len(index)} usable index points "
                  f"from {len(rows)} rows")
            continue

        age = _imf_age_days(index[-1][0])
        if age > IMF_MAX_AGE_DAYS:
            print(f"  [imf-cpi] {tag} REJECTED stale: {len(index)} points "
                  f"ending {index[-1][0]} ({age:.0f} days old, "
                  f"limit {IMF_MAX_AGE_DAYS})")
            continue

        by_period = {p[0]: p[1] for p in index}
        yoy = []
        for per, val in index:
            prev = _period_back_n(per, 12)
            base = by_period.get(prev) if prev else None
            if base:
                yoy.append([per, round((val / base - 1) * 100, 2)])
        if not yoy:
            print(f"  [imf-cpi] {tag} YoY transform produced nothing")
            continue
        print(f"  [imf-cpi] {tag} SUCCESS: {len(yoy)} points, "
              f"{yoy[0][0]} to {yoy[-1][0]}")
        return yoy
    return None

def fetch_cpi_with_fallback() -> tuple[list | None, str]:
    """Try OECD live CPI first, then IMF monthly, then World Bank annual.

    Morocco is not published in either OECD prices dataflow: both
    DSD_PRICES_COICOP2018 and DSD_PRICES return 404 for MAR on every
    variant (verified directly against the endpoint on 2026-09-13, and
    visible as 404s in the pipeline log). The OECD attempt is kept in
    case that changes, but it is not expected to succeed today, which is
    why the IMF tier sits between it and the annual World Bank series.
    """
    # OECD does not publish Morocco in either prices dataflow. Every key
    # variant returns 404 on DSD_PRICES_COICOP2018 and on DSD_PRICES,
    # verified directly against the endpoint on 2026-09-13 and visible as
    # 404s in the pipeline log. The call is skipped rather than made,
    # because the 8 requests it costs are spent before twelve countries
    # that run later in the same job reach OECD at all, and they are the
    # ones currently losing their CPI to 429s.
    # To restore if OECD ever adds Morocco, uncomment the next line.
    # pts = fetch_oecd_cpi(("MAR",), "M")
    pts = None
    if pts:
        return pts, "OECD live prices system"
    print("  [cpi] OECD attempt exhausted, trying IMF monthly CPI")
    pts = fetch_imf_cpi("MA")
    if pts:
        return pts, "IMF, monthly"
    print("  [cpi] IMF attempt exhausted, falling back to World Bank annual CPI")
    pts = fetch_worldbank("FP.CPI.TOTL.ZG")
    if pts:
        return pts, "World Bank, annual"
    return None, ""


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

    extras = [
        # business_confidence is not fetched for Morocco. OECD does not
        # publish it: the BCI endpoint returns 404 for MAR, and the series
        # has never been present in any of the 689 recorded revisions of
        # data-ma.json. The 3 requests it cost were spent before twelve
        # later countries reached OECD. To restore, re-add the tuple:
        #   ("business_confidence", lambda: fetch_oecd_bci(),
        #    "Business confidence indicator, LT avg = 100 (OECD BCICP)",
        #    "index", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
        ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
         "Unemployment, % of total labor force (World Bank, annual)", "%", "years"),
        ("gdp_level", lambda: [[p, round(v / 1e6, 1)] for p, v in (fetch_worldbank("NY.GDP.MKTP.CN") or [])],
         "GDP, current prices, MAD (World Bank, NY.GDP.MKTP.CN, annual)", "MADm", "years"),
        ("gdp_real", lambda: [[p, round(v / 1e6, 1)] for p, v in (fetch_worldbank("NY.GDP.MKTP.KN") or [])],
         "GDP, constant prices, MAD (World Bank, NY.GDP.MKTP.KN, annual)", "MADm", "years"),
        ("debt_gdp", lambda: fetch_fred("MARGGDGDPGDPPT", "a", key) if key else None,
         "Total government debt, general government, % of GDP (IMF MENA REO)", "%", "years"),
        ("deficit", lambda: fetch_worldbank("GC.NLD.TOTL.GD.ZS"),
         "Net lending/net borrowing, % of GDP (World Bank, annual)", "%", "years"),
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

    if "debt_gdp" not in out["series"]:
        # IMF MENA REO's MARGGDGDPGDPPT didn't come back with anything
        # usable. Fall back to the old World Bank central-government
        # series -- it's stuck at 2011 (WDI simply stopped publishing this
        # specific indicator for Morocco), so it's a last resort, not a
        # fix, but a stale number with its staleness disclosed is still
        # better than nothing at all.
        try:
            wb_pts = fetch_worldbank("GC.DOD.TOTL.GD.ZS")
            if wb_pts:
                out["series"]["debt_gdp"] = {
                    "label": "Central government debt, total, % of GDP (World Bank, annual "
                             "-- STALE: this WDI series stopped being published for Morocco "
                             "after 2011, kept only as a last-resort fallback)",
                    "unit": "%", "freq": "years", "points": wb_pts,
                }
                print(f"  ok  debt_gdp (WB stale fallback) {len(wb_pts):>5} observations "
                      f"({wb_pts[0][0]} to {wb_pts[-1][0]}, years)")
                if "debt_gdp" in failures:
                    failures.remove("debt_gdp")
        except Exception as exc:
            print(f"FAIL  debt_gdp (WB stale fallback) {exc}")

    # CPI handled separately since it has a two-stage fallback (OECD, then
    # World Bank annual) rather than a single source.
    try:
        cpi_points, cpi_source = fetch_cpi_with_fallback()
        if not cpi_points:
            raise ValueError("no usable response from OECD or World Bank")
        out["series"]["cpi"] = {
            "label": f"CPI, all items, YoY ({cpi_source})", "unit": "%",
            "freq": "months" if cpi_source.startswith("OECD") else "years",
            "points": cpi_points}
        print(f"  ok  cpi              {len(cpi_points):>5} observations "
              f"({cpi_points[0][0]} to {cpi_points[-1][0]}, via {cpi_source})")
    except Exception as exc:
        failures.append("cpi")
        print(f"FAIL  cpi              {exc}")

    try:
        with open("data-ma.json") as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}

    # Carry forward any series that failed THIS run but succeeded on a
    # previous run, so a transient failure (confirmed Aug 2026: FRED
    # itself 429-rate-limited mid-run and took out most of a country's
    # series in one shot -- Italy and Spain lost 7-8 series each with
    # no fallback, since this protection previously only existed on 9
    # countries that had needed it for a different, earlier reason)
    # doesn't wipe good data from the live page and leave the country's
    # whole page blank instead of a disclosed-stale reading. Placed
    # BEFORE the "nothing fetched" bailout below (matching the pattern
    # already used elsewhere) so a run where every series fails still
    # gets rescued by carried-over data rather than giving up entirely.
    _prev_series = prev_full.get("series", {})
    _guard_verdicts = series_guard.apply_guard(
        out["series"], _prev_series, allow_shrink=ALLOW_SHRINK)
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

    # fx_to_usd: switched (Aug 2026) from "no confirmed live FX series"
    # to World Bank PA.NUS.FCRF -- re-checked and confirmed a genuine,
    # live, ongoing World Bank indicator page exists for Morocco (IMF
    # IFS-sourced, "Official exchange rate, LCU per US$"), back to
    # 1960 -- ANNUAL resolution only, same tradeoff already accepted for
    # Poland/Turkey/Chile/Colombia/Argentina/Indonesia/Israel. No live
    # Fed H.10-style daily series has ever existed for the dirham
    # (confirmed via search -- the only FRED alternative found,
    # XRNCUSMAA618NRUG, a Penn World Table series, stopped updating in
    # 2019). Needs no FRED_API_KEY, so this runs unconditionally.
    try:
        fx_pts = fetch_worldbank("PA.NUS.FCRF")
        if fx_pts:
            fx_period, fx_rate = fx_pts[-1]
            out["fx_to_usd"] = {"pair": "MAD/USD", "rate": fx_rate,
                                 "as_of": fx_period, "direction": "divide",
                                 "history": fx_pts}
            print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                  f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points, annual)")
        else:
            print("note  fx_to_usd: no observations returned")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-ma.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ma.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
