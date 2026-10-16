"""Fetch Peru's economic series and write data-pe.json.

Run:  python3 fetch_pe.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

Sources, chosen from tools/probe_country.py (13 Oct 2026, full probe and
--quick follow-up). The Central Reserve Bank of Peru (BCRP) publishes an
open statistics API that answers from outside Peru, so its own series are
used wherever it publishes them; the probe read each series' title from the
reply, which is how the codes below were confirmed. Built v1.7.56. Run 1
not yet made: every source below is unconfirmed until the first real run
and audit. Not an OECD member: no OECD calls.

- cpi / cpi_mom: BCRP's own Metropolitan Lima CPI rates, INEI's headline
  index, as published: PN01273PM (twelve-month change) and PN01271PM
  (monthly change), to one decimal place. Run 1 (13 Oct 2026) used the IMF's
  CPI rates, which differed from BCRP's Lima figures by up to 0.28 points a
  month, so the publisher's own series are used; the IMF's are reported by
  the audit, not served.
- gdp_real: BCRP PN02538AQ, GDP by expenditure, millions of soles at 2007
  prices, quarterly, not seasonally adjusted (BCRP publishes no seasonally
  adjusted quarterly GDP). The page rolls four quarters into a year.
- gdp_growth_yoy: BCRP PN02507AQ, real GDP, change on the same quarter a
  year earlier, as published, to one decimal place.
- gdp_level / gdp_growth: World Bank annual national accounts
  (NY.GDP.MKTP.CN, NY.GDP.MKTP.KN), soles, scaled to million. BCRP's
  quarterly GDP at current prices was not found by the probe.
- policy_rate: BIS central bank policy rates, M.PE, BCRP's reference rate,
  from September 2003 (when BCRP adopted it as its policy instrument),
  extended past BIS's last monthly value with BIS's daily series.
  BCRP PD04722MM is the audit's cross-check.
- exports / imports / trade_balance: BCRP trade balance, FOB values, US$
  million (PN38714BM exports, PN38718BM imports), converted to soles at the
  BIS monthly average rate (WS_XRU M.PE.PEN.A).
- unemployment: World Bank SL.UEM.TOTL.ZS (ILO modelled estimate), annual.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, soles per US$, annual average
  (fx_config.ANNUAL: no Federal Reserve H.10 series for the sol).
Not served: quarterly GDP at current prices, monthly labour data, bond
yield, business confidence.
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

import bis_daily
import imf_weo
import series_guard

ISO3 = "PER"
OUT_FILE = "data-pe.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230
REF_RATE_START = "2003-09"   # BCRP's reference rate became the policy instrument in September 2003

BCRP = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{code}/json/{start}/{end}"
BIS_POLICY_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.PE?format=csv"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.PE.PEN.A?format=csv"
WB_URL = "https://api.worldbank.org/v2/country/PER/indicator/{code}?format=json&per_page=200"

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


# ---------------------------------------------------------------- BCRP
MESES = {"Ene": 1, "Feb": 2, "Mar": 3, "Abr": 4, "May": 5, "Jun": 6,
         "Jul": 7, "Ago": 8, "Sep": 9, "Set": 9, "Oct": 10, "Nov": 11, "Dic": 12}


def bcrp_period(name: str) -> str | None:
    """BCRP period names to the site's: "Ene.2025" -> 2025-01, "T1.23" -> 2023-Q1."""
    m = re.fullmatch(r"([A-Z][a-z]{2})\.(\d{4})", name.strip())
    if m and m.group(1) in MESES:
        return f"{m.group(2)}-{MESES[m.group(1)]:02d}"
    m = re.fullmatch(r"T([1-4])\.(\d{2})", name.strip())
    if m:
        yy = int(m.group(2))
        return f"{1900 + yy if yy >= 50 else 2000 + yy}-Q{m.group(1)}"
    return None


