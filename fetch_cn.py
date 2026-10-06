"""Fetch China's economic series and write data-cn.json.

Run:  FRED_API_KEY=yourkey python3 fetch_cn.py
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sources, each confirmed by tools/probe_cn.py (Oct 2026) before wiring in:
- gdp_level: OECD quarterly national accounts (DF_QNA, table T0101),
  GDP at current prices, yuan millions, not seasonally adjusted. A
  quarterly level: the page rolls four quarters into a year, as for India
  and South Korea. Unit CNYm (ISO code, so it is never confused with the
  Japanese yen sign).
- gdp_growth: the same dataflow, real GDP change on the previous quarter,
  seasonally adjusted (TRANSFORMATION G1), from 2011.
- gdp_growth_yoy: real GDP change on the same quarter a year earlier
  (TRANSFORMATION GY), the figure China's statistics bureau headlines.
- gdp_real: World Bank, GDP in constant yuan, annual. The OECD's quarterly
  real series is in previous-year prices, which does not chain into a level.
- cpi: OECD prices database, all-items CPI, 12-month rate, national
  methodology. COICOP 2018 first (none for China yet), then COICOP 1999.
- cpi_mom: derived from the IMF's all-items CPI index (the same function
  Morocco uses), because the OECD carries no China index.
- policy_rate: BIS central bank policy rates, China. For China the BIS
  series is the one-year loan prime rate, and it is labelled as that: the
  PBoC's main operating rate since 2024 is the seven-day reverse repo.
- bond_yield_10y: OECD long-term interest rate (IRLT), monthly.
- exports / imports: IMF international trade in goods, US dollars, monthly;
  exports valued FOB, imports CIF, as China's customs reports them.
  trade_balance is exports minus imports, only for months with both. All
  three are converted to yuan at each month's own exchange rate.
- business_confidence: OECD BCICP.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- unemployment: World Bank, ILO modelled estimate, annual. The statistics
  bureau's monthly surveyed urban rate cannot be fetched from outside
  China (every request returns 403), so the page carries the annual
  estimate and says which one it is.
- fx_to_usd: FRED DEXCHUS (yuan per US dollar, daily, reduced to month
  end), World Bank annual average only if FRED is unreachable.

OECD requests run in turn group C (oecd_turn.py); off-turn the previous
values are carried over by series_guard, as for every other country.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

import imf_weo
import oecd_turn
import series_guard
from fetch_bonds_daily import fetch_oecd_irlt
from fetch_ma import fetch_imf_cpi_mom

ISO3 = "CHN"
OUT_FILE = "data-cn.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1981-01-01")
WB_URL = "https://api.worldbank.org/v2/country/CHN/indicator/{code}?format=json&per_page=200"
OECD = "https://sdmx.oecd.org/public/rest/data/"
QNA_URL = OECD + "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/Q..CHN..........?startPeriod=1992&format=csvfile"
BCI_URL = OECD + "OECD.SDD.STES,DSD_STES@DF_CLI/CHN.M.BCICP......?format=csvfile&startPeriod=1990"
CPI_URLS = (
    ("C2018", OECD + "OECD.SDD.TPS,DSD_PRICES_COICOP2018@DF_PRICES_C2018_ALL,1.0/CHN.M..CPI.PA._T..GY?format=csvfile&startPeriod=1990"),
    ("C1999", OECD + "OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,1.0/CHN.M..CPI.PA._T..GY?format=csvfile&startPeriod=1990"),
)
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.CN?format=csv"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "CHN.*.*.M?c[TIME_PERIOD]=ge:1990-M01")

MONTHLY_MAX_AGE = 120     # days past the end of the last month
QUARTERLY_MAX_AGE = 220


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
    """Reject a series whose last period is too old to show as current."""
    if not points:
        raise ValueError(f"{what}: no observations")
    end = _period_end(points[-1][0])
    if end and (datetime.now(timezone.utc) - end).days > max_days:
        raise ValueError(f"{what}: series ends {points[-1][0]}, too old to show as current")
    return points


def oecd_rows(url: str) -> list:
    r = requests.get(url, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [oecd] {url.split('/data/')[1][:60]} status={r.status_code}")
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def pick(rows: list, **want) -> list:
    """Points from rows whose columns match every key=value in `want`."""
    out = {}
    for row in rows:
        if all((row.get(k) or "") == v for k, v in want.items()):
            p, v = (row.get("TIME_PERIOD") or "").strip(), (row.get("OBS_VALUE") or "").strip()
            if p and v:
                try:
                    out[p] = float(v)
                except ValueError:
                    pass
    return sorted([[p, v] for p, v in out.items()])


# ---------------------------------------------------------------- sources
_QNA: list | None = None


def qna() -> list:
    global _QNA
    if _QNA is None:
        oecd_turn.check()
        _QNA = oecd_rows(QNA_URL)
    return _QNA


def fetch_gdp_level() -> list:
    pts = pick(qna(), TRANSACTION="B1GQ", UNIT_MEASURE="XDC", PRICE_BASE="V", ADJUSTMENT="N",
               TRANSFORMATION="N", TABLE_IDENTIFIER="T0101")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA GDP level")


def fetch_gdp_growth(transformation: str) -> list:
    pts = pick(qna(), TRANSACTION="B1GQ", UNIT_MEASURE="PC", PRICE_BASE="L", ADJUSTMENT="Y",
               TRANSFORMATION=transformation)
    pts = [[p, round(v, 2)] for p, v in pts]
    return require_current(pts, QUARTERLY_MAX_AGE, f"OECD QNA GDP growth {transformation}")


def fetch_cpi() -> list:
    oecd_turn.check()
    for tag, url in CPI_URLS:
        try:
            rows = oecd_rows(url)
        except Exception as exc:
            print(f"  [oecd-cpi] {tag} {exc}")
            continue
        pts = pick(rows, METHODOLOGY="N", ADJUSTMENT="N", TRANSFORMATION="GY")
        try:
            return require_current(pts, MONTHLY_MAX_AGE, f"OECD CPI {tag}")
        except ValueError as exc:
            print(f"  [oecd-cpi] {exc}")
    raise ValueError("no current OECD CPI series for China")


def fetch_bci() -> list:
    oecd_turn.check()
    pts = pick(oecd_rows(BCI_URL), MEASURE="BCICP", FREQ="M")
    return require_current(pts, MONTHLY_MAX_AGE, "OECD BCI")


def fetch_bond() -> list:
    oecd_turn.check()
    freq, pts = fetch_oecd_irlt(ISO3)
    if freq != "months":
        raise ValueError("OECD IRLT for China is no longer monthly")
    return pts


def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.CN status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def fetch_trade() -> dict:
    """Exports and imports in US$ millions, plus the balance for months
    with both. Raw values from the IMF are in US dollars."""
    r = requests.get(ITG_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-itg] CHN status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = {}
    for key, ind, val in (("exports", "XG", "FOB"), ("imports", "MG", "CIF")):
        pts = {}
        for row in rows:
            if (row.get("INDICATOR"), row.get("VALUATION"), row.get("UNIT")) != (ind, val, "USD"):
                continue
            if row.get("TRANSFORMATION"):
                continue
            per = (row.get("TIME_PERIOD") or "").replace("-M", "-")
            try:
                v = float(row.get("OBS_VALUE") or "")
            except ValueError:
                continue
            if re.fullmatch(r"\d{4}-\d{2}", per):
                pts[per] = round(v / 1e6, 1)
        out[key] = require_current(sorted([[p, v] for p, v in pts.items()]), MONTHLY_MAX_AGE, f"IMF {ind}")
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    return out


def fetch_worldbank(code: str, scale: float = 1.0) -> list:
    r = requests.get(WB_URL.format(code=code), timeout=60, headers=UA)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"World Bank {code}: empty response")
    pts = sorted([[str(d["date"]), round(float(d["value"]) * scale, 4)] for d in payload[1]
                  if d.get("value") is not None])
    return require_current(pts, 900, f"World Bank {code}")


def fetch_fred(sid: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60, headers=UA)
    r.raise_for_status()
    month_end = {}
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        month_end[o["date"][:7]] = float(o["value"])   # dates ascend: last value of each month wins
    return sorted([[p, v] for p, v in month_end.items()])


def rate_for(fx_hist: list, period: str, fallback: float) -> float:
    """Yuan per dollar in effect for `period` (month, quarter or year)."""
    if re.fullmatch(r"\d{4}-\d{2}", period):
        k = period
    elif "Q" in period:
        y, q = period.split("-Q")
        k = f"{y}-{int(q) * 3:02d}"
    else:
        k = f"{period}-12"
    best = None
    for p, v in fx_hist:
        if p <= k:
            best = v
        else:
            break
    return best if best is not None else (fx_hist[0][1] if fx_hist else fallback)


# ---------------------------------------------------------------- main
SERIES = [
    # key, fetch, label, unit, freq
    ("gdp_level", fetch_gdp_level,
     "GDP, current prices, not seasonally adjusted (OECD quarterly national accounts, B1GQ)", "CNYm", "quarters"),
    ("gdp_growth", lambda: fetch_gdp_growth("G1"),
     "Real GDP growth, change on previous quarter, seasonally adjusted (OECD quarterly national accounts, B1GQ)", "%", "quarters"),
    ("gdp_growth_yoy", lambda: fetch_gdp_growth("GY"),
     "Real GDP growth, change on same quarter a year earlier (OECD quarterly national accounts, B1GQ)", "%", "quarters"),
    ("gdp_real", lambda: fetch_worldbank("NY.GDP.MKTP.KN", 1e-6),
     "Real GDP, constant prices (World Bank NY.GDP.MKTP.KN)", "CNYm", "years"),
    ("cpi", fetch_cpi, "CPI, all items, YoY (OECD prices database)", "%", "months"),
    ("cpi_mom", lambda: fetch_imf_cpi_mom(ISO3), "CPI, all items, MoM (IMF CPI index)", "%", "months"),
    ("policy_rate", fetch_policy_rate, "One-year loan prime rate (BIS central bank policy rates, M.CN)", "%", "months"),
    ("bond_yield_10y", fetch_bond, "10-year government bond yield (OECD IRLT)", "%", "months"),
    ("business_confidence", fetch_bci, "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
     "FDI net inflows, % of GDP (World Bank)", "%", "years"),
    ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
     "Unemployment rate, ILO modelled estimate, % of labour force (World Bank SL.UEM.TOTL.ZS)", "%", "years"),
]
TRADE_LABELS = {
    "exports": "Exports of goods, FOB (IMF international trade in goods, XG)",
    "imports": "Imports of goods, CIF (IMF international trade in goods, MG)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF (IMF international trade in goods)",
}


def main() -> int:
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "sample": False, "series": {}}
    failures = []

    for key, fn, label, unit, freq in SERIES:
        try:
            pts = fn()
            if not pts:
                raise ValueError("no usable response")
            out["series"][key] = {"label": label, "unit": unit, "freq": freq, "points": pts}
            print(f"  ok  {key:<20} {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, {freq})")
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<20} {exc}")
        time.sleep(0.4)

    try:
        for k, pts in fetch_trade().items():
            out["series"][k] = {"label": TRADE_LABELS[k], "unit": "$m", "freq": "months", "points": pts}
            print(f"  ok  {k:<20} {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, months)")
    except Exception as exc:
        failures += ["exports", "imports", "trade_balance"]
        print(f"FAIL  trade                {exc}")

    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_series = prev_full.get("series", {})
    fresh = set(out["series"])

    # Exchange rate, then convert freshly fetched dollar trade into yuan at
    # each month's own rate. A carried-over series is already in yuan.
    fx_ok = False
    key = os.environ.get("FRED_API_KEY")
    try:
        fx = fetch_fred("DEXCHUS", key) if key else []
        if fx:
            out["fx_to_usd"] = {"pair": "CNY/USD", "rate": fx[-1][1], "as_of": fx[-1][0],
                                "direction": "divide", "history": fx}
            print(f"  ok  fx_to_usd            {fx[-1][1]} ({fx[-1][0]}), history from {fx[0][0]}")
        else:
            wb = fetch_worldbank("PA.NUS.FCRF")
            fx = wb
            out["fx_to_usd"] = {"pair": "CNY/USD", "rate": wb[-1][1], "as_of": wb[-1][0],
                                "direction": "divide", "history": wb}
            print(f"  ok  fx_to_usd            {wb[-1][1]} ({wb[-1][0]}, World Bank annual average)")
        fx_ok = True
        for tk in ("exports", "imports", "trade_balance"):
            ser = out["series"].get(tk)
            if tk in fresh and ser and ser["unit"] == "$m":
                ser["points"] = [[p, round(v * rate_for(fx, p, fx[-1][1]), 1)] for p, v in ser["points"]]
                ser["unit"] = "CNYm"
                ser["label"] += ", converted to yuan at each month's exchange rate"
                print(f"  ok  {tk:<20} converted $ -> CNY at each month's rate")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")

    if not fx_ok:
        for tk in ("exports", "imports", "trade_balance"):
            if tk in fresh:
                del out["series"][tk]
                print(f"FAIL  {tk:<20} no exchange rate this run to convert it; left out")

    series_guard.apply_guard(out["series"], prev_series, allow_shrink=ALLOW_SHRINK)
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")
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


if __name__ == "__main__":
    sys.exit(main())
