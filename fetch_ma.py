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

import json
import os
import sys
from datetime import datetime, timezone

import requests

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


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    if freq == "a":
        return y
    if freq == "q":
        return f"{y}-Q{(m - 1) // 3 + 1}"
    return f"{y}-{m:02d}"


def _is_future_period(period: str) -> bool:
    """True if `period` (a fred_period-format string: 'YYYY', 'YYYY-Qn', or
    'YYYY-MM') refers to a year beyond the current calendar year. Some IMF
    REO/WEO-derived FRED mirrors bundle several years of forward projections
    into the same series as real observations, with no flag distinguishing
    actual from forecast. We only want actual/estimated-to-date figures on
    the site, so any point dated beyond the current year is dropped at
    fetch time."""
    try:
        year = int(period[:4])
    except (ValueError, TypeError):
        return False
    return year > datetime.now(timezone.utc).year


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
    points = [p for p in points if not _is_future_period(p[0])]
    return points


def transform(points: list, kind: str | None) -> list:
    if kind not in ("yoy", "mom", "qoq"):
        return points
    lag = 12 if kind == "yoy" else 1
    return [[points[i][0], round((points[i][1] / points[i - lag][1] - 1) * 100, 2)]
            for i in range(lag, len(points)) if points[i - lag][1]]


# ---- OECD business confidence (Morocco) -- free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
MA_AREAS = ("MAR",)
OECD_QUERIES = [
    f"{OECD_BASE}/MAR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/MAR.M.BCICP......?format=csvfile&startPeriod=1990",
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


def fetch_cpi_with_fallback() -> tuple[list | None, str]:
    """Try OECD live CPI first; if that fails, fall back to World Bank's
    annual CPI indicator rather than showing nothing at all."""
    pts = fetch_oecd_cpi(("MAR",), "M")
    if pts:
        return pts, "OECD live prices system"
    print("  [cpi] OECD attempt exhausted, falling back to World Bank annual CPI")
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
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
        ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
         "Unemployment, % of total labor force (World Bank, annual)", "%", "years"),
        ("gdp_level", lambda: fetch_worldbank("NY.GDP.MKTP.CD"),
         "GDP, nominal, current US$ (World Bank, annual)", "$", "years"),
        ("gdp_real", lambda: fetch_worldbank("NY.GDP.MKTP.KD"),
         "GDP, real, constant 2015 US$ (World Bank, annual)", "$", "years"),
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

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-ma.json") as f:
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

    # No confirmed live FX series exists for the dirham -- unlike Israel,
    # where a genuine (if undocumented-until-tried) OECD quarterly mirror
    # existed, desk research turned up nothing usable here, and inventing
    # a plausible-looking API call to "try" would just be guessing dressed
    # up as due diligence. Documenting the gap honestly instead: Dollarise
    # will have nothing to convert, which the shared frontend code already
    # handles gracefully.
    print("note  fx_to_usd: no confirmed live FX series found for the "
          "dirham -- Dollarise will be unavailable on this page unless "
          "one is found and wired in later.")

    with open("data-ma.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ma.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
