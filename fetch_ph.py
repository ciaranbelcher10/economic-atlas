"""Fetch the Philippines' economic series and write data-ph.json.

Run:  python3 fetch_ph.py   (FRED is not used)
In GitHub Actions this runs with the other fetchers.

Built v1.7.49 from fetch_my.py (Malaysia: national statistics API first,
BIS policy rate). Run 1 (12 Oct 2026) fixed: PXWeb replies carry a byte-
order mark, the price variable is "Type of Valuation", value texts carry
classification codes ("0 - ALL ITEMS"), the IMF's peso trade stops in 2022,
and PSA's published q/q table mislabels its periods (see gdp_growth).
Confirmed by the first real runs and audit (12 Oct 2026: run 1 fetched
17/17 series with 12 audit FAILs, cleared by the fixes and named events
in tools/audit_ph.py; run 3: 38 PASS/INFO, 0 FAIL). fx_to_usd moved to the
World Bank annual rate after run 3, for fx_config.ANNUAL.
Sources chosen from tools/probe_country.py PHL PH and the batch 5 round 2
and 3 probes (12 Oct 2026). National first: the Philippine Statistics
Authority's OpenSTAT (PXWeb API) answers from outside the Philippines.
Not an OECD member: no OECD calls.

PXWeb tables are queried by value TEXT (resolved to codes from each table's
own metadata), so a code change at PSA does not silently select the wrong
row; any variable the query does not name must have a single obvious value
(one value, or a Philippines / both sexes / total value), else the series
fails with the variable's values printed.

- gdp_level: PSA quarterly national accounts, GDP by expenditure, current
  prices, peso million, not seasonally adjusted (OpenSTAT 2B/NA/QT/1SUM
  0012B5BEXQ1). The page rolls four quarters into a year.
- gdp_real: PSA seasonally adjusted national accounts, GDP at constant 2018
  prices (2B/SANA/1SUM 012B5BEXS1).
- gdp_growth: real GDP change on the previous quarter, seasonally adjusted,
  computed from PSA's seasonally adjusted real GDP levels (012B5BEXS1) to
  one decimal place, which is how PSA computes its headline q/q. PSA's own
  growth table (022B5BEXS2) came back in run 1 with periods we could not
  read reliably (it ran to "2026-Q4" and missed 2.1pp against the levels),
  so it is not used.
- gdp_growth_yoy: real GDP change on the same quarter a year earlier,
  computed from PSA's UNADJUSTED constant-price levels (0012B5BEXQ1), which
  is PSA's headline growth figure.
- cpi: PSA's published year-on-year rate, all items, Philippines, 2018=100,
  from January 2019 (0012M4ACP23). January 1995 to December 2018 is the
  year-on-year change in PSA's 2018-based index (back-cast 0012M4ACP28
  joined to 0012M4ACP22), to one decimal place. The fetch fails unless that
  same computation reproduces PSA's published rate from 2019 within 0.15pp.
  PSA's older published back series (0012M4ACP27) is not used: run 2 showed
  it leaves a hole before 2019 and breaks at its join with the index.
- cpi_mom: change on the previous month in PSA's all-items index
  (0012M4ACP22), not seasonally adjusted, to PSA's one decimal place.
- unemployment / participation: PSA labour force survey rates, both sexes,
  not seasonally adjusted (1B/LFS 0021B3FKEI2), rounded to PSA's published
  one decimal place (the table carries three). The survey was quarterly
  (January, April, July, October rounds) before it became monthly, so the
  series start at the first month of the unbroken monthly run.
- employment: employment-to-population ratio, computed as participation
  times PSA's employment rate (employed as a share of the labour force,
  which is what PSA calls the employment rate), from the unrounded table
  values, to one decimal place.
- policy_rate: BIS central bank policy rates, M.PH (BSP's reverse
  repurchase rate), from January 2002, extended with BIS daily. Before 2002
  BIS carries a money-market measure with six gaps and monthly moves of up
  to 19.5pp (run 1), not a policy rate set in steps.
- exports / imports / trade_balance: IMF international trade in goods (ITG),
  in US dollars (PSA's own headline currency), converted to pesos at the
  BIS monthly average rate (WS_XRU M.PH.PHP.A); the IMF's peso figures stop
  in 2022. All three end at the last month with both flows.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: World Bank PA.NUS.FCRF, pesos per US$, annual average, as for
  the other currencies in fx_config.ANNUAL (fetch_fx_daily.py reads annual
  history only). BIS's monthly rate is used for the trade conversion above.
Not served: 10-year bond yield (no source in the probe states a 10-year
maturity) and business confidence (BSP's survey is quarterly and a
different measure; no OECD coverage).
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
import series_guard

ISO3 = "PHL"
OUT_FILE = "data-ph.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}

PX = "https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB/"
PX_PAUSE = 2
T_GDP_NSA = "2B/NA/QT/1SUM/0012B5BEXQ1.px"
T_GDP_SA = "2B/SANA/1SUM/012B5BEXS1.px"
T_CPI_YOY = "2M/PI/CPI/2018NEW/0012M4ACP23.px"
T_CPI_INDEX = "2M/PI/CPI/2018NEW/0012M4ACP22.px"
T_CPI_INDEX_BACK = "2M/PI/CPI/2018NEW/0012M4ACP28.px"
T_LFS = "1B/LFS/0021B3FKEI2.px"

BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.PH?format=csv"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.PH.PHP.A?format=csv"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "PHL.*.*.M?c[TIME_PERIOD]=ge:1990-M01")
WB_URL = "https://api.worldbank.org/v2/country/PHL/indicator/{code}?format=json&per_page=200"
SERIES_START = {"policy_rate": "2002-01"}  # run 1: a spliced money-market measure before 2002

MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230

GDP_ITEM = r"^\W*gross domestic product\W*$"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
DEFAULT_VALUE = re.compile(r"^\W*(philippines|both sexes|total|all items|all|levels?)\W*$", re.I)


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


def _key(p: str) -> int:
    if "Q" in p:
        return int(p[:4]) * 4 + int(p[6]) - 1
    return int(p[:4]) * 12 + int(p[5:]) - 1


def unbroken_tail(points: list) -> list:
    """The points from the start of the last run with no missing period."""
    if not points:
        return points
    start = 0
    for i in range(1, len(points)):
        if _key(points[i][0]) - _key(points[i - 1][0]) != 1:
            start = i
    return points[start:]


# ---------------------------------------------------------------- PXWeb
_META: dict = {}


def px_meta(table: str) -> list:
    if table not in _META:
        time.sleep(PX_PAUSE)
        r = requests.get(PX + table, timeout=90, headers=UA)
        print(f"  [psa] meta {table} status={r.status_code}")
        r.raise_for_status()
        _META[table] = _json(r)["variables"]
    return _META[table]


def _json(r):
    """PSA's PXWeb replies start with a UTF-8 byte-order mark."""
    return json.loads(r.content.decode("utf-8-sig"))


