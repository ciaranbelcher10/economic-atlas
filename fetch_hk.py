"""Fetch Hong Kong's economic series and write data-hk.json.

Run:  FRED_API_KEY=yourkey python3 fetch_hk.py
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sources, chosen from tools/probe_country.py (13 Oct 2026) and a direct
read of the Census and Statistics Department's web-table API. C&SD's API
answers from outside Hong Kong, so its own national accounts are used.
Built v1.7.56. Run 1 not yet made: every source below is unconfirmed until
the first real run and audit. Not an OECD member: no OECD calls.

- gdp_level / gdp_real: C&SD table 310-31001 (full_series=1), GDP at
  current market prices (sv CUR) and in chained (2024) dollars (sv CON),
  HK$ million, quarterly, not seasonally adjusted, from 1973.
- gdp_growth: the same table's seasonally adjusted change on the previous
  quarter (sv SA1), as published.
- gdp_growth_yoy: the same table's real GDP change on the same quarter a
  year earlier (sv CON, "Year-on-year % change"), as published.
- cpi / cpi_mom: IMF CPI dataflow, all items (C&SD's Composite CPI), the
  rates as published (HKG.CPI._T.YOY_PCH_PA_PT.M and .POP_PCH_PA_PT.M), to
  one decimal place.
- policy_rate: BIS central bank policy rates, M.HK, the HKMA's base rate,
  from October 1998 (the base rate's first full month), extended past BIS's
  last monthly value with BIS's daily series. Under the Linked Exchange
  Rate System the base rate follows the US federal funds rate.
- exports / imports / trade_balance: IMF international trade in goods
  (ITG), US dollars, converted to HK$ at the BIS monthly average rate
  (WS_XRU M.HK.HKD.A). Hong Kong's exports are mostly re-exports.
- unemployment: World Bank SL.UEM.TOTL.ZS (ILO modelled estimate), annual.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: FRED DEXHKUS (HK$ per US dollar, daily, reduced to month
  end), World Bank annual average only if FRED is unreachable. The HK
  dollar has been linked to the US dollar since 17 October 1983, within
  7.75 to 7.85 since May 2005, so Dollarise changes the level, not the shape.
Not served: monthly labour data (C&SD publishes it; the table is not yet
wired), bond yield, business confidence.
"""
from __future__ import annotations

import redact_stream  # noqa: F401  (v1.7.42: masks api_key= in all output)
import csv
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

import bis_daily
import imf_weo
import series_guard

ISO3 = "HKG"
OUT_FILE = "data-hk.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230
TRADE_MAX_AGE = 200          # probe, 13 Oct 2026: ITG to June 2026
BASE_RATE_START = "1998-10"  # the HKMA base rate was introduced in September 1998

IMF = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"
CPI_YOY_URL = IMF + "CPI/~/HKG.CPI._T.YOY_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
CPI_MOM_URL = IMF + "CPI/~/HKG.CPI._T.POP_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
ITG_URL = IMF + "ITG/~/HKG.*.*.M?c[TIME_PERIOD]=ge:1995-M01"
CSD_GDP_URL = "https://www.censtatd.gov.hk/api/get.php?id=310-31001&lang=en&full_series=1"
BIS_POLICY_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.HK?format=csv"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.HK.HKD.A?format=csv"
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1981-01-01")
WB_URL = "https://api.worldbank.org/v2/country/HKG/indicator/{code}?format=json&per_page=200"

# ---------------------------------------------------------------- helpers
def _period_end(per: str) -> datetime | None:
    m = re.fullmatch(r"(\d{4})-(\d{2})", per)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=timezone.utc)
    m = re.fullmatch(r"(\d{4})-Q([1-4])", per)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return datetime(y + (q == 4), (q * 3) % 12 + 1, 1, tzinfo=timezone.utc)
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
    if re.fullmatch(r"\d{4}-Q[1-4]", p):
        t = int(p[:4]) * 4 + int(p[6]) - 1 - n
        return f"{t // 4}-Q{t % 4 + 1}"
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
        out[key] = require_current(pts, TRADE_MAX_AGE, f"IMF {ind} (US$ to {cur})")
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


