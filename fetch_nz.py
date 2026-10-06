"""Fetch New Zealand's economic series and write data-nz.json.

Run:  FRED_API_KEY=yourkey python3 fetch_nz.py
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sources, chosen from tools/probe_country.py (6 Oct 2026). New Zealand is an
OECD member, so the OECD republishes Stats NZ's own figures; Stats NZ's data
API needs a registered key and the Reserve Bank publishes spreadsheets, so
the international copies are used and Stats NZ's releases are the
spot-check reference.

OECD requests run only in this script's oecd_turn group (C); in the other
two runs oecd_turn.check() raises NotThisHour, the series is left out, and
series_guard carries the previous one over.

- gdp_level: OECD quarterly national accounts (DF_QNA), T0102, current
  prices, NZ$ million, seasonally adjusted, quarterly.
- gdp_real: DF_QNA T0101, chain-linked volume (production GDP, the
  measure Stats NZ headlines), NZ$ million, seasonally adjusted.
- gdp_growth / gdp_growth_yoy: DF_QNA T0101 G1 / GY, seasonally adjusted.
- cpi / cpi_qoq: Stats NZ's CPI is QUARTERLY (there is no monthly CPI; the
  OECD documents NZ and Australia as the quarterly exceptions). The all-items
  index from the OECD (oecd_prices.fetch_cpi_index, as Australia), with the
  annual and quarterly rates computed from it to Stats NZ's one decimal
  place; tools/audit_nz.py checks them against BIS's independent copy and
  Ciaran's spot-check against Stats NZ's release.
- unemployment: OECD infra-annual labour statistics (DF_IALFS_UNE_M), 15+,
  seasonally adjusted, QUARTERLY (the Household Labour Force Survey is
  quarterly).
- policy_rate: BIS central bank policy rates, M.NZ, the Reserve Bank's
  official cash rate, from April 1999 only, extended past BIS's last
  monthly value with BIS's daily series (see BIS_DAILY_URL). BIS joins it to the overnight
  cash rate before 17 Mar 1999; the series starts at the first full OCR
  month so one measure is shown throughout (the Malaysia rule).
- bond_yield_10y: OECD long-term interest rate (DF_FINMARK, IRLT), monthly.
- business_confidence: OECD BCICP, amplitude-adjusted, monthly.
- exports / imports / trade_balance: IMF international trade in goods
  (ITG), US dollars, converted to NZ$ at each month's rate (the OECD trade
  dataflow does not answer for New Zealand).
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: FRED DEXUSNZ, US dollars per NZ dollar (direction
  "multiply", as Australia's DEXUSAL), month end.
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
import oecd_prices
import oecd_turn
import series_guard

ISO3 = "NZL"
OUT_FILE = "data-nz.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}

QNA_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
           "Q..NZL..........?format=csvfile&startPeriod=1987-Q1")
LFS_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"
           "NZL.UNE_LF_M.._Z.Y._T.Y_GE15..Q?format=csvfile")
# Same wildcard keys the probe used (which answered); the measure is picked
# out of the reply, so no guess about dimension order is needed.
FINMARK_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_FINMARK/"
               "NZL.M.........?format=csvfile&startPeriod=1985-01")
BCI_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI/"
           "NZL.M.........?format=csvfile&startPeriod=1980-01")
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.NZ?format=csv"
# BIS's daily series runs ahead of the monthly one: on 6 Oct 2026 the monthly
# series ended at August (2.5%) though the Reserve Bank had raised the OCR to
# 2.75% on 2 September. Months after the last monthly value are filled from
# the daily series (the month's last observation; the current month shows the
# latest), the same convention as the exchange rate.
BIS_DAILY_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.NZ?format=csv&startPeriod={start}"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "NZL.*.*.M?c[TIME_PERIOD]=ge:1990-M01")
WB_URL = "https://api.worldbank.org/v2/country/NZL/indicator/{code}?format=json&per_page=200"
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1971-01-01")
OCR_START = "1999-04"     # first full month of the official cash rate (from 17 Mar 1999)
OECD_PAUSE = 2

MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230


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


def norm_period(p: str) -> str:
    """OECD/IMF period labels to the site's: 2026-Q2, 2026-07, 2024."""
    p = (p or "").strip()
    return p.replace("-M", "-")