def _clean(t: str) -> str:
    """'0 - ALL ITEMS' -> 'ALL ITEMS': PSA prefixes classification codes."""
    return re.sub(r"^\s*[\d.]+\s*-\s*", "", t)


def _is_time(v: dict) -> bool:
    return bool(v.get("time")) or bool(re.search(r"year|month|quarter|period", v.get("text", "") + v.get("code", ""), re.I))


def px_query(table: str, picks: dict) -> list:
    """picks: {variable regex: value regex}. Returns [[period, value], ...]."""
    vars_ = px_meta(table)
    query, texts = [], {}
    for v in vars_:
        codes, vt = v["values"], v.get("valueTexts", v["values"])
        texts[v["code"]] = dict(zip(codes, vt))
        rx = next((val for var, val in picks.items() if re.search(var, v["text"] + " " + v["code"], re.I)), None)
        if rx is not None:
            hit = [c for c, t in zip(codes, vt) if re.search(rx, _clean(t), re.I)]
        elif _is_time(v):
            continue
        else:
            hit = codes if len(codes) == 1 else [c for c, t in zip(codes, vt) if DEFAULT_VALUE.match(_clean(t))]
        if len(hit) != 1:
            raise ValueError(f"{table}: variable {v['text']!r} matched {len(hit)} values; values are {vt[:25]}")
        query.append({"code": v["code"], "selection": {"filter": "item", "values": hit}})
    time.sleep(PX_PAUSE)
    r = requests.post(PX + table, timeout=120, headers=UA,
                      json={"query": query, "response": {"format": "json"}})
    print(f"  [psa] data {table} status={r.status_code}")
    r.raise_for_status()
    j = _json(r)
    cols = [c["code"] for c in j["columns"] if c.get("type") != "c"]
    chosen = {q["code"] for q in query}  # period text comes only from the time variables
    out = {}
    for row in j["data"]:
        labels = [texts.get(c, {}).get(k, k) for c, k in zip(cols, row["key"]) if c not in chosen]
        per = _period(labels)
        try:
            val = float(str(row["values"][0]).replace(",", ""))
        except ValueError:
            continue
        if per:
            out[per] = val
    return sorted([[p, v] for p, v in out.items()], key=lambda x: _key(x[0]))


