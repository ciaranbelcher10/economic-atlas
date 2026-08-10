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
import os
import re
import sys
from datetime import datetime, timezone

import requests

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
    "debt_gdp": ("GGGDTAJPA188N", "a", "General government gross debt, % of GDP", "%", None, 1.0),
    "deficit": ("GGNLBAJPA188N", "a", "General government net lending/borrowing, % of GDP", "%", None, 1.0),
    "exports": ("XTEXVA01JPM667S", "m", "Exports of goods, $", "$m", None, 1e-6),
    "imports": ("XTIMVA01JPM667S", "m", "Imports of goods, $", "$m", None, 1e-6),
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


# ---- OECD business confidence (USA) — free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
JP_AREAS = ("JPN",)
OECD_QUERIES = [
    f"{OECD_BASE}/JPN.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/JPN.M.BCICP......?format=csvfile&startPeriod=1990",
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


# ---- e-Stat (Statistics Bureau of Japan) live CPI (post-8.3.2) ----
# OECD's DF_PRICES_ALL has no current Japan CPI at all (confirmed on a live
# 8.3.0 run -- every METHODOLOGY/ADJUSTMENT variant for JPN dead-ends at the
# retired 2015=100 base, June 2021). This queries Japan's own statistics
# bureau directly via the e-Stat API, using an ESTAT_APP_ID repository
# secret (same pattern as FRED_API_KEY/MOSPI creds -- a free, user-issued
# key, not something Claude can obtain). statsDataId "0003427113" is the
# long-run national CPI table (2020=100 base, the one currently in force --
# Japan's last base-year rebasing was Aug 2021, per e-Stat's own news
# archive, and no newer rebasing notice was posted as of this write-up) --
# sourced from public e-Stat API tutorials, not verified end-to-end from
# this sandbox (e-Stat isn't reachable from the build environment). Rather
# than hardcode a guessed category code for "all items" (cat01), this reads
# the response's own CLASS_INF metadata to find it by name, and does the
# same for the time-axis codes, so it's robust to code churn even if the
# guessed statsDataId itself turns out to need adjustment. Check the
# [estat-cpi] log lines on the first live run.
ESTAT_BASE = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"
ESTAT_CPI_STATS_DATA_ID = "0003427113"


def fetch_estat_cpi() -> list | None:
    app_id = os.environ.get("ESTAT_APP_ID")
    if not app_id:
        print("  [estat-cpi] no ESTAT_APP_ID set — skipping")
        return None

    url = (f"{ESTAT_BASE}?appId={app_id}&statsDataId={ESTAT_CPI_STATS_DATA_ID}"
           f"&cdArea=00000&metaGetFlg=Y&cntGetFlg=N")
    try:
        r = requests.get(url, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [estat-cpi] status={r.status_code}")
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        print(f"  [estat-cpi] request failed: {exc}")
        return None

    root = payload.get("GET_STATS_DATA", {})
    result = root.get("RESULT", {})
    if str(result.get("STATUS", "0")) != "0":
        print(f"  [estat-cpi] API error status={result.get('STATUS')} "
              f"msg={result.get('ERROR_MSG')!r}")
        return None

    stat_data = root.get("STATISTICAL_DATA", {})
    class_objs = stat_data.get("CLASS_INF", {}).get("CLASS_OBJ", [])
    if isinstance(class_objs, dict):
        class_objs = [class_objs]

    def classes_for(class_id: str) -> list:
        for co in class_objs:
            if co.get("@id") == class_id:
                items = co.get("CLASS", [])
                return [items] if isinstance(items, dict) else items
        return []

    # Find the "all items" (総合) category code -- exact match preferred
    # over e.g. "生鮮食品を除く総合" (all items less fresh food), which also
    # contains the substring "総合".
    cat_items = classes_for("cat01")
    all_items_code = None
    for c in cat_items:
        if c.get("@name") == "総合":
            all_items_code = c.get("@code")
            break
    if all_items_code is None:
        for c in cat_items:
            if "総合" in (c.get("@name") or ""):
                all_items_code = c.get("@code")
                print(f"  [estat-cpi] no exact '総合' match; falling back to "
                      f"{c.get('@name')!r} ({all_items_code})")
                break
    if all_items_code is None:
        print(f"  [estat-cpi] could not find an 'all items' category in "
              f"cat01 metadata ({len(cat_items)} categories present)")
        return None

    # Build time-code -> "YYYY-MM" from the time-axis metadata rather than
    # guessing e-Stat's internal time-code format.
    time_items = classes_for("time")
    period_of = {}
    for t in time_items:
        name = t.get("@name", "")
        m = re.match(r"(\d{4})年(\d{1,2})月", name)
        if m:
            period_of[t.get("@code")] = f"{m.group(1)}-{int(m.group(2)):02d}"

    values = stat_data.get("DATA_INF", {}).get("VALUE", [])
    if isinstance(values, dict):
        values = [values]
    rows = {}
    for v in values:
        if v.get("@cat01") != all_items_code:
            continue
        period = period_of.get(v.get("@time"))
        raw = v.get("$")
        if period is None or raw in (None, ""):
            continue
        try:
            rows[period] = float(raw)
        except ValueError:
            continue

    if not rows:
        print(f"  [estat-cpi] parsed response but got 0 matching rows "
              f"(cat01={all_items_code}, {len(values)} VALUE entries, "
              f"{len(period_of)} time codes resolved)")
        return None

    pts = sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
    yoy = transform(pts, "yoy")
    if not yoy:
        print(f"  [estat-cpi] {len(pts)} index points parsed but YoY "
              f"transform produced nothing")
        return None
    print(f"  [estat-cpi] SUCCESS: {len(yoy)} points, {yoy[0][0]} to {yoy[-1][0]}")
    return yoy



# DSD_PRICES@DF_PRICES_ALL confirmed via OECD's own generated example query
# (dimension order REF_AREA.FREQ.METHODOLOGY.MEASURE.UNIT_MEASURE.EXPENDITURE.
# ADJUSTMENT.TRANSFORMATION). Not personally executed end-to-end -- the query
# structure is sourced from OECD's own documentation, not guessed from
# nothing, but treat the first live run as the real verification step and
# check the Actions log, same caveat as MoSPI.
OECD_PRICES_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0"


def fetch_oecd_cpi(areas: tuple, freq: str) -> list | None:
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
        return [[pts[i][0], round((pts[i][1] / pts[i - lag][1] - 1) * 100, 2)]
                for i in range(lag, len(pts)) if pts[i - lag][1]] or None

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
                    return out
                print(f"  [oecd-cpi] {tag} all series variants stale or "
                      f"unusable -- trying next combo")
                continue
            except Exception as exc:
                print(f"  [oecd-cpi] {tag} parsing failed: {exc}")
                continue
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
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_estat_cpi() or fetch_oecd_cpi(("JPN",), "M"),
         "CPI, all items, YoY (e-Stat, Statistics Bureau of Japan)", "%", "months"),
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

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    if "exports" in out["series"] and "imports" in out["series"]:
        imp = dict(out["series"]["imports"]["points"])
        tb = [[p, round(x - imp[p], 1)]
              for p, x in out["series"]["exports"]["points"] if p in imp]
        if tb:
            out["series"]["trade_balance"] = {
                "label": "Trade balance, goods (exports minus imports)", "unit": "$m",
                "freq": "months", "points": tb}
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

    try:
        if key:
            fx_pts = fetch_fred("DEXJPUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "JPY/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

                to_local = lambda v: v * fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
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

    with open("data-jp.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-jp.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
