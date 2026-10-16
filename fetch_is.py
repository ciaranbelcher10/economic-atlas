"""Fetch Iceland's economic series and write data-is.json.

Run:  python3 fetch_is.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

Sources, chosen from tools/probe_country.py (13 Oct 2026). Iceland is an
OECD member, so the OECD republishes Statistics Iceland's own figures.
Statistics Iceland's PxWeb API answers, but the OECD copies are already in
the shape the site's other OECD fetchers read, so they are used and
Statistics Iceland's releases are the spot-check reference. Built v1.7.56
from fetch_nz.py. Run 1 not yet made: every source below is unconfirmed
until the first real run and audit.

OECD requests run only in this script's oecd_turn group; in the other two
runs oecd_turn.check() raises NotThisHour, the series is left out, and
series_guard carries the previous one over.

- gdp_level: OECD quarterly national accounts (DF_QNA), T0102, current
  prices, ISK million, seasonally adjusted, quarterly.
- gdp_real: DF_QNA T0102, chain-linked volume (PRICE_BASE L), ISK million,
  seasonally adjusted. (Iceland's QNA is served under T0102 only.)
- gdp_growth / gdp_growth_yoy: DF_QNA T0102 G1 / GY, seasonally adjusted.
- cpi / cpi_mom: Statistics Iceland's national CPI (not the HICP), the
  all-items index from the OECD (oecd_prices.fetch_cpi_index, monthly), with
  the twelve-month and one-month rates computed from it to one decimal
  place; tools/audit_is.py checks them against the OECD's own published
  rates and BIS's independent copy.
- unemployment: OECD infra-annual labour statistics (DF_IALFS_UNE_M), 15+,
  seasonally adjusted, monthly (Statistics Iceland's labour force survey).
- policy_rate: BIS central bank policy rates, M.IS, the Central Bank of
  Iceland's key rate (the seven-day term deposit rate), from June 2014 only:
  BIS splices three earlier measures before 21 May 2014, and the series
  starts at the first full month of the current one (the Malaysia rule).
  Extended past BIS's last monthly value with BIS's daily series.
- exports / imports / trade_balance: IMF international trade in goods
  (ITG), US dollars, converted to krónur at the BIS monthly average rate
  (WS_XRU M.IS.ISK.A). The OECD trade dataflow does not answer for Iceland.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, krónur per US$, annual average
  (fx_config.ANNUAL: there is no Federal Reserve H.10 series for the króna).
Not served: bond_yield_10y (the OECD's IRLT for Iceland stops in August
2022), business_confidence (the OECD publishes no BCICP for Iceland).
"""
from __future__ import annotations

import redact_stream  # noqa: F401  (v1.7.42: masks api_key= in all output)
import csv
import io
import json
import re
import sys
import time
from datetime import datetime, timezone

import requests

import bis_daily
import imf_weo
import oecd_prices
import oecd_turn
import series_guard

ISO3 = "ISL"
OUT_FILE = "data-is.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {
    # v1.7.56 run 4: months with copied IMF figures left out (drop_mirrored)
    "exports": "months where the IMF's imports equal its exports exactly are left out",
    "imports": "months where the IMF's imports equal its exports exactly are left out",
    "trade_balance": "months where the IMF's imports equal its exports exactly are left out",
}

QNA_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
           "Q..ISL..........?format=csvfile&startPeriod=1995-Q1")
LFS_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"
           "ISL.UNE_LF_M.._Z.Y._T.Y_GE15..M?format=csvfile")
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.IS?format=csv"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.IS.ISK.A?format=csv"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "ISL.*.*.M?c[TIME_PERIOD]=ge:1995-M01")
WB_URL = "https://api.worldbank.org/v2/country/ISL/indicator/{code}?format=json&per_page=200"
KEY_RATE_START = "2014-06"   # first full month of the term deposit rate (from 21 May 2014)
OECD_PAUSE = 2

MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230
TRADE_MAX_AGE = 200       # probe, 13 Oct 2026: ITG imports to May 2026


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
        _QNA.extend(oecd_csv(QNA_URL, "DF_QNA ISL"))
    return _QNA


def fetch_gdp_level() -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0102", PRICE_BASE="V",
                 ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA nominal GDP")


def fetch_gdp_real() -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0102", PRICE_BASE="L",
                 ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA real GDP")


def fetch_gdp_rate(transformation: str) -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", TABLE_IDENTIFIER="T0102", PRICE_BASE="L",
                 ADJUSTMENT="Y", TRANSFORMATION=transformation, UNIT_MEASURE="PC")
    return require_current(pts, QUARTERLY_MAX_AGE, f"OECD QNA real GDP {transformation}")


# ---------------------------------------------------------------- CPI
def fetch_cpi_index() -> list:
    ix = oecd_prices.fetch_cpi_index(("ISL",), "M", label="ISL")
    if not ix:
        raise ValueError("OECD CPI index: none")
    return require_current([[norm_period(p), v] for p, v in ix], MONTHLY_MAX_AGE, "OECD CPI index")


def fetch_cpi() -> tuple[list, list]:
    ix = fetch_cpi_index()
    return pct_change(ix, 12), pct_change(ix, 1)