def _period(labels: list) -> str | None:
    """Year plus a month or quarter, from the row's time labels; None for
    annual rows (Annual / Average) and anything unrecognised."""
    s = " ".join(labels)
    y = re.search(r"\b(19|20)\d{2}\b", s)
    if not y:
        return None
    rest = s.replace(y.group(0), " ")
    q = re.search(r"\bQ([1-4])\b|\b([1-4])(?:st|nd|rd|th) quarter\b", rest, re.I)
    if q:
        return f"{y.group(0)}-Q{q.group(1) or q.group(2)}"
    for word in re.findall(r"[A-Za-z]+", rest):
        if word[:3].lower() in MONTHS:
            return f"{y.group(0)}-{MONTHS[word[:3].lower()]:02d}"
    return None


# ---------------------------------------------------------------- GDP
def fetch_gdp_level() -> list:
    pts = px_query(T_GDP_NSA, {r"item|expenditure|account|transaction": GDP_ITEM, r"price|valuation": r"current"})
    return require_current(pts, QUARTERLY_MAX_AGE, "PSA nominal GDP")


def fetch_gdp_real_nsa() -> list:
    return px_query(T_GDP_NSA, {r"item|expenditure|account|transaction": GDP_ITEM, r"price|valuation": r"constant"})


def fetch_gdp_real() -> list:
    pts = px_query(T_GDP_SA, {r"item|expenditure|account|transaction": GDP_ITEM})
    return require_current(pts, QUARTERLY_MAX_AGE, "PSA seasonally adjusted real GDP")


def fetch_gdp_growth() -> list:
    return require_current(pct_change(fetch_gdp_real(), 1), QUARTERLY_MAX_AGE, "PSA SA real GDP growth q/q")


def fetch_gdp_growth_yoy() -> list:
    return require_current(pct_change(fetch_gdp_real_nsa(), 4), QUARTERLY_MAX_AGE, "PSA real GDP, unadjusted, y/y")


# ---------------------------------------------------------------- CPI
CPI_PICKS = {r"geo|area|region": r"^\W*philippines\W*$", r"commodity|item": r"^\W*all items\W*$"}


def fetch_cpi() -> list:
    new = px_query(T_CPI_YOY, CPI_PICKS)
    ix_back, ix_new = px_query(T_CPI_INDEX_BACK, CPI_PICKS), px_query(T_CPI_INDEX, CPI_PICKS)
    if not (new and ix_back and ix_new):
        raise ValueError("PSA CPI: a table came back empty")
    if abs(ix_new[0][1] / ix_back[-1][1] - 1) > 0.05:
        raise ValueError(f"CPI index join {ix_back[-1]} -> {ix_new[0]} is not on one basis")
    derived = dict(pct_change(sorted(dict(ix_back + ix_new).items(), key=lambda x: _key(x[0])), 12))
    gaps = [(p, round(v - derived[p], 2)) for p, v in new if p in derived and abs(v - derived[p]) > 0.15]
    if gaps or not any(p in derived for p, _ in new):
        raise ValueError(f"CPI: the index does not reproduce PSA's published rate: {gaps[:3]}")
    first = new[0][0]
    old = sorted([[p, v] for p, v in derived.items() if p < first], key=lambda x: _key(x[0]))
    pts = old + [[p, round(v, 1)] for p, v in new]
    return require_current(unbroken_tail(pts), MONTHLY_MAX_AGE, "PSA CPI y/y")


def fetch_cpi_mom() -> list:
    ix = px_query(T_CPI_INDEX, CPI_PICKS)
    return require_current(pct_change(ix, 1), MONTHLY_MAX_AGE, "PSA CPI m/m")


# ---------------------------------------------------------------- labour
def fetch_labour() -> dict:
    out = {}
    for k, rx in (("unemployment", r"^\W*unemployment rate\W*$"), ("participation", r"labo[u]?r force participation"),
                  ("emp_rate", r"^\W*employment rate\W*$")):
        out[k] = unbroken_tail(px_query(T_LFS, {r"rate": rx, r"sex": r"^\W*both sexes\W*$"}))
    er = dict(out.pop("emp_rate"))
    out["employment"] = [[p, v * er[p] / 100] for p, v in out["participation"] if p in er]
    for k in out:
        out[k] = require_current([[p, round(v, 1)] for p, v in out[k]], MONTHLY_MAX_AGE, f"PSA LFS {k}")
    return out


