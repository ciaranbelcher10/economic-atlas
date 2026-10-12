"""Fetch Nigeria's economic series and write data-ng.json.

Run:  python3 fetch_ng.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

PARTIAL COVERAGE, by decision (12 Oct 2026), the Vietnam pattern. Probe of
12 Oct 2026 (tools/probe_country.py NGA NG): the National Bureau of
Statistics and the Central Bank of Nigeria answer, but only with
JavaScript page shells, so nothing is machine-readable; OECD and BIS carry
no Nigeria series; the IMF has no trade-in-goods (ITG) series for Nigeria.
Built v1.7.53 from fetch_vn.py. Run 1 not yet made: every source below is
unconfirmed until the first real run and audit.
Not an OECD member: no OECD calls.

- cpi / cpi_mom: IMF CPI dataflow, all items, the rates as published
  (NGA.CPI._T.YOY_PCH_PA_PT.M and .POP_PCH_PA_PT.M), to one decimal place.
  NBS rebased the CPI in January 2025 (2024=100); the IMF series is the
  rebased one, so the audit checks the join for a break.
- policy_rate: IMF monetary and financial statistics, interest rates,
  MFS166 (the monetary policy-related rate: the CBN's Monetary Policy Rate).
  The IMF publishes it some months after the CBN decides, so it is allowed
  POLICY_MAX_AGE days rather than the usual monthly bar, and the tile shows
  its month.
- gdp_level / gdp_real / gdp_growth: World Bank annual national accounts
  (NY.GDP.MKTP.CN, NY.GDP.MKTP.KN), naira, scaled to million; growth is the
  change in real GDP on the year before.
- unemployment: World Bank SL.UEM.TOTL.ZS (ILO modelled estimate), annual.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, naira per US$, annual average
  (fx_config.ANNUAL).
Not served: goods trade, quarterly GDP, monthly labour data, bond yield,
business confidence (no free machine-readable source).
"""
from __future__ import annotations

import redact_stream  # noqa: F401  (v1.7.42: masks api_key= in all output)
import csv
import io
import json
import re
import sys
from datetime import datetime, timezone

import requests

import imf_weo
import series_guard

ISO3 = "NGA"
OUT_FILE = "data-ng.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120
POLICY_MAX_AGE = 200    # probe, 12 Oct 2026: the IMF's latest month was April 2026

IMF = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"
CPI_YOY_URL = IMF + "CPI/~/NGA.CPI._T.YOY_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
CPI_MOM_URL = IMF + "CPI/~/NGA.CPI._T.POP_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
POLICY_URL = IMF + "MFS_IR/~/NGA.MFS166_RT_PT_A_PT.M?c[TIME_PERIOD]=ge:2000-M01"
WB_URL = "https://api.worldbank.org/v2/country/NGA/indicator/{code}?format=json&per_page=200"

# ---------------------------------------------------------------- helpers
def _period_end(per: str) -> datetime | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", per)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=timezone.utc)
    if re.fullmatch(r"\d{4}", per):
        return datetime(int(per) + 1, 1, 1, tzinfo=timezone.utc)
    return None


def require_current(points: list, max_days: int, what: str) -> list:
    if not points:
        raise ValueError(f"{what}: no observations")
    end = _period_end(points[-1][0])
    if end and (datetime.now(timezone.utc) - end).days > max_days:
        raise ValueError(f"{what}: series ends {points[-1][0]}, too old to show as current")
    return points


def _back(p: str, n: int) -> str | None:
    if re.fullmatch(r"\d{4}-\d{2}", p):
        t = int(p[:4]) * 12 + int(p[5:]) - 1 - n
        return f"{t // 12}-{t % 12 + 1:02d}"
    if re.fullmatch(r"\d{4}", p):
        return str(int(p) - n)
    return None


def pct_change(points: list, lag: int, dp: int = 1) -> list:
    by = dict(points)
    out = []
    for p, v in points:
        back = _back(p, lag)
        if back in by and by[back]:
            out.append([p, round((v / by[back] - 1) * 100, dp)])
    return out


def imf_csv(url: str, tag: str) -> list:
    r = requests.get(url, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf] {tag} status={r.status_code}")
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def monthly(rows: list, match: dict) -> list:
    pts = {}
    for row in rows:
        if any(row.get(k) != v for k, v in match.items()):
            continue
        per = (row.get("TIME_PERIOD") or "").replace("-M", "-")
        try:
            v = float(row.get("OBS_VALUE") or "")
        except ValueError:
            continue
        if re.fullmatch(r"\d{4}-\d{2}", per):
            pts[per] = v
    return sorted([[p, v] for p, v in pts.items()])


def trade_from_usd(rows: list, rate: dict, cur: str) -> dict:
    """IMF ITG US$ flows converted at the month's rate (local per US$).
    All three series end at the last month with both flows and a rate."""
    out = {}
    for key, ind, val in (("exports", "XG", "FOB"), ("imports", "MG", "CIF")):
        usd = monthly(rows, {"INDICATOR": ind, "VALUATION": val, "UNIT": "USD"})
        if not usd:
            have = sorted({(r.get("INDICATOR"), r.get("VALUATION"), r.get("UNIT")) for r in rows})[:12]
            raise ValueError(f"IMF ITG {ind}/{val}/USD: no rows; available {have}")
        pts = [[p, round(v / 1e6 * rate[p], 1)] for p, v in usd if p in rate]
        out[key] = require_current(pts, MONTHLY_MAX_AGE, f"IMF {ind} (US$ to {cur})")
    common = set(dict(out["exports"])) & set(dict(out["imports"]))
    out = {k: [p for p in v if p[0] in common] for k, v in out.items()}
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    if not out["trade_balance"]:
        raise ValueError("IMF trade: no month with both exports and imports")
    return out