def pct_change(points: list, lag: int, dp: int = 1) -> list:
    by = dict(points)
    out = []
    for p, v in points:
        back = _back(p, lag)
        if back in by and by[back]:
            out.append([p, round((v / by[back] - 1) * 100, dp)])
    return out


def _back(p: str, n: int) -> str | None:
    if re.fullmatch(r"\d{4}-\d{2}", p):
        t = int(p[:4]) * 12 + int(p[5:]) - 1 - n
        return f"{t // 12}-{t % 12 + 1:02d}"
    if re.fullmatch(r"\d{4}-Q[1-4]", p):
        t = int(p[:4]) * 4 + int(p[6]) - 1 - n
        return f"{t // 4}-Q{t % 4 + 1}"
    return None


def oecd_csv(url: str, tag: str) -> list:
    """Rows of one OECD CSV reply. Only in this script's OECD turn."""
    oecd_turn.check()
    time.sleep(OECD_PAUSE)
    r = requests.get(url, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [oecd] {tag} status={r.status_code}")
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def select(rows: list, value_dp: int | None = None, **want) -> list:
    out = {}
    for row in rows:
        if all((row.get(k) or "") == v for k, v in want.items()):
            try:
                v = float(row.get("OBS_VALUE") or "")
            except ValueError:
                continue
            out[norm_period(row.get("TIME_PERIOD"))] = round(v, value_dp) if value_dp is not None else v
    return sorted([[p, v] for p, v in out.items()])


# ---------------------------------------------------------------- GDP
_QNA: list = []


def qna() -> list:
    if not _QNA:
        _QNA.extend(oecd_csv(QNA_URL, "DF_QNA NZL"))
    return _QNA


def fetch_gdp_level() -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0102", PRICE_BASE="V",
                 ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA nominal GDP")


def fetch_gdp_real() -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0101", PRICE_BASE="L",
                 ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA real GDP")


def fetch_gdp_rate(transformation: str) -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0101", PRICE_BASE="L",
                 ADJUSTMENT="Y", TRANSFORMATION=transformation, UNIT_MEASURE="PC")
    return require_current(pts, QUARTERLY_MAX_AGE, f"OECD QNA real GDP {transformation}")


# ---------------------------------------------------------------- CPI
def fetch_cpi_index() -> list:
    ix = oecd_prices.fetch_cpi_index(("NZL",), "Q", label="NZL")
    if not ix:
        raise ValueError("OECD CPI index: none")
    return require_current([[norm_period(p), v] for p, v in ix], QUARTERLY_MAX_AGE, "OECD CPI index")


def fetch_cpi() -> tuple[list, list]:
    ix = fetch_cpi_index()
    return pct_change(ix, 4), pct_change(ix, 1)


# ---------------------------------------------------------------- others
def fetch_unemployment() -> list:
    rows = oecd_csv(LFS_URL, "DF_IALFS_UNE_M NZL Q")
    pts = select(rows, 1, MEASURE="UNE_LF_M", ADJUSTMENT="Y", SEX="_T", AGE="Y_GE15", FREQ="Q")
    if len(pts) < 40:
        raise ValueError(f"OECD unemployment: only {len(pts)} quarters")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD unemployment")


def fetch_bond() -> list:
    pts = select(oecd_csv(FINMARK_URL, "DF_FINMARK IRLT NZL"), 2, MEASURE="IRLT")
    return require_current(pts, MONTHLY_MAX_AGE, "OECD IRLT")


