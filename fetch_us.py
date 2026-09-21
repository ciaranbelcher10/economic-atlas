"""Fetch US economic series and write data-us.json.

Run:  FRED_API_KEY=yourkey python3 fetch_us.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.
"""

from __future__ import annotations

import re
import oecd_turn
import json
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
ALLOW_SHRINK = {
    "cpi_mom": "one point fewer by design: Nov 2025 has no computable month on month value because BLS published no Oct 2025 CPI",
    "cpi_mom_sa": "one point fewer by design: Nov 2025 has no computable month on month value because BLS published no Oct 2025 CPI",
}

# key: (fred_id, freq 'm'|'q', label, unit, transform None|'yoy'|'mom')
FRED_SERIES = {
    "gdp_level": ("GDP", "q", "GDP, nominal, seasonally adjusted annual rate", "$bn", None),
    "gdp_real": ("GDPC1", "q", "Real GDP, chained 2017 dollars, SAAR", "$bn", None),
    "gdp_growth": ("A191RL1Q225SBEA", "q", "Real GDP growth, QoQ annualised", "%", None),
    "productivity": ("OPHNFB", "q", "Nonfarm business output per hour, index", "index", None),
    "unemployment": ("UNRATE", "m", "Unemployment rate, SA", "%", None),
    "employment": ("EMRATIO", "m", "Employment-population ratio, SA", "%", None),
    "participation": ("CIVPART", "m", "Labor force participation rate, SA", "%", None),
    # 12-month rates use the unadjusted indexes, which is how BLS publishes
    # them. The monthly change is served unadjusted as well, so a US month on
    # month rate is built the same way as every other country's on this site
    # (no other source in use publishes a seasonally adjusted monthly index).
    # BLS's own headline monthly print is the adjusted one, so it is kept
    # alongside under its own key and labelled, rather than dropped.
    "cpi": ("CPIAUCNS", "m", "CPI, all items, YoY, not seasonally adjusted", "%", "yoy"),
    "cpi_mom": ("CPIAUCNS", "m", "CPI, all items, MoM, not seasonally adjusted", "%", "mom"),
    "cpi_mom_sa": ("CPIAUCSL", "m", "CPI, all items, MoM, seasonally adjusted", "%", "mom"),
    "core_cpi": ("CPILFENS", "m", "Core CPI (ex food & energy), YoY, not seasonally adjusted", "%", "yoy"),
    "ppi": ("PPIFID", "m", "PPI, final demand, YoY", "%", "yoy"),
    "pce": ("PCEPI", "m", "PCE price index (Fed's preferred gauge), YoY", "%", "yoy"),
    "fed_funds": ("FEDFUNDS", "m", "Effective federal funds rate", "%", None),
    # The FOMC sets a target RANGE, and has since December 2008; that range,
    # not the effective rate above, is the policy decision headlines quote.
    # Both bounds are daily, so they are reduced to the month-end value.
    "fed_funds_upper": ("DFEDTARU", "m", "Federal funds target range, upper bound", "%", "eom"),
    "fed_funds_lower": ("DFEDTARL", "m", "Federal funds target range, lower bound", "%", "eom"),
    "debt_gdp": ("GFDEGDQ188S", "q", "Federal debt, % of GDP", "%", None),
    "net_debt": ("GFDEBTN", "q", "Total federal public debt", "$m", None),
    "deficit": ("MTSDS133FMS", "m", "Federal surplus or deficit, monthly", "$m", None),
    "trade_balance": ("BOPGSTB", "m", "Trade balance, goods & services, SA", "$m", None),
    "exports": ("BOPTEXP", "m", "Exports, goods & services, SA", "$m", None),
    "imports": ("BOPTIMP", "m", "Imports, goods & services, SA", "$m", None),
}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    return f"{y}-{m:02d}" if freq == "m" else f"{y}-Q{(m - 1) // 3 + 1}"


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
    return points


def _period_back(per, months: int):
    """The period label `months` earlier. Handles YYYY-MM, YYYY-Qn and YYYY."""
    s = str(per)
    if re.fullmatch(r"\d{4}-\d{2}", s):
        t = int(s[:4]) * 12 + (int(s[5:]) - 1) - months
        return "%d-%02d" % (t // 12, t % 12 + 1)
    if re.fullmatch(r"\d{4}-Q[1-4]", s):
        steps = max(1, months // 3)
        t = int(s[:4]) * 4 + (int(s[6]) - 1) - steps
        return "%d-Q%d" % (t // 4, t % 4 + 1)
    if re.fullmatch(r"\d{4}", s):
        return str(int(s) - max(1, months // 12))
    return None


def month_end(points: list) -> list:
    """Collapse a daily series to one point per period: the last day's value.

    The federal funds target range is published daily, and both FRED
    fetchers here label each observation by its month, so a daily series
    arrives as about thirty points sharing one label. FRED returns dates in
    ascending order and the sort that follows is stable, so the last point
    kept for each label is the latest day in it -- the target in force at
    the end of that month, which is the figure a monthly chart should show.
    """
    last = {}
    for per, val in points:
        last[per] = val
    return [[per, last[per]] for per in sorted(last)]


def transform(points: list, kind: str | None) -> list:
    """Year on year or month on month rate, matched BY PERIOD, not by position.

    This used to index backwards a fixed number of list slots
    (points[i - 12]), which compares the wrong months whenever the source
    series has a hole in it. BLS published no October 2025 CPI during the
    shutdown, so every US CPI point from November 2025 onward was compared
    against the month before the one it should have been. August 2026 read
    3.71% where BLS published 3.4%.

    Looking the counterpart up by period label means a gap yields no point
    rather than a wrong one, which is correct: the rate genuinely is not
    computable for that month.
    """
    if kind == "eom":
        return month_end(points)
    if kind not in ("yoy", "mom"):
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
OECD_QUERIES = [
    f"{OECD_BASE}/USA.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/USA.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "USA") != "USA":
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


# ---- World Bank (USA) — free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/USA/indicator/"
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
        with open("data-us.json") as f:
            old = json.load(f)
        return {k: v["points"][-1][0]
                for k, v in old.get("series", {}).items() if v.get("points")}
    except Exception:
        return {}


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
        for name, (sid, freq, label, unit, tf) in FRED_SERIES.items():
            try:
                points = transform(fetch_fred(sid, freq, key), tf)
                if not points:
                    raise ValueError("no observations")
                fr = "months" if freq == "m" else "quarters"
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
        with open("data-us.json") as f:
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

    with open("data-us.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-us.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