def bcrp(code: str, start: str, end: str, title_has: str) -> list:
    """One BCRP series. The reply's title must contain `title_has`, so a
    series code that has been reassigned fails loudly instead of feeding the
    page the wrong numbers. "n.d." (no data) entries are skipped."""
    r = requests.get(BCRP.format(code=code, start=start, end=end), timeout=60, headers=UA)
    print(f"  [bcrp] {code} status={r.status_code}")
    r.raise_for_status()
    payload = r.json()
    title = (payload.get("config") or {}).get("title", "")
    if title_has.lower() not in title.lower():
        raise ValueError(f"BCRP {code}: title is {title!r}, expected it to mention {title_has!r}")
    pts = {}
    for row in payload.get("periods") or []:
        per = bcrp_period(row.get("name", ""))
        try:
            v = float((row.get("values") or [""])[0])
        except (TypeError, ValueError):
            continue
        if per:
            pts[per] = v
    if not pts:
        raise ValueError(f"BCRP {code}: no usable periods")
    return sorted([[p, v] for p, v in pts.items()])


# ---------------------------------------------------------------- series
def fetch_gdp_real() -> list:
    pts = bcrp("PN02538AQ", "1980-1", "2030-4", "millones S/ 2007")
    pts = [[p, round(v, 1)] for p, v in pts]
    bad = [p for p in pts if not 10_000 < p[1] < 1_000_000]
    if bad:
        raise ValueError(f"BCRP real GDP: implausible quarter {bad[0]} (PEN million at 2007 prices)")
    return require_current(pts, QUARTERLY_MAX_AGE, "BCRP real GDP")


def fetch_gdp_growth_yoy() -> list:
    pts = [[p, round(v, 1)] for p, v in bcrp("PN02507AQ", "1980-1", "2030-4", "variación porcentual interanual")]
    # Run 1 (13 Oct 2026): Q2 2021 was +42.1% against Q2 2020 (-29.8%, the
    # pandemic lockdown); the bound is wide enough for that rebound.
    bad = [p for p in pts if not -40 < p[1] < 50]
    if bad:
        raise ValueError(f"BCRP GDP growth: implausible quarter {bad[0]}")
    return require_current(pts, QUARTERLY_MAX_AGE, "BCRP GDP growth y/y")


def fetch_policy_rate() -> list:
    r = requests.get(BIS_POLICY_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.PE status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= REF_RATE_START]
    pts = bis_daily.extend(pts, "PE", "reference rate")
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def fill_single_gaps(rate: dict) -> dict:
    """A month BIS skips on its own takes the mean of the months either
    side, named in the log; a run of two or more is left for the audit."""
    out = dict(rate)
    keys = sorted(rate)
    for a, b in zip(keys, keys[1:]):
        mid = _back(b, 1)
        if mid != a and _back(mid, 1) == a:
            out[mid] = round((rate[a] + rate[b]) / 2, 4)
            print(f"  [bis] WS_XRU M.PE.PEN.A has no {mid}: using the mean of {a} and {b} ({out[mid]})")
    return out