# ---------------------------------------------------------------- C&SD GDP
_CSD: list = []


def csd_gdp() -> list:
    if not _CSD:
        r = requests.get(CSD_GDP_URL, timeout=90, headers=UA)
        print(f"  [csd] 310-31001 status={r.status_code}")
        r.raise_for_status()
        rows = r.json().get("dataSet") or []
        if not rows:
            raise ValueError("C&SD 310-31001: empty dataSet")
        _CSD.extend(rows)
    return _CSD


def csd_period(per: str) -> str | None:
    """C&SD quarters are labelled by their last month: 202606 -> 2026-Q2."""
    m = re.fullmatch(r"(\d{4})(03|06|09|12)", per)
    return f"{m.group(1)}-Q{int(m.group(2)) // 3}" if m else None


def csd_series(sv: str, desc: str) -> list:
    """Quarterly rows of one series, matched on code AND unit description
    (each code carries both a level and a percentage change). Blank figures
    (not yet released) are skipped."""
    pts = {}
    for row in csd_gdp():
        if row.get("freq") != "Q" or row.get("sv") != sv or row.get("svDesc") != desc:
            continue
        per = csd_period(str(row.get("period", "")))
        try:
            v = float(row.get("figure"))
        except (TypeError, ValueError):
            continue
        if per:
            pts[per] = v
    if not pts:
        raise ValueError(f"C&SD 310-31001: no quarterly rows for {sv} / {desc}")
    return sorted([[p, v] for p, v in pts.items()])


def fetch_gdp_level() -> list:
    pts = csd_series("CUR", "HK$ million")
    bad = [p for p in pts if p[0] >= "1990" and not 50_000 < p[1] < 2_000_000]
    if bad:
        raise ValueError(f"C&SD nominal GDP: implausible quarter {bad[0]} (HK$ million)")
    return require_current(pts, QUARTERLY_MAX_AGE, "C&SD nominal GDP")


def fetch_gdp_real() -> list:
    pts = csd_series("CON", "HK$ million")
    bad = [p for p in pts if p[0] >= "1990" and not 100_000 < p[1] < 2_000_000]
    if bad:
        raise ValueError(f"C&SD real GDP: implausible quarter {bad[0]} (HK$ million, chained)")
    return require_current(pts, QUARTERLY_MAX_AGE, "C&SD real GDP")


def fetch_gdp_rate(sv: str, desc: str, what: str) -> list:
    pts = [[p, round(v, 1)] for p, v in csd_series(sv, desc)]
    bad = [p for p in pts if not -25 < p[1] < 25]
    if bad:
        raise ValueError(f"C&SD {what}: implausible quarter {bad[0]}")
    return require_current(pts, QUARTERLY_MAX_AGE, f"C&SD {what}")


# ---------------------------------------------------------------- others
def fetch_policy_rate() -> list:
    r = requests.get(BIS_POLICY_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.HK status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= BASE_RATE_START]
    pts = bis_daily.extend(pts, "HK", "base rate")
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS base rate")


def fill_single_gaps(rate: dict) -> dict:
    """A month BIS skips on its own takes the mean of the months either
    side, named in the log; a run of two or more is left for the audit."""
    out = dict(rate)
    keys = sorted(rate)
    for a, b in zip(keys, keys[1:]):
        mid = _back(b, 1)
        if mid != a and _back(mid, 1) == a:
            out[mid] = round((rate[a] + rate[b]) / 2, 4)
            print(f"  [bis] WS_XRU M.HK.HKD.A has no {mid}: using the mean of {a} and {b} ({out[mid]})")
    return out