# ---------------------------------------------------------------- others
def fetch_unemployment() -> list:
    rows = oecd_csv(LFS_URL, "DF_IALFS_UNE_M ISL M")
    pts = select(rows, 1, MEASURE="UNE_LF_M", ADJUSTMENT="Y", SEX="_T", AGE="Y_GE15", FREQ="M")
    if len(pts) < 120:
        raise ValueError(f"OECD unemployment: only {len(pts)} months")
    bad = [p for p in pts if not 0 < p[1] < 25]
    if bad:
        raise ValueError(f"OECD unemployment: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "OECD unemployment")


def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.IS status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= KEY_RATE_START]
    pts = extend_with_daily(pts)
    bad = [p for p in pts if not (0 <= p[1] < 25)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def extend_with_daily(monthly: list) -> list:
    """Months after the last monthly BIS value, from the daily series
    (shared rule in bis_daily.py since v1.7.13)."""
    return bis_daily.extend(monthly, "IS", "key rate")


def fetch_trade_usd() -> dict:
    """Exports and imports in US$ million (converted to ISK in main)."""
    r = requests.get(ITG_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-itg] ISL status={r.status_code}")
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
        out[key] = require_current(sorted([[p, v] for p, v in pts.items()]), TRADE_MAX_AGE, f"IMF {ind}")
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


def fetch_bis_fx_avg() -> dict:
    """BIS monthly average krónur per US$, {"YYYY-MM": rate}."""
    r = requests.get(BIS_FX_AVG_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_XRU M.IS.ISK.A status={r.status_code}")
    r.raise_for_status()
    rate = {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", row.get("TIME_PERIOD", ""))}
    bad = [k for k, v in rate.items() if k >= "2000" and not 50 < v < 250]
    if bad:
        raise ValueError(f"BIS ISK rate: implausible value {bad[0]} {rate[bad[0]]}")
    return rate


def drop_mirrored(usd: dict) -> dict:
    """Leaves out months where the IMF's imports equal its exports exactly.
    Run 1 (13 Oct 2026): January 2026, March 2013 and April 2013 carried
    identical figures for both flows (a balance of exactly zero), the
    import figure a copy of the export one. Named in the log; the audit
    checks no such month is served."""
    x, m = dict(usd["exports"]), dict(usd["imports"])
    bad = sorted(p for p in x if p in m and x[p] == m[p])
    for p in bad:
        print(f"  [imf-itg] ISL {p}: imports equal exports exactly ({x[p]} US$m), left out as a copied figure")
    return {k: [q for q in v if q[0] not in bad] for k, v in usd.items()}


def usd_to_isk(points: list, rate: dict) -> list:
    """US$ million to ISK million at each month's BIS average rate. A month
    with no rate is left out, never converted at another month's rate."""
    return [[p, round(v * rate[p], 1)] for p, v in points if p in rate]


SERIES = [
    ("gdp_level", fetch_gdp_level,
     "GDP, current prices, seasonally adjusted (Statistics Iceland via OECD quarterly national accounts, T0102)", "ISKm", "quarters"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, chain-linked volume, seasonally adjusted (Statistics Iceland via OECD, T0102)", "ISKm", "quarters"),
    ("gdp_growth", lambda: fetch_gdp_rate("G1"),
     "Real GDP growth, change on previous quarter, seasonally adjusted (Statistics Iceland via OECD, T0102)", "%", "quarters"),
    ("gdp_growth_yoy", lambda: fetch_gdp_rate("GY"),
     "Real GDP growth, change on same quarter a year earlier, seasonally adjusted (Statistics Iceland via OECD, T0102)", "%", "quarters"),
    ("unemployment", fetch_unemployment,
     "Unemployment rate, 15+, seasonally adjusted, monthly (Statistics Iceland labour force survey via OECD)", "%", "months"),
    ("policy_rate", fetch_policy_rate,
     "Central Bank of Iceland key rate, seven-day term deposits (BIS central bank policy rates, M.IS, from June 2014)", "%", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]
CPI_LABEL = {
    "cpi": "CPI, all items, change on same month a year earlier, from Statistics Iceland's all-items index (via OECD)",
    "cpi_mom": "CPI, all items, change on previous month, not seasonally adjusted, from Statistics Iceland's all-items index (via OECD)",
}
TRADE_LABEL = {
    "exports": "Exports of goods, FOB, US$ converted to krónur at the BIS monthly average rate (IMF international trade in goods)",
    "imports": "Imports of goods, CIF, US$ converted to krónur at the BIS monthly average rate (IMF international trade in goods)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF, krónur (IMF ITG, converted at the BIS monthly average rate)",
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
        put(out, "cpi", rates[0], CPI_LABEL["cpi"], "%", "months")
        put(out, "cpi_mom", rates[1], CPI_LABEL["cpi_mom"], "%", "months")

    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}

    try:
        fx = fetch_worldbank("PA.NUS.FCRF")
        out["fx_to_usd"] = {"pair": "ISK/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx,
                            # Dollarise leaves out pre-1981 years (fx_config.SERIES_START): the new krona
                            # replaced the old at 100 to 1 on 1 January 1981, and the World Bank restates
                            # the years before in new kronur (run 1 FX sheet: US$276 per kr100 in 1960).
                            "floor": "1981"}
        print(f"  ok  fx_to_usd            {fx[-1][1]} kronur per US$ ({fx[-1][0]}, World Bank PA.NUS.FCRF annual average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    # Trade is converted at BIS's monthly average rate; without it, trade
    # is left out (and carried over) rather than converted at a wrong rate.
    usd = attempt("trade", fetch_trade_usd)
    rate = attempt("trade", fetch_bis_fx_avg) if usd else None
    if usd and rate:
        isk = {k: usd_to_isk(v, rate) for k, v in drop_mirrored(usd).items()}
        # All three series end at the last month both flows are published,
        # so the Trade tiles always describe the same month.
        common = set(dict(isk["exports"])) & set(dict(isk["imports"]))
        isk = {k: [p for p in v if p[0] in common] for k, v in isk.items()}
        m = dict(isk["imports"])
        isk["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in isk["exports"] if p in m]
        if isk["trade_balance"]:
            for k, v in isk.items():
                put(out, k, v, TRADE_LABEL[k], "ISKm", "months")
        else:
            failures.append("trade")
            print("FAIL  trade                no month with exports, imports and a BIS rate")

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
