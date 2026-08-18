"""Fetch Israel economic series and write data-il.json.

Run:  FRED_API_KEY=yourkey python3 fetch_il.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank.
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

VERIFICATION NOTES (checked against each series before wiring in, same
discipline as every other country -- these are desk-research checks via
each series' own FRED page, NOT a live end-to-end run, so treat every one
of these as "expected to work, confirm in the first Actions log"):

- unemployment (LRHUTTTTILM156S), bond_yield_10y (IRLTLT01ILM156N),
  trade_balance (XTNTVA01ILQ667S): confirmed working.
  debt_gdp / deficit: FRED's usual IMF WEO series (GGGDTAILA188N / GGNLBAILA188N)
  returned a 400 Bad Request on the first live run -- Israel isn't covered
  by that particular FRED mirror. Switched to World Bank indicators instead
  (GC.DOD.TOTL.GD.ZS for debt, GC.BAL.CASH.GD.ZS for deficit), using the
  same fetch_worldbank() already proven for fdi/current_account below.
  trade_balance (XTNTVA01ILQ667S): these follow the exact naming
  convention already confirmed working for AU/CA/KR/JP/IN (just the
  country-code segment swapped to IL), so confidence is reasonably high,
  but none of these were individually opened and checked the way the GDP
  series below were -- if any come back FAIL in the log, that's why.
- gdp_level / gdp_real: Israel's OECD-mirrored quarterly GDP on FRED
  (ISRGDPNQDSMEI, the equivalent of South Korea's NGDPSAXDCKRQ) was
  checked directly and is DEAD -- last observation Q3 2023, "Next Release
  Date: Not Available". This is the same "stale FRED MEI mirror" problem
  that hit Japan's CPI, just for GDP instead. World Bank's annual GDP
  indicators were used instead -- but the FIRST version of this fetch
  (before Aug 2026) used the USD-only NY.GDP.MKTP.CD, with no gdp_real
  at all, on a "no verified local-currency source" claim that turned out
  to be false (checked directly against World Bank's own indicator pages
  -- NY.GDP.MKTP.CN / NY.GDP.MKTP.KN genuinely exist for Israel, same
  "confidently-wrong disclosed gap" already caught for Norway/Colombia/
  Chile). Fixed to use the genuine ILS-denominated series for both --
  lower resolution than other countries' quarterly figure (this is
  annual only), a real and honest gap versus the rest of the site, not a
  bug. A live quarterly OECD SDMX query (DSD_NAMAIN1@DF_QNA_EXPENDITURE_GROWTH_OECD) was considered
  for gdp_growth but NOT attempted here -- that dataset's dimension
  structure is materially more complex than the prices one CPI already
  uses successfully, and guessing it blind risked shipping something
  wrong rather than absent. Revisit once there's a channel to actually
  test SDMX queries live rather than write them from documentation alone.
- cpi: wired in directly via OECD's live SDMX prices system
  (DSD_PRICES@DF_PRICES_ALL), the same fix already used for Japan, India,
  Canada, Australia and South Korea, precisely BECAUSE FRED's own mirror
  for Israeli CPI has the same discontinuation risk as the GDP one above.
  Same query structure, same confidence level as those fixes.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern already used for every other country. Best-effort.
- fx_to_usd: no FRED daily H.10-style series was found for the shekel
  (unlike DEXKOUS for the won) -- the closest available is an OECD
  quarterly average-rate mirror (CCUSMA02ILQ618N), used here on a
  best-effort basis. If it also turns out to be stale or absent, the
  existing "Dollarise will be unavailable on this page until next run"
  fallback already in the shared frontend code handles that gracefully --
  it was written for exactly this situation.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
# - participation_rate (LRAC64TTILQ156S) / employment_rate (LREM64TTILQ156S): OECD infra-annual labour-statistics FRED family, quarterly, ages 15-64. Same pattern confirmed live for Germany (pilot); inferred-by-pattern for Israel -- not individually confirmed, check the first Actions log.
FRED_SERIES = {
    "unemployment": ("LRHUTTTTILM156S", "m", "Unemployment rate, 15+, SA", "%", None, 1.0),
    "participation_rate": ("LRAC64TTILQ156S", "q", "Labour force participation rate, 15-64, SA", "%", None, 1.0),
    "employment_rate": ("LREM64TTILQ156S", "q", "Employment rate, 15-64, SA", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01ILM156N", "m", "10-year government bond yield", "%", None, 1.0),
    "trade_balance": ("XTNTVA01ILQ667S", "q", "Trade balance, goods, $", "$m", None, 1e-6),
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


# ---- OECD business confidence (Israel) -- free SDMX API, no key ----
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
IL_AREAS = ("ISR",)
OECD_QUERIES = [
    f"{OECD_BASE}/ISR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/ISR.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "ISR") not in IL_AREAS:
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

# ---- OECD live CPI -- same fix already proven for Japan/India/Canada/
# Australia/South Korea, applied here because Israel's FRED "MEI" mirror
# carries the same discontinuation risk documented above for GDP.
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

# ---- World Bank (Israel) -- free API, no key ----
WB_URL = ("https://api.worldbank.org/v2/country/ISR/indicator/"
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

    # gdp_level / gdp_real: BUG FIX (Aug 2026 continued rollout). Both
    # were left on World Bank USD (NY.GDP.MKTP.CD) or missing entirely
    # (gdp_real never existed for Israel at all) -- checked directly
    # against World Bank's own indicator pages and NY.GDP.MKTP.CN (GDP,
    # current LCU) / NY.GDP.MKTP.KN (GDP, constant LCU) genuinely exist
    # for Israel, same "confidently-wrong disclosed gap" already caught
    # for Norway/Colombia/Chile in earlier sessions. This is what makes
    # both "Dollarise" AND "Make it real" mean something for Israel --
    # previously gdp_level was USD-only (Dollarise silently did
    # nothing) and there was no gdp_real at all (the "Make it real"
    # toggle was permanently disabled on this page).
    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("ISR",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
        ("gdp_level", lambda: [[p, round(v / 1e6, 1)] for p, v in (fetch_worldbank("NY.GDP.MKTP.CN") or [])],
         "GDP, current prices, ILS (World Bank, NY.GDP.MKTP.CN, annual)", "\u20aam", "years"),
        ("gdp_real", lambda: [[p, round(v / 1e6, 1)] for p, v in (fetch_worldbank("NY.GDP.MKTP.KN") or [])],
         "GDP, constant prices, ILS (World Bank, NY.GDP.MKTP.KN, annual)", "\u20aam", "years"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank)", "%", "years"),
        ("debt_gdp", lambda: fetch_fred("QILGAM770A", "a", key) if key else None,
         "Total credit to general government, adjusted for breaks, % of GDP (BIS)", "%", "years"),
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
        # BIS's QILGAM770A didn't come back with anything usable. Fall
        # back to the old World Bank central-government series -- it's
        # stuck at 1999 (WDI simply stopped publishing this specific
        # indicator for Israel), so it's a last resort, not a fix, but a
        # stale number with its staleness disclosed is still better than
        # nothing at all.
        try:
            wb_pts = fetch_worldbank("GC.DOD.TOTL.GD.ZS")
            if wb_pts:
                out["series"]["debt_gdp"] = {
                    "label": "Central government debt, % of GDP (World Bank, annual -- "
                             "STALE: this WDI series stopped being published for Israel "
                             "after 1999, kept only as a last-resort fallback)",
                    "unit": "%", "freq": "years", "points": wb_pts,
                }
                print(f"  ok  debt_gdp (WB stale fallback) {len(wb_pts):>5} observations "
                      f"({wb_pts[0][0]} to {wb_pts[-1][0]}, years)")
                if "debt_gdp" in failures:
                    failures.remove("debt_gdp")
        except Exception as exc:
            print(f"FAIL  debt_gdp (WB stale fallback) {exc}")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    try:
        with open("data-il.json") as f:
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

    # fx_to_usd: switched (Aug 2026) from CCUSMA02ILQ618N (OECD
    # quarterly) to World Bank PA.NUS.FCRF -- the OECD series was
    # confirmed discontinued (stopped updating Feb 2026, "Next Release
    # Date: Not Available"). No live Fed H.10-style daily series exists
    # for the shekel either (confirmed via search -- unlike the won/
    # yen/etc, no DEXISUS or equivalent has ever existed). PA.NUS.FCRF
    # is a genuine, live, ongoing World Bank indicator (IMF IFS-sourced,
    # "Official exchange rate, LCU per US$"), back to 1960 -- ANNUAL
    # resolution only, same tradeoff already accepted for Poland/Turkey/
    # Chile/Colombia/Argentina/Indonesia. Needs no FRED_API_KEY, so this
    # now runs unconditionally rather than behind the `if key:` gate the
    # old FRED-based fetch used.
    try:
        fx_pts = fetch_worldbank("PA.NUS.FCRF")
        if fx_pts:
            fx_period, fx_rate = fx_pts[-1]
            out["fx_to_usd"] = {"pair": "ILS/USD", "rate": fx_rate,
                                 "as_of": fx_period, "direction": "divide",
                                 "history": fx_pts}
            print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                  f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points, annual)")

            to_local = lambda v: v * fx_rate
            for tk in ("trade_balance", "exports", "imports"):
                if tk in out["series"]:
                    ser = out["series"][tk]
                    if ser["unit"].strip().startswith("$"):
                        ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                        ser["unit"] = ser["unit"].replace("$", "\u20aa", 1)
                        ser["label"] = ser["label"].replace(", $ ", ", \u20aa ") \
                                                    .replace(", $", ", \u20aa")
                        print(f"  ok  {tk:<16} converted {'$'}->{'\u20aa'} using {fx_rate}")
        else:
            print("note  fx_to_usd: no observations returned")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-il.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-il.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} -- the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
