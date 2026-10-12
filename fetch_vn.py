"""Fetch Vietnam's economic series and write data-vn.json.

Run:  python3 fetch_vn.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

PARTIAL COVERAGE, by decision (12 Oct 2026). Vietnam does not meet the
site's usual bar (quarterly GDP, current monthly CPI, a policy rate): the
statistics office (now NSO, formerly GSO) and the State Bank publish HTML
only, with no API, and BIS has no Vietnam policy rate. The page shows what
international sources carry and says plainly what is missing.
Built v1.7.50 from fetch_ph.py. Run 1 not yet made: every source below is
unconfirmed until the first real run and audit.
Not an OECD member: no OECD calls.

- cpi / cpi_mom: IMF CPI dataflow, all items, index (VNM.CPI._T.IX.M);
  change on twelve months and on one month, to one decimal place.
- exports / imports / trade_balance: IMF international trade in goods (ITG),
  US dollars, converted to dong at the BIS monthly average rate
  (WS_XRU M.VN.VND.A). A single month BIS does not carry (August 2025 in
  run 1) takes the mean of the BIS rates either side; see fill_single_gaps.
- gdp_level / gdp_real / gdp_growth: World Bank annual national accounts
  (NY.GDP.MKTP.CN, NY.GDP.MKTP.KN), dong, scaled to million; growth is the
  change in real GDP on the year before.
- unemployment: World Bank SL.UEM.TOTL.ZS (ILO modelled estimate), annual.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, dong per US$, annual average
  (fx_config.ANNUAL).
Not served: quarterly GDP, policy rate, monthly labour data, bond yield,
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

ISO3 = "VNM"
OUT_FILE = "data-vn.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120

CPI_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/"
           "VNM.CPI._T.IX.M?c[TIME_PERIOD]=ge:2005-M01")
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "VNM.*.*.M?c[TIME_PERIOD]=ge:2000-M01")
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.VN.VND.A?format=csv"
WB_URL = "https://api.worldbank.org/v2/country/VNM/indicator/{code}?format=json&per_page=200"

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
_CPI: list = []


def cpi_index() -> list:
    if not _CPI:
        ix = monthly(imf_csv(CPI_URL, "CPI VNM"), {})
        _CPI.extend(require_current(ix, MONTHLY_MAX_AGE, "IMF CPI index VNM"))
    return _CPI


def fetch_cpi() -> list:
    return require_current(pct_change(cpi_index(), 12), MONTHLY_MAX_AGE, "IMF CPI y/y")


def fetch_cpi_mom() -> list:
    return require_current(pct_change(cpi_index(), 1), MONTHLY_MAX_AGE, "IMF CPI m/m")


def fetch_trade() -> dict:
    r = requests.get(BIS_FX_AVG_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_XRU M.VN.VND.A status={r.status_code}")
    r.raise_for_status()
    rate = {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", row.get("TIME_PERIOD", ""))}
    return trade_from_usd(imf_csv(ITG_URL, "ITG VNM"), fill_single_gaps(rate), "dong")


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
            print(f"  [bis] WS_XRU M.VN.VND.A has no {mid}: using the mean of {a} and {b} ({out[mid]})")
    return out


def wb_scaled(code: str) -> list:
    return [[p, round(v / 1e6, 1)] for p, v in fetch_worldbank(code)]


def fetch_gdp_growth() -> list:
    return pct_change(fetch_worldbank("NY.GDP.MKTP.KN"), 1)


SERIES = [
    ("cpi", fetch_cpi, "CPI, all items, change on same month a year earlier (IMF CPI, from Vietnam's statistics office)", "%", "months"),
    ("cpi_mom", fetch_cpi_mom, "CPI, all items, change on previous month, not seasonally adjusted (IMF CPI)", "%", "months"),
    ("trade", fetch_trade, {
        "exports": "Exports of goods, FOB, US$ converted to dong at the BIS monthly average rate (IMF international trade in goods)",
        "imports": "Imports of goods, CIF, US$ converted to dong at the BIS monthly average rate (IMF international trade in goods)",
        "trade_balance": "Trade balance, goods, exports less imports, dong (IMF ITG, converted at the BIS monthly average rate)",
    }, "VNDm", "months"),
    ("gdp_level", lambda: wb_scaled("NY.GDP.MKTP.CN"), "GDP, current prices, annual (World Bank)", "VNDm", "years"),
    ("gdp_real", lambda: wb_scaled("NY.GDP.MKTP.KN"), "Real GDP, constant prices, annual (World Bank)", "VNDm", "years"),
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
        out["fx_to_usd"] = {"pair": "VND/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} dong per US$ ({fx[-1][0]}, World Bank PA.NUS.FCRF annual average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