def fetch_worldbank(code: str, max_days: int = 900) -> list:
    r = requests.get(WB_URL.format(code=code), timeout=60, headers=UA)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"World Bank {code}: empty response")
    pts = sorted([[str(d["date"]), round(float(d["value"]), 4)] for d in payload[1]
                  if d.get("value") is not None])
    return require_current(pts, max_days, f"World Bank {code}")


def put(out, key, pts, label, unit, freq):
    out["series"][key] = {"label": label, "unit": unit, "freq": freq, "points": pts}
    print(f"  ok  {key:<20} {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, {freq})")


def write(out: dict, prev_full: dict, failures: list) -> int:
    series_guard.apply_guard(out["series"], prev_full.get("series", {}), allow_shrink=ALLOW_SHRINK)
    if not out["series"]:
        print("\nNothing fetched.")
        return 1
    prev_meta = prev_full.get("new_points_meta") or {}
    new_meta = {}
    for k, v in out["series"].items():
        period = v["points"][-1][0]
        prior = prev_meta.get(k)
        same = prior and prior.get("period") == period
        new_meta[k] = {"period": period, "first_seen": prior["first_seen"] if same else out["updated"]}
    out["new_points_meta"] = new_meta
    out["new_points"] = {k: m["period"] for k, m in new_meta.items() if m["first_seen"] == out["updated"]}
    with open(OUT_FILE, "w") as f:
        json.dump(out, f)
    print(f"\nWrote {OUT_FILE} with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} (carried over where a previous run had them).")
    return 0


def run(series: list, extra) -> int:
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sample": False, "series": {}}
    failures = []
    for key, fn, label, unit, freq in series:
        try:
            res = fn()
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<20} {exc}")
            continue
        if isinstance(res, dict):
            for k, pts in res.items():
                put(out, k, pts, label[k], unit, freq)
        elif res:
            put(out, key, res, label, unit, freq)
    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    extra(out, prev_full)
    return write(out, prev_full, failures)


# ---------------------------------------------------------------- series


def wb_scaled(code: str) -> list:
    return [[p, round(v / 1e6, 1)] for p, v in fetch_worldbank(code)]


def fetch_gdp_growth() -> list:
    return pct_change(fetch_worldbank("NY.GDP.MKTP.KN"), 1)


def imf_rate(url: str, tag: str) -> list:
    """An IMF series published as a rate (%), to one decimal place."""
    pts = [[p, round(v, 1)] for p, v in monthly(imf_csv(url, tag), {})]
    return require_current(pts, MONTHLY_MAX_AGE, f"IMF {tag}")


def fetch_policy_rate() -> list:
    pts = [[p, round(v, 2)] for p, v in monthly(imf_csv(POLICY_URL, "MFS_IR NGA MFS166"), {})]
    bad = [p for p in pts if not 0 < p[1] < 60]
    if bad:
        raise ValueError(f"IMF policy rate: implausible value {bad[0]}")
    return require_current(pts, POLICY_MAX_AGE, "IMF MFS166 policy rate")


SERIES = [
    ("cpi", lambda: imf_rate(CPI_YOY_URL, "CPI NGA y/y"),
     "CPI, all items, change on same month a year earlier (IMF CPI, from Nigeria's National Bureau of Statistics)", "%", "months"),
    ("cpi_mom", lambda: imf_rate(CPI_MOM_URL, "CPI NGA m/m"),
     "CPI, all items, change on previous month, not seasonally adjusted (IMF CPI)", "%", "months"),
    ("policy_rate", fetch_policy_rate, "Central Bank of Nigeria Monetary Policy Rate, monthly (IMF monetary and financial statistics)", "%", "months"),
    ("gdp_level", lambda: wb_scaled("NY.GDP.MKTP.CN"), "GDP, current prices, annual (World Bank)", "NGNm", "years"),
    ("gdp_real", lambda: wb_scaled("NY.GDP.MKTP.KN"), "Real GDP, constant prices, annual (World Bank)", "NGNm", "years"),
    ("gdp_growth", fetch_gdp_growth, "Real GDP growth, change on previous year (World Bank)", "%", "years"),
    ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
     "Unemployment rate, ILO modelled estimate, annual (World Bank)", "%", "years"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT), "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT), "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"), "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]


def extra(out: dict, prev_full: dict) -> None:
    try:
        fx = fetch_worldbank("PA.NUS.FCRF")
        out["fx_to_usd"] = {"pair": "NGN/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx,
                           # Dollarise leaves out pre-1999 years (fx_config.SERIES_START)
                           "floor": "1999"}
        print(f"  ok  fx_to_usd            {fx[-1][1]} naira per US$ ({fx[-1][0]}, World Bank PA.NUS.FCRF annual average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
