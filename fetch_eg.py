"""Fetch Egypt's economic series and write data-eg.json.

Run:  python3 fetch_eg.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

PARTIAL COVERAGE, by decision (12 Oct 2026), the Vietnam pattern. Probe of
12 Oct 2026 (tools/probe_country.py EGY EG): every Central Bank of Egypt
page returns a firewall "Request Rejected" page; CAPMAS answers with a
JavaScript application shell only; OECD and BIS carry no Egypt policy rate
or CPI. Built v1.7.53 from fetch_vn.py. Run 1 not yet made: every source
below is unconfirmed until the first real run and audit.
Not an OECD member: no OECD calls.

- cpi / cpi_mom: IMF CPI dataflow, all items, the rates as published
  (EGY.CPI._T.YOY_PCH_PA_PT.M and .POP_PCH_PA_PT.M), to one decimal place.
- exports / imports / trade_balance: IMF international trade in goods (ITG),
  US dollars, converted to Egyptian pounds at the BIS monthly average rate
  (WS_XRU M.EG.EGP.A). The probe found ITG ending April (imports) and May
  2026 (exports), so trade is allowed TRADE_MAX_AGE days.
- gdp_level / gdp_real / gdp_growth: World Bank annual national accounts
  (NY.GDP.MKTP.CN, NY.GDP.MKTP.KN), pounds, scaled to million. Egypt's
  fiscal year runs July to June; the World Bank labels each year by the
  calendar year in which it ends.
- unemployment: World Bank SL.UEM.TOTL.ZS (ILO modelled estimate), annual.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, pounds per US$, annual average
  (fx_config.ANNUAL).
Not served: policy rate (the IMF's latest Central Bank of Egypt rate was
August 2025 at the probe, 14 months old, too stale to show as current, and
CBE's own site blocks automated requests), quarterly GDP, monthly labour
data, bond yield, business confidence.
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

ISO3 = "EGY"
OUT_FILE = "data-eg.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120
TRADE_MAX_AGE = 200     # probe, 12 Oct 2026: ITG imports to April 2026
# Run 1 (12 Oct 2026): the IMF's ITG figures for February 2016 have exports
# and imports the wrong way round: US$5.2bn exports and US$1.6bn imports,
# the only surplus month since 2008, against Egypt's usual pattern of about
# US$1.7bn exports and US$5.3bn imports either side of it. Swapped back here,
# named in the log; the audit checks it. Remove if the IMF corrects it.
SWAPPED_MONTHS = {"2016-02"}

IMF = "https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/"
CPI_YOY_URL = IMF + "CPI/~/EGY.CPI._T.YOY_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
CPI_MOM_URL = IMF + "CPI/~/EGY.CPI._T.POP_PCH_PA_PT.M?c[TIME_PERIOD]=ge:2000-M01"
ITG_URL = IMF + "ITG/~/EGY.*.*.M?c[TIME_PERIOD]=ge:2000-M01"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.EG.EGP.A?format=csv"
WB_URL = "https://api.worldbank.org/v2/country/EGY/indicator/{code}?format=json&per_page=200"

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


# ---------------------------------------------------------------- series
def unswap(rows: list) -> list:
    """Puts exports and imports back the right way round for SWAPPED_MONTHS.
    Applied only while the swap is still there (exports above imports)."""
    by = {}
    for r in rows:
        per = (r.get("TIME_PERIOD") or "").replace("-M", "-")
        if per in SWAPPED_MONTHS and r.get("UNIT") == "USD":
            by.setdefault(per, {})[r.get("INDICATOR")] = r
    for per, pair in by.items():
        x, m = pair.get("XG"), pair.get("MG")
        if x and m and float(x["OBS_VALUE"] or 0) > float(m["OBS_VALUE"] or 0):
            x["OBS_VALUE"], m["OBS_VALUE"] = m["OBS_VALUE"], x["OBS_VALUE"]
            print(f"  [imf] ITG EGY {per}: exports and imports swapped back (see SWAPPED_MONTHS)")
    return rows


def fetch_trade() -> dict:
    r = requests.get(BIS_FX_AVG_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_XRU M.EG.EGP.A status={r.status_code}")
    r.raise_for_status()
    rate = {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", row.get("TIME_PERIOD", ""))}
    return trade_from_usd(unswap(imf_csv(ITG_URL, "ITG EGY")), fill_single_gaps(rate), "Egyptian pounds")


def fill_single_gaps(rate: dict) -> dict:
    """BIS skips the odd month (run 1, 12 Oct 2026: no August 2025 rate,
    though July and September are there). A month missing on its own takes
    the mean of the months either side, and the log names it; a run of two
    or more missing months is left as a gap for the audit to catch."""
    out = dict(rate)
    keys = sorted(rate)
    for a, b in zip(keys, keys[1:]):
        mid = _back(b, 1)
        if mid != a and _back(mid, 1) == a:
            out[mid] = round((rate[a] + rate[b]) / 2, 2)
            print(f"  [bis] WS_XRU M.EG.EGP.A has no {mid}: using the mean of {a} and {b} ({out[mid]})")
    return out




def wb_scaled(code: str) -> list:
    return [[p, round(v / 1e6, 1)] for p, v in fetch_worldbank(code)]


def fetch_gdp_growth() -> list:
    return pct_change(fetch_worldbank("NY.GDP.MKTP.KN"), 1)


def imf_rate(url: str, tag: str) -> list:
    """An IMF series published as a rate (%), to one decimal place."""
    pts = [[p, round(v, 1)] for p, v in monthly(imf_csv(url, tag), {})]
    return require_current(pts, MONTHLY_MAX_AGE, f"IMF {tag}")


SERIES = [
    ("cpi", lambda: imf_rate(CPI_YOY_URL, "CPI EGY y/y"),
     "CPI, all items, change on same month a year earlier (IMF CPI, from CAPMAS)", "%", "months"),
    ("cpi_mom", lambda: imf_rate(CPI_MOM_URL, "CPI EGY m/m"),
     "CPI, all items, change on previous month, not seasonally adjusted (IMF CPI)", "%", "months"),
    ("trade", fetch_trade, {
        "exports": "Exports of goods, FOB, US$ converted to Egyptian pounds at the BIS monthly average rate (IMF international trade in goods)",
        "imports": "Imports of goods, CIF, US$ converted to Egyptian pounds at the BIS monthly average rate (IMF international trade in goods)",
        "trade_balance": "Trade balance, goods, exports less imports, Egyptian pounds (IMF ITG, converted at the BIS monthly average rate)",
    }, "EGPm", "months"),
    ("gdp_level", lambda: wb_scaled("NY.GDP.MKTP.CN"), "GDP, current prices, annual (World Bank)", "EGPm", "years"),
    ("gdp_real", lambda: wb_scaled("NY.GDP.MKTP.KN"), "Real GDP, constant prices, annual (World Bank)", "EGPm", "years"),
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
        out["fx_to_usd"] = {"pair": "EGP/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx,
                           # Dollarise leaves out pre-1991 years (fx_config.SERIES_START)
                           "floor": "1991"}
        print(f"  ok  fx_to_usd            {fx[-1][1]} pounds per US$ ({fx[-1][0]}, World Bank PA.NUS.FCRF annual average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