def fetch_trade() -> dict:
    r = requests.get(BIS_FX_AVG_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_XRU M.PE.PEN.A status={r.status_code}")
    r.raise_for_status()
    rate = {row["TIME_PERIOD"]: float(row["OBS_VALUE"]) for row in csv.DictReader(io.StringIO(r.text))
            if row.get("OBS_VALUE") not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}", row.get("TIME_PERIOD", ""))}
    bad = [k for k, v in rate.items() if k >= "1994" and not 1.5 < v < 6]
    if bad:
        raise ValueError(f"BIS PEN rate: implausible value {bad[0]} {rate[bad[0]]}")
    rate = fill_single_gaps(rate)
    out = {}
    for key, code, word in (("exports", "PN38714BM", "Exportaciones"), ("imports", "PN38718BM", "Importaciones")):
        usd = bcrp(code, "1994-1", "2030-12", "valores FOB (millones US$)")
        pts = [[p, round(v * rate[p], 1)] for p, v in usd if p in rate]
        bad = [p for p in usd if not 0 < p[1] < 50_000]
        if bad:
            raise ValueError(f"BCRP {word}: implausible month {bad[0]} (US$ million)")
        out[key] = require_current(pts, MONTHLY_MAX_AGE, f"BCRP {word} (soles)")
    common = set(dict(out["exports"])) & set(dict(out["imports"]))
    out = {k: [p for p in v if p[0] in common] for k, v in out.items()}
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    if not out["trade_balance"]:
        raise ValueError("BCRP trade: no month with exports, imports and a BIS rate")
    return out


def wb_scaled(code: str) -> list:
    return [[p, round(v / 1e6, 1)] for p, v in fetch_worldbank(code)]


def fetch_gdp_level() -> list:
    """From 1991, the sol's first year. The World Bank restates every year in
    today's soles (one sol is a billion of the soles of the 1980s), so the
    years before round to zero million and say nothing (run 1, 13 Oct 2026)."""
    return [p for p in wb_scaled("NY.GDP.MKTP.CN") if p[0] >= "1991"]


def fetch_gdp_growth() -> list:
    return pct_change(fetch_worldbank("NY.GDP.MKTP.KN"), 1)


def fetch_cpi(code: str, title_has: str, lo: float, hi: float) -> list:
    """A BCRP Lima CPI rate, from 1995 (after the early-1990s hyperinflation
    had wound down), to one decimal place."""
    pts = [[p, round(v, 1)] for p, v in bcrp(code, "1995-1", "2030-12", title_has)]
    bad = [p for p in pts if not lo < p[1] < hi]
    if bad:
        raise ValueError(f"BCRP {code}: implausible month {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, f"BCRP {code}")


SERIES = [
    ("cpi", lambda: fetch_cpi("PN01273PM", "var% 12 meses", -5, 30),
     "CPI, all items, Metropolitan Lima, change on same month a year earlier (BCRP, PN01273PM, from INEI)", "%", "months"),
    ("cpi_mom", lambda: fetch_cpi("PN01271PM", "var% mensual", -5, 10),
     "CPI, all items, Metropolitan Lima, change on previous month, not seasonally adjusted (BCRP, PN01271PM)", "%", "months"),
    ("policy_rate", fetch_policy_rate,
     "BCRP reference rate (BIS central bank policy rates, M.PE, from September 2003)", "%", "months"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, millions of soles at 2007 prices, not seasonally adjusted (BCRP, PN02538AQ)", "PENm", "quarters"),
    ("gdp_growth_yoy", fetch_gdp_growth_yoy,
     "Real GDP growth, change on same quarter a year earlier, as published (BCRP, PN02507AQ)", "%", "quarters"),
    ("trade", fetch_trade, {
        "exports": "Exports of goods, FOB, US$ converted to soles at the BIS monthly average rate (BCRP trade balance, PN38714BM)",
        "imports": "Imports of goods, FOB, US$ converted to soles at the BIS monthly average rate (BCRP trade balance, PN38718BM)",
        "trade_balance": "Trade balance, goods, exports less imports, both FOB, soles (BCRP, converted at the BIS monthly average rate)",
    }, "PENm", "months"),
    ("gdp_level", fetch_gdp_level, "GDP, current prices, annual, from 1991 (World Bank)", "PENm", "years"),
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
        # Pre-1991 rates round to zero soles per US$ (see fetch_gdp_level) and
        # would divide by zero; Dollarise leaves those years out anyway.
        fx = [p for p in fetch_worldbank("PA.NUS.FCRF") if p[1] > 0]
        out["fx_to_usd"] = {"pair": "PEN/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx,
                           # Dollarise leaves out pre-1991 years (fx_config.SERIES_START)
                           "floor": "1991"}
        print(f"  ok  fx_to_usd            {fx[-1][1]} soles per US$ ({fx[-1][0]}, World Bank PA.NUS.FCRF annual average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