def fetch_bci() -> list:
    pts = select(oecd_csv(BCI_URL, "DF_CLI BCICP NZL"), 2, MEASURE="BCICP")
    return require_current(pts, MONTHLY_MAX_AGE, "OECD BCICP")


def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.NZ status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= OCR_START]
    pts = extend_with_daily(pts)
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def extend_with_daily(monthly: list) -> list:
    """Append months after the last monthly BIS value from the daily series.
    Any failure leaves the monthly series as it is."""
    if not monthly:
        return monthly
    last = monthly[-1][0]
    try:
        r = requests.get(BIS_DAILY_URL.format(start=last + "-01"), timeout=60, headers=dict(UA, Accept="text/csv"))
        print(f"  [bis] WS_CBPOL D.NZ status={r.status_code}")
        r.raise_for_status()
        by_month = {}
        for row in sorted(csv.DictReader(io.StringIO(r.text)), key=lambda x: x.get("TIME_PERIOD", "")):
            v, d = row.get("OBS_VALUE"), row.get("TIME_PERIOD") or ""
            if v not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                by_month[d[:7]] = float(v)
        extra = [[m, v] for m, v in sorted(by_month.items()) if m > last]
        if extra:
            print(f"  [bis] daily extends the OCR from {last} to {extra[-1][0]} ({extra[-1][1]}%)")
        return monthly + extra
    except Exception as exc:
        print(f"  [bis] daily OCR unavailable ({exc}); monthly series as is")
        return monthly


def fetch_trade_usd() -> dict:
    """Exports and imports in US$ million (converted to NZ$ in main)."""
    r = requests.get(ITG_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-itg] NZL status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = {}
    for key, ind, val in (("exports", "XG", "FOB"), ("imports", "MG", "CIF")):
        pts = {}
        for row in rows:
            if (row.get("INDICATOR"), row.get("VALUATION"), row.get("UNIT")) != (ind, val, "USD"):
                continue
            per = norm_period(row.get("TIME_PERIOD"))
            try:
                v = float(row.get("OBS_VALUE") or "")
            except ValueError:
                continue
            if re.fullmatch(r"\d{4}-\d{2}", per):
                pts[per] = v / 1e6
        out[key] = require_current(sorted([[p, v] for p, v in pts.items()]), MONTHLY_MAX_AGE, f"IMF {ind}")
    return out


def fetch_worldbank(code: str) -> list:
    r = requests.get(WB_URL.format(code=code), timeout=60, headers=UA)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"World Bank {code}: empty response")
    pts = sorted([[str(d["date"]), round(float(d["value"]), 4)] for d in payload[1]
                  if d.get("value") is not None])
    return require_current(pts, 900, f"World Bank {code}")


def fetch_fred_month_end(sid: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60, headers=UA)
    r.raise_for_status()
    month_end = {}
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        month_end[o["date"][:7]] = float(o["value"])
    return sorted([[p, v] for p, v in month_end.items()])


def usd_to_nzd(points: list, fx: dict, latest: float) -> list:
    """US$ million to NZ$ million at each month's rate (US$ per NZ$)."""
    out = []
    for p, v in points:
        rate = fx.get(p, latest)
        out.append([p, round(v / rate, 1)])
    return out