def fetch_trade() -> dict:
    r = requests.get(BIS_FX_AVG_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_XRU M.HK.HKD.A status={r.status_code}")
    r.raise_for_status()
    rate = {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", row.get("TIME_PERIOD", ""))}
    bad = [k for k, v in rate.items() if k >= "1984" and not 7.0 < v < 8.5]
    if bad:
        raise ValueError(f"BIS HKD rate: implausible value {bad[0]} {rate[bad[0]]} (the link is 7.75 to 7.85)")
    return trade_from_usd(imf_csv(ITG_URL, "ITG HKG"), fill_single_gaps(rate), "HK dollars")


def fetch_fred_month_end(sid: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60, headers=UA)
    r.raise_for_status()
    month_end = {}
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        month_end[o["date"][:7]] = float(o["value"])
    return sorted([[p, v] for p, v in month_end.items()])


def imf_rate(url: str, tag: str) -> list:
    """An IMF series published as a rate (%), to one decimal place."""
    pts = [[p, round(v, 1)] for p, v in monthly(imf_csv(url, tag), {})]
    return require_current(pts, MONTHLY_MAX_AGE, f"IMF {tag}")


SERIES = [
    ("gdp_level", fetch_gdp_level,
     "GDP, current market prices, not seasonally adjusted (C&SD, table 310-31001)", "HKDm", "quarters"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, chained (2024) dollars, not seasonally adjusted (C&SD, table 310-31001)", "HKDm", "quarters"),
    ("gdp_growth", lambda: fetch_gdp_rate("SA1", "Quarter-to-quarter % change", "GDP q/q"),
     "Real GDP growth, change on previous quarter, seasonally adjusted (C&SD, table 310-31001)", "%", "quarters"),
    ("gdp_growth_yoy", lambda: fetch_gdp_rate("CON", "Year-on-year % change", "GDP y/y"),
     "Real GDP growth, change on same quarter a year earlier (C&SD, table 310-31001)", "%", "quarters"),
    ("cpi", lambda: imf_rate(CPI_YOY_URL, "CPI HKG y/y"),
     "Composite CPI, all items, change on same month a year earlier (IMF CPI, from C&SD)", "%", "months"),
    ("cpi_mom", lambda: imf_rate(CPI_MOM_URL, "CPI HKG m/m"),
     "Composite CPI, all items, change on previous month, not seasonally adjusted (IMF CPI)", "%", "months"),
    ("policy_rate", fetch_policy_rate,
     "HKMA base rate (BIS central bank policy rates, M.HK, from October 1998)", "%", "months"),
    ("trade", fetch_trade, {
        "exports": "Exports of goods, including re-exports, FOB, US$ converted to HK$ at the BIS monthly average rate (IMF international trade in goods)",
        "imports": "Imports of goods, CIF, US$ converted to HK$ at the BIS monthly average rate (IMF international trade in goods)",
        "trade_balance": "Trade balance, goods, exports less imports, HK$ (IMF ITG, converted at the BIS monthly average rate)",
    }, "HKDm", "months"),
    ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
     "Unemployment rate, ILO modelled estimate, annual (World Bank)", "%", "years"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT), "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT), "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"), "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]


def extra(out: dict, prev_full: dict) -> None:
    key = os.environ.get("FRED_API_KEY")
    try:
        fx = fetch_fred_month_end("DEXHKUS", key) if key else []
        src = "FRED DEXHKUS"
        if not fx:
            fx, src = fetch_worldbank("PA.NUS.FCRF"), "World Bank annual average"
        bad = [p for p in fx if p[0] >= "1984" and not 7.0 < p[1] < 8.5]
        if bad:
            raise ValueError(f"{src}: implausible rate {bad[0]} (the link is 7.75 to 7.85)")
        out["fx_to_usd"] = {"pair": "HKD/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} HK$ per US$ ({fx[-1][0]}, {src}), history from {fx[0][0]}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