# ---------------------------------------------------------------- trade
def fetch_trade() -> dict:
    """Exports FOB and imports CIF in peso million. The IMF's peso (XDC)
    figures for the Philippines stop in December 2022 (run 1, 12 Oct 2026),
    so the IMF's US dollar figures, which PSA itself headlines, are converted
    at the BIS monthly AVERAGE peso rate for the same month. All three end
    at the last month with both flows and a rate."""
    r = requests.get(ITG_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
    print(f"  [imf-itg] PHL status={r.status_code}")
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    rate = dict(p for p in bis_csv(BIS_FX_AVG_URL, "WS_XRU M.PH.PHP.A") if re.fullmatch(r"\d{4}-\d{2}", p[0]))
    out = {}
    for key, ind, val in (("exports", "XG", "FOB"), ("imports", "MG", "CIF")):
        pts = {}
        for row in rows:
            if (row.get("INDICATOR"), row.get("VALUATION"), row.get("UNIT")) != (ind, val, "USD"):
                continue
            per = (row.get("TIME_PERIOD") or "").replace("-M", "-")
            try:
                v = float(row.get("OBS_VALUE") or "")
            except ValueError:
                continue
            if re.fullmatch(r"\d{4}-\d{2}", per) and per in rate:
                pts[per] = round(v / 1e6 * rate[per], 1)
        out[key] = require_current(sorted([[p, v] for p, v in pts.items()]), MONTHLY_MAX_AGE, f"IMF {ind} (US$)")
    common = set(dict(out["exports"])) & set(dict(out["imports"]))
    out = {k: [p for p in v if p[0] in common] for k, v in out.items()}
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    if not out["trade_balance"]:
        raise ValueError("IMF trade: no month with both exports and imports")
    return out


# ---------------------------------------------------------------- others
def bis_csv(url: str, tag: str) -> list:
    r = requests.get(url, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] {tag} status={r.status_code}")
    r.raise_for_status()
    return sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                   for row in csv.DictReader(io.StringIO(r.text))
                   if row.get("OBS_VALUE") not in (None, "", "NaN")])


def fetch_policy_rate() -> list:
    pts = bis_csv(BIS_URL, "WS_CBPOL M.PH")
    pts = [p for p in pts if p[0] >= SERIES_START.get("policy_rate", "")]
    pts = bis_daily.extend(pts, "PH", "BSP policy rate")
    bad = [p for p in pts if not (0 <= p[1] < 30)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


def fetch_fx() -> tuple[list, str]:
    return fetch_worldbank("PA.NUS.FCRF"), "World Bank PA.NUS.FCRF annual average"


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
     "GDP, current prices, not seasonally adjusted (PSA quarterly national accounts, OpenSTAT)", "PHPm", "quarters"),
    ("gdp_real", fetch_gdp_real,
     "Real GDP, constant 2018 prices, seasonally adjusted (PSA seasonally adjusted national accounts, OpenSTAT)", "PHPm", "quarters"),
    ("gdp_growth", fetch_gdp_growth,
     "Real GDP growth, change on previous quarter, seasonally adjusted (PSA, OpenSTAT)", "%", "quarters"),
    ("gdp_growth_yoy", fetch_gdp_growth_yoy,
     "Real GDP growth, change on same quarter a year earlier, not seasonally adjusted (PSA quarterly national accounts; PSA's headline)", "%", "quarters"),
    ("cpi", fetch_cpi,
     "CPI, all income households, all items, change on same month a year earlier, 2018=100 (PSA, OpenSTAT)", "%", "months"),
    ("cpi_mom", fetch_cpi_mom,
     "CPI, all items, change on previous month, not seasonally adjusted, from PSA's all-items index (OpenSTAT)", "%", "months"),
    ("policy_rate", fetch_policy_rate,
     "BSP target reverse repurchase rate, end of month (BIS central bank policy rates, M.PH)", "%", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]
LABOUR_LABEL = {
    "unemployment": "Unemployment rate, not seasonally adjusted (PSA labour force survey, OpenSTAT)",
    "participation": "Labour force participation rate, not seasonally adjusted (PSA labour force survey, OpenSTAT)",
    "employment": "Employment-to-population ratio, not seasonally adjusted, computed from PSA's participation and employment rates (PSA labour force survey)",
}
TRADE_LABEL = {
    "exports": "Exports of goods, FOB, US$ converted to pesos at the BIS monthly average rate (IMF international trade in goods, from PSA)",
    "imports": "Imports of goods, CIF, US$ converted to pesos at the BIS monthly average rate (IMF international trade in goods, from PSA)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF, pesos (IMF ITG, converted at the BIS monthly average rate)",
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
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<20} {exc}")
        return None

    for key, fn, label, unit, freq in SERIES:
        pts = attempt(key, fn)
        if pts:
            put(out, key, pts, label, unit, freq)

    lab = attempt("labour", fetch_labour)
    if lab:
        for k, pts in lab.items():
            put(out, k, pts, LABOUR_LABEL[k], "%", "months")

    tr = attempt("trade", fetch_trade)
    if tr:
        for k, v in tr.items():
            put(out, k, v, TRADE_LABEL[k], "PHPm", "months")

    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}

    try:
        fx, src = fetch_fx()
        out["fx_to_usd"] = {"pair": "PHP/USD", "rate": fx[-1][1], "as_of": fx[-1][0],
                            "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} pesos per US$ ({fx[-1][0]}, {src}), history from {fx[0][0]}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

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