SERIES = [
    ("gdp_level", fetch_gdp_level,
     "GDP, current prices, seasonally adjusted (Stats NZ via OECD quarterly national accounts, T0102)", "NZDm", "quarters"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, production measure, chain-linked volume, seasonally adjusted (Stats NZ via OECD, T0101)", "NZDm", "quarters"),
    ("gdp_growth", lambda: fetch_gdp_rate("G1"),
     "Real GDP growth, change on previous quarter, seasonally adjusted (Stats NZ via OECD, T0101)", "%", "quarters"),
    ("gdp_growth_yoy", lambda: fetch_gdp_rate("GY"),
     "Real GDP growth, change on same quarter a year earlier, seasonally adjusted (Stats NZ via OECD, T0101)", "%", "quarters"),
    ("unemployment", fetch_unemployment,
     "Unemployment rate, 15+, seasonally adjusted, quarterly (Stats NZ household labour force survey via OECD)", "%", "quarters"),
    ("bond_yield_10y", fetch_bond, "10-year government bond yield (OECD long-term interest rate, IRLT)", "%", "months"),
    ("business_confidence", fetch_bci, "Business confidence (OECD BCICP, amplitude-adjusted, long-term average = 100)",
     "index", "months"),
    ("policy_rate", fetch_policy_rate,
     "Official cash rate (BIS central bank policy rates, M.NZ, from April 1999)", "%", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]
CPI_LABEL = {
    "cpi": "CPI, all items, change on same quarter a year earlier, from Stats NZ's all-items index (via OECD)",
    "cpi_qoq": "CPI, all items, change on previous quarter, from Stats NZ's all-items index (via OECD)",
}
TRADE_LABEL = {
    "exports": "Exports of goods, FOB, converted from US dollars at each month's rate (IMF international trade in goods)",
    "imports": "Imports of goods, CIF, converted from US dollars at each month's rate (IMF international trade in goods)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF, converted from US dollars (IMF ITG)",
}


def put(out, key, pts, label, unit, freq):
    out["series"][key] = {"label": label, "unit": unit, "freq": freq, "points": pts}
    print(f"  ok  {key:<20} {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, {freq})")


def main() -> int:
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sample": False, "series": {}}
    failures = []

    def attempt(key, fn):
        try:
            return fn()
        except oecd_turn.NotThisHour as exc:
            print(f"SKIP  {key:<20} {exc}")
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<20} {exc}")
        return None

    for key, fn, label, unit, freq in SERIES:
        pts = attempt(key, fn)
        if pts:
            put(out, key, pts, label, unit, freq)

    rates = attempt("cpi", fetch_cpi)
    if rates:
        put(out, "cpi", rates[0], CPI_LABEL["cpi"], "%", "quarters")
        put(out, "cpi_qoq", rates[1], CPI_LABEL["cpi_qoq"], "%", "quarters")

    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}

    key = os.environ.get("FRED_API_KEY")
    fx = []
    if key:
        try:
            fx = fetch_fred_month_end("DEXUSNZ", key)
            out["fx_to_usd"] = {"pair": "NZD/USD", "rate": fx[-1][1], "as_of": fx[-1][0],
                                "direction": "multiply", "history": fx}
            print(f"  ok  fx_to_usd            {fx[-1][1]} US$ per NZ$ ({fx[-1][0]}, FRED DEXUSNZ), history from {fx[0][0]}")
        except Exception as exc:
            print(f"FAIL  fx_to_usd            {exc}")
    else:
        print("note  fx_to_usd not set (no FRED_API_KEY)")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        fx = out["fx_to_usd"].get("history") or []
        print("CARRIED OVER fx_to_usd from previous run")

    # Trade needs a monthly rate to be shown in NZ$; without one it is left
    # out (and carried over) rather than converted at a wrong rate.
    if fx:
        usd = attempt("trade", fetch_trade_usd)
        if usd:
            fxm, latest = dict(fx), fx[-1][1]
            nz = {k: usd_to_nzd(v, fxm, latest) for k, v in usd.items()}
            # The IMF often has exports a month before imports. All three
            # series end at the last month both are published, so the
            # Trade tiles always describe the same month.
            common = set(dict(nz["exports"])) & set(dict(nz["imports"]))
            nz = {k: [p for p in v if p[0] in common] for k, v in nz.items()}
            m = dict(nz["imports"])
            nz["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in nz["exports"] if p in m]
            for k, v in nz.items():
                put(out, k, v, TRADE_LABEL[k], "NZDm", "months")
    else:
        print("note  trade left out: no monthly exchange rate to convert it with")

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


if __name__ == "__main__":
    sys.exit(main())
