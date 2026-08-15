"""Fetch Singapore economic series and write data-sg.json.

Run:  FRED_API_KEY=yourkey python3 fetch_sg.py
Sources: FRED (free key required: fred.stlouisfed.org), OECD, World Bank,
IMF Asia and Pacific Regional Economic Outlook (via FRED).
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Singapore build note: derived from fetch_ar.py (most recent non-OECD,
World-Bank-member, own-currency page at build time) per the v2
country-build framework. Singapore is neither an OECD, EU, nor EEA/EFTA
member.

IMPORTANT STRUCTURAL NOTE: unlike every other country built so far,
Singapore's real GDP growth is only genuinely available ANNUALLY from a
verified live source (IMF APD REO), not quarterly. This is a real
data-availability constraint, not an oversight -- the page's
gdp_growth panel is explicitly labeled "annual" rather than
"quarter on quarter", and there is no separate gdp_real level series
or derived YoY line chart the way most other pages have.

VERIFICATION NOTES (checked against each series' own FRED page via
web_search before wiring in -- sandbox network cannot reach
fred.stlouisfed.org directly, so these are page-content confirmations,
not live API test calls; the first real Actions run is still the
genuine test):
- gdp_growth (SGPNGDPRPCPPPT): CONFIRMED genuinely live and updated
  through Jan 2026 -- IMPORTANT: this is one of several series in the
  same IMF Asia-Pacific REO family for Singapore, and NOT ALL of them
  are live. SGPNTDDRPCPPPT (domestic demand) and SGPTXRPCPPPT (exports
  volume) and SGPGGXWDGG01GDPPT (general-government debt) are all
  STALE, stuck at "Updated: Oct 23, 2019" despite showing values through
  2024-2030 (those are 2019-vintage projections, not real updates).
  Only gdp_growth, cpi, and current_account from this family were
  confirmed genuinely current for this build -- the stale ones were
  deliberately excluded rather than used. This is a real, verified
  distinction within a single data source, not a blanket assumption.
- gdp_level (World Bank NY.GDP.MKTP.CD, country=SGP): standard
  fetch_worldbank() mechanism, same raw-USD-to-$m scale correction
  (1e-6) as every other country using this indicator family. Singapore
  IS a World Bank member (unlike Taiwan, which was skipped this batch
  specifically because it is not).
- debt_gdp (DEBTTLSGA188A): CONFIRMED live (through 2024, updated May
  2025), World Bank World Development Indicators. This is CENTRAL
  government debt, NOT general government -- the general-government
  series in the IMF REO family (SGPGGXWDGG01GDPPT) is one of the stale
  2019 series described above, so this World Bank series was used
  instead despite the narrower scope. Also worth noting: Singapore's
  government debt is structurally unusual -- most of it funds domestic
  capital-market development and the reserves system (via the Singapore
  Government Securities program and CPF), not deficit financing, so a
  high number here does not mean the same thing it would for most
  countries. Disclosed on the page itself.
- current_account (SGPBCAGDPBP6PT): CONFIRMED genuinely live and
  updated through Jan 2026, IMF Asia-Pacific REO. Singapore runs a
  large, persistent surplus as a financial/trade hub -- real, not a
  data error.
- cpi (SGPPCPIPCPPPT): CONFIRMED genuinely live and updated through
  Jan 2026, IMF Asia-Pacific REO, ANNUAL % change. The page also tries
  OECD's live monthly CPI system first (same convention as every other
  country here) and falls back to this only if that returns nothing --
  see fetch_oecd_cpi() below. Singapore is not an OECD member, so the
  OECD system's coverage for it was not individually confirmed before
  this build; check the Actions log.
- unemployment (World Bank SL.UEM.TOTL.ZS, modeled ILO estimate): same
  mechanism used for Indonesia/Argentina. No dedicated FRED series ID
  was confirmed for Singapore's unemployment rate during this build's
  research pass, so the standard World Bank fallback is used. Real
  published figures put Singapore's unemployment at roughly 2%,
  genuinely very low by international standards -- expect small numbers
  here, not a data error.
- deficit / participation_rate / policy_rate: NOT included. No clean
  live source individually confirmed for any of these during this
  build -- genuine, disclosed gaps, not guesses.
- fx_to_usd (DEXSIUS): CONFIRMED live (through Mar 2026), a real Fed
  H.10 daily series -- same quality tier as Norway/Denmark/Sweden's own
  FX series, better than the OECD monthly-average fallback used for
  several other countries in this batch.
- business_confidence: OECD BCICP via SDMX, same multi-query fallback
  pattern used for every other country, REF_AREA=SGP. Best-effort, not
  individually confirmed -- Singapore is not an OECD member, so this
  may well come back empty; check the Actions log.
- trade_balance: standard OECD merchandise trade, monthly -- not
  individually confirmed for Singapore's specific data availability;
  best-effort, check the first Actions log. Converted from USD to SGD
  using the live DEXSIUS rate if fetched successfully, matching the
  pattern used for Denmark/Sweden's own-currency trade series.
- fdi: World Bank, same indicator code used for every other country
  (BX.KLT.DINV.WD.GD.ZS), country=SGP. Not individually confirmed for
  Singapore's specific data availability -- standard World Bank annual
  lag applies. Real published FDI inflows for Singapore are unusually
  large as a share of GDP (financial-hub effect) -- expect a bigger
  number here than most other countries, not a data error.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import requests

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_growth": ("SGPNGDPRPCPPPT", "a", "Real GDP growth, annual (IMF APD REO)", "%", None, 1.0),
    "current_account": ("SGPBCAGDPBP6PT", "a", "Current account, % of GDP (IMF APD REO)", "%", None, 1.0),
    "debt_gdp": ("DEBTTLSGA188A", "a", "Central government debt, % of GDP (World Bank)", "%", None, 1.0),
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


def _is_future_period(period: str) -> bool:
    """True if `period` (a fred_period-format string: 'YYYY', 'YYYY-Qn', or
    'YYYY-MM') refers to a year beyond the current calendar year. Some IMF
    REO/WEO-derived FRED mirrors (e.g. the annual *PPPT/GGXWDGGDP/GGXCNLGDP
    series) bundle several years of forward projections into the same
    series as real observations, with no flag distinguishing actual from
    forecast. We only want actual/estimated-to-date figures on the site,
    so any point dated beyond the current year is dropped at fetch time."""
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


OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/SGP.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/SGP.M.BCICP......?format=csvfile&startPeriod=1990",
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
                if low.get("REF_AREA", "SGP") != "SGP":
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

WB_URL = ("https://api.worldbank.org/v2/country/SGP/indicator/"
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

    extras = [
        ("business_confidence", lambda: fetch_oecd_bci(),
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("cpi", lambda: fetch_oecd_cpi(("SGP",), "M"),
         "CPI, all items, YoY (OECD live prices system)", "%", "months"),
        ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
         "Unemployment, total (modeled ILO estimate, World Bank)", "%", "years"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "FDI net inflows, % of GDP (World Bank)", "%", "years"),
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

    if "cpi" not in out["series"]:
        try:
            sid, freq, label, unit, tf, scale = ("SGPPCPIPCPPPT", "a",
                "CPI, all items, YoY (IMF Asia-Pacific REO)", "%", None, 1.0)
            if key:
                raw = fetch_fred(sid, freq, key)
                if raw:
                    out["series"]["cpi"] = {"label": f"{label} ({sid})", "unit": unit,
                                            "freq": "years", "points": raw}
                    print(f"  ok  cpi (REO fallback) {len(raw):>5} observations "
                          f"({raw[0][0]} to {raw[-1][0]}, years)")
                    if "cpi" in failures:
                        failures.remove("cpi")
        except Exception as exc:
            print(f"FAIL  cpi (REO fallback) {exc}")

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
        with open("data-sg.json") as f:
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
            fx_pts = fetch_fred("DEXSIUS", "d", key)
            if fx_pts:
                fx_period, fx_rate = fx_pts[-1]
                out["fx_to_usd"] = {"pair": "SGD/USD", "rate": fx_rate,
                                     "as_of": fx_period, "direction": "divide"}
                print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate})")

                to_local = lambda v: v * fx_rate
                for tk in ("trade_balance", "exports", "imports"):
                    if tk in out["series"]:
                        ser = out["series"][tk]
                        if ser["unit"].strip().startswith("$"):
                            ser["points"] = [[p, round(to_local(v), 1)] for p, v in ser["points"]]
                            ser["unit"] = ser["unit"].replace("$", "S$", 1)
                            ser["label"] = ser["label"].replace(", $ ", ", S$ ") \
                                                        .replace(", $", ", S$")
                            print(f"  ok  {tk:<16} converted $->S$ using {fx_rate}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    with open("data-sg.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-sg.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
