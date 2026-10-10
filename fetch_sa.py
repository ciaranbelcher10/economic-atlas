"""Fetch Saudi Arabia's economic series and write data-sa.json.

Run:  FRED_API_KEY=yourkey python3 fetch_sa.py   (FRED is not used; the key is harmless)
In GitHub Actions this runs with the other fetchers.

Built v1.7.35 from fetch_nz.py (New Zealand: OECD national accounts, BIS
policy rate, IMF trade). Sources chosen from tools/probe_country.py SAU SA
(9 Oct 2026). Saudi Arabia is not an OECD member but is in the G20, and the
OECD republishes GASTAT's quarterly national accounts and consumer prices.
GASTAT's own database portal is a script-rendered app (to probe later);
SAMA's statistics page moved (404). The riyal is pegged at 3.75 per US$.

OECD requests run only in this script's oecd_turn group (A).

- gdp_level: OECD DF_QNA, GDP at current prices, riyal million, seasonally
  adjusted, quarterly. If the OECD carries only the annualised (LA) form,
  it is divided by four, and the label says so.
- gdp_real: DF_QNA, GDP at constant prices (PRICE_BASE L), SA, quarterly.
- gdp_growth: DF_QNA G1, seasonally adjusted (GASTAT's q/q).
- gdp_growth_yoy: computed from DF_QNA's UNADJUSTED constant-price levels,
  matching GASTAT's headline (the OECD's GY is on the adjusted series).
  Oil output moves both sharply (Q2 2026: oil activities -24.7% y/y).
- cpi / cpi_mom: GASTAT's CPI, all items, from the OECD all-items index
  (oecd_prices.fetch_cpi_index, monthly), annual and monthly rates computed
  to one decimal place; the IMF CPI dataset is the audit's cross-check.
- unemployment: World Bank SL.UEM.TOTL.ZS, the ILO's modelled estimate,
  annual, all residents. A disclosed stand-in: GASTAT's quarterly labour
  force survey (total and Saudi nationals) is not in any international
  database the probe reached. Replace when GASTAT's portal is probed.
- policy_rate: BIS central bank policy rates, M.SA (SAMA's official repo
  rate, the BIS series from January 2000 per its compilation note),
  extended with BIS daily.
- exports / imports / trade_balance: IMF international trade in goods
  (ITG), in riyals as the IMF publishes them (FOB_XDC, CIF_XDC), monthly;
  all three end at the last month with both flows.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, riyals per US$, annual (the peg).
Not served: 10-year bond yield and business confidence (no source in the
probe: OECD DF_FINMARK has only the exchange rate for SAU, DF_CLI 404s).
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

ISO3 = "SAU"
OUT_FILE = "data-sa.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}

QNA_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
           "Q..SAU..........?format=csvfile&startPeriod=1990-Q1")
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.SA?format=csv"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "SAU.*.*.M?c[TIME_PERIOD]=ge:1990-M01")
WB_URL = "https://api.worldbank.org/v2/country/SAU/indicator/{code}?format=json&per_page=200"
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1971-01-01")
POLICY_START = "2000-01"  # BIS compilation note: "From 1 Jan 2000 onwards: official market repo rate"
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
        _QNA.extend(oecd_csv(QNA_URL, "DF_QNA SAU"))
    return _QNA


def fetch_gdp_level() -> list:
    """Nominal GDP, riyal million, SA. GASTAT via the OECD publishes no
    T01xx table split, so the table is not filtered (the values agree)."""
    pts = select(qna(), 1, TRANSACTION="B1GQ", PRICE_BASE="V", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    if not pts:
        la = select(qna(), 1, TRANSACTION="B1GQ", PRICE_BASE="V", ADJUSTMENT="Y", TRANSFORMATION="LA", UNIT_MEASURE="XDC")
        pts = [[p, round(v / 4, 1)] for p, v in la]
        if pts:
            print("  note gdp_level: OECD has only the annualised (LA) form; divided by four")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA nominal GDP")


def fetch_gdp_real() -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", PRICE_BASE="L", ADJUSTMENT="Y", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pts, QUARTERLY_MAX_AGE, "OECD QNA real GDP")


def fetch_gdp_yoy_nsa() -> list:
    """GASTAT headlines the year-on-year change of UNADJUSTED real GDP (Q2 2026:
    -4.7%, from SAR 1,197.99bn to 1,141.54bn); the OECD's GY rate is computed
    on the seasonally adjusted series (-4.3%). Computed here from the OECD's
    unadjusted constant-price levels, so the tile matches GASTAT's release.
    Spot-check of 9 Oct 2026."""
    lv = select(qna(), 1, TRANSACTION="B1GQ", PRICE_BASE="L", ADJUSTMENT="N", TRANSFORMATION="N", UNIT_MEASURE="XDC")
    return require_current(pct_change(lv, 4), QUARTERLY_MAX_AGE, "OECD QNA real GDP, unadjusted, y/y")


def fetch_gdp_rate(transformation: str) -> list:
    pts = select(qna(), 1, TRANSACTION="B1GQ", PRICE_BASE="L", ADJUSTMENT="Y", TRANSFORMATION=transformation, UNIT_MEASURE="PC")
    return require_current(pts, QUARTERLY_MAX_AGE, f"OECD QNA real GDP {transformation}")


# ---------------------------------------------------------------- CPI
def fetch_cpi_index() -> list:
    ix = oecd_prices.fetch_cpi_index(("SAU",), "M", label="SAU")
    if not ix:
        raise ValueError("OECD CPI index: none")
    return require_current([[norm_period(p), v] for p, v in ix], MONTHLY_MAX_AGE, "OECD CPI index")


def fetch_cpi() -> tuple[list, list]:
    ix = fetch_cpi_index()
    return pct_change(ix, 12), pct_change(ix, 1)


# ---------------------------------------------------------------- others
def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.SA status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= POLICY_START]
    pts = extend_with_daily(pts)
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def extend_with_daily(monthly: list) -> list:
    """Months after the last monthly BIS value, from the daily series
    (shared rule in bis_daily.py since v1.7.13)."""
    return bis_daily.extend(monthly, "SA", "SAMA repo rate")


def fetch_trade() -> dict:
    """Exports FOB and imports CIF in riyal million, as the IMF publishes them
    (UNIT XDC, scale 6). Both end at the last month with both flows."""
    r = requests.get(ITG_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-itg] SAU status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = {}
    for key, ind, val in (("exports", "XG", "FOB"), ("imports", "MG", "CIF")):
        pts = {}
        for row in rows:
            if (row.get("INDICATOR"), row.get("VALUATION"), row.get("UNIT")) != (ind, val, "XDC"):
                continue
            per = norm_period(row.get("TIME_PERIOD"))
            try:
                v = float(row.get("OBS_VALUE") or "")
            except ValueError:
                continue
            if re.fullmatch(r"\d{4}-\d{2}", per):
                pts[per] = round(v / 1e6, 1)
        out[key] = require_current(sorted([[p, v] for p, v in pts.items()]), MONTHLY_MAX_AGE, f"IMF {ind}")
    common = set(dict(out["exports"])) & set(dict(out["imports"]))
    out = {k: [p for p in v if p[0] in common] for k, v in out.items()}
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    if not out["trade_balance"]:
        raise ValueError("IMF trade: no month with both exports and imports")
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


SERIES = [
    ("gdp_level", fetch_gdp_level,
     "GDP, current prices, seasonally adjusted (GASTAT via OECD quarterly national accounts)", "SARm", "quarters"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, constant prices, seasonally adjusted (GASTAT via OECD quarterly national accounts)", "SARm", "quarters"),
    ("gdp_growth", lambda: fetch_gdp_rate("G1"),
     "Real GDP growth, change on previous quarter, seasonally adjusted (GASTAT via OECD)", "%", "quarters"),
    ("gdp_growth_yoy", fetch_gdp_yoy_nsa,
     "Real GDP growth, change on same quarter a year earlier, not seasonally adjusted (GASTAT via OECD; GASTAT's headline)", "%", "quarters"),
    ("unemployment", lambda: fetch_worldbank("SL.UEM.TOTL.ZS"),
     "Unemployment rate, total, ILO modelled estimate, annual (World Bank SL.UEM.TOTL.ZS)", "%", "years"),
    ("policy_rate", fetch_policy_rate,
     "SAMA repo rate, end of month (BIS central bank policy rates, M.SA, from January 2000)", "%", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]
CPI_LABEL = {
    "cpi": "CPI, all items, change on same month a year earlier, from GASTAT's all-items index (via OECD)",
    "cpi_mom": "CPI, all items, change on previous month, from GASTAT's all-items index (via OECD)",
}
TRADE_LABEL = {
    "exports": "Exports of goods, FOB, riyals (IMF international trade in goods, from GASTAT)",
    "imports": "Imports of goods, CIF, riyals (IMF international trade in goods, from GASTAT)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF, riyals (IMF ITG)",
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
        out["fx_to_usd"] = {"pair": "SAR/USD", "rate": fx[-1][1], "as_of": fx[-1][0],
                            "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} riyals per US$ ({fx[-1][0]}, World Bank), history from {fx[0][0]}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    tr = attempt("trade", fetch_trade)
    if tr:
        for k, v in tr.items():
            put(out, k, v, TRADE_LABEL[k], "SARm", "months")

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
