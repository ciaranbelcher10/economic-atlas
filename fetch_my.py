"""Fetch Malaysia's economic series and write data-my.json.

Run:  FRED_API_KEY=yourkey python3 fetch_my.py
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Sources, chosen from tools/probe_country.py (6 Oct 2026). National first:
OpenDOSM (Department of Statistics Malaysia's open API) answers from outside
Malaysia, unlike China's statistics bureau, so the official figures are
taken from the publisher itself wherever it publishes them.

- gdp_level: OpenDOSM gdp_qtr_nominal, series "abs", RM million, quarterly,
  not seasonally adjusted. The page rolls four quarters into a year.
- gdp_real: OpenDOSM gdp_qtr_real, series "abs", constant prices, quarterly.
- gdp_growth_yoy: OpenDOSM gdp_qtr_real, "growth_yoy", as published.
- gdp_growth: real GDP change on the previous quarter, seasonally adjusted,
  computed from DOSM's seasonally adjusted real GDP levels (gdp_qtr_real_sa
  serves levels only). The "growth_qoq" in gdp_qtr_real is the unadjusted
  change (qoq_basis() proves it) and is only a labelled fallback.
- cpi / cpi_mom: DOSM's own published rates (cpi_headline_inflation) when
  served. Otherwise derived from DOSM's own all-items index, which is the
  index DOSM computes its rates from, so a derived rate should reproduce
  the official one; tools/audit_my.py checks that it does before launch.
  (China's month-on-month rate was dropped because rebuilding it from the
  IMF's rebased index did NOT reproduce the official figure. Different
  case: here the index is the publisher's own.)
- unemployment / participation: OpenDOSM lfs_month_sa (seasonally
  adjusted); employment (ep_ratio): lfs_month, not seasonally adjusted, as
  the adjusted table does not carry it. All from Jan 2011, after a survey
  re-basing in Dec 2010 (see LFS_START).
- exports / imports / trade_balance: OpenDOSM trade_sitc_1d, all sections,
  RM, monthly. Exports FOB, imports CIF, as DOSM reports them. Already in
  ringgit: no currency conversion.
- policy_rate: BIS central bank policy rates, M.MY, from May 2004 only,
  extended past BIS's last monthly value with BIS's daily series D.MY
  (bis_daily.py) when the two agree at the join.
  BIS splices three measures (3-month interbank rate 1995-97, 3-month
  intervention rate 1998 to 25 Apr 2004, overnight policy rate since 26 Apr
  2004); the series is cut at the first full OPR month so one measure is
  shown throughout.
- debt_gdp / deficit: IMF World Economic Outlook via imf_weo.py.
- current_account / fdi: World Bank, annual.
- fx_to_usd: FRED DEXMAUS (ringgit per US dollar, daily, reduced to month
  end), World Bank annual average only if FRED is unreachable.

Not served, on purpose: business_confidence (no OECD coverage for Malaysia;
DOSM's business tendency survey is a different measure) and
bond_yield_10y (the IMF's S13BOND series does not state its maturity, and
the site labels nothing 10-year that its source does not call 10-year).
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

import bis_daily
import imf_weo
import series_guard

ISO3 = "MYS"
OUT_FILE = "data-my.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}

DOSM = "https://api.data.gov.my/data-catalogue?id={id}"
DOSM_PAUSE = 16          # OpenDOSM throttles anonymous callers; one call per pause
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json&observation_start=1981-01-01")
WB_URL = "https://api.worldbank.org/v2/country/MYS/indicator/{code}?format=json&per_page=200"
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.MY?format=csv"
OPR_START = "2004-05"    # first full month of the overnight policy rate (from 26 Apr 2004)

MONTHLY_MAX_AGE = 120
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
    if not points:
        raise ValueError(f"{what}: no observations")
    end = _period_end(points[-1][0])
    if end and (datetime.now(timezone.utc) - end).days > max_days:
        raise ValueError(f"{what}: series ends {points[-1][0]}, too old to show as current")
    return points


def month_of(d: str) -> str:
    """'2026-08-01' -> '2026-08'."""
    return d[:7]


def quarter_of(d: str) -> str:
    """'2026-04-01' (first day of the quarter, as OpenDOSM dates them) -> '2026-Q2'."""
    y, m = int(d[:4]), int(d[5:7])
    if m not in (1, 4, 7, 10):
        raise ValueError(f"quarterly date {d} is not the first month of a quarter")
    return f"{y}-Q{(m - 1) // 3 + 1}"


_DOSM_CACHE: dict = {}
_DOSM_LAST = [0.0]


def dosm(dataset: str) -> list:
    """All rows of one OpenDOSM dataset (cached; throttled; one retry on 429)."""
    if dataset in _DOSM_CACHE:
        return _DOSM_CACHE[dataset]
    for attempt in (1, 2):
        wait = DOSM_PAUSE - (time.time() - _DOSM_LAST[0])
        if wait > 0:
            time.sleep(wait)
        r = requests.get(DOSM.format(id=dataset), timeout=90, headers=UA)
        _DOSM_LAST[0] = time.time()
        print(f"  [opendosm] {dataset} status={r.status_code}")
        if r.status_code == 429 and attempt == 1:
            time.sleep(60)
            continue
        r.raise_for_status()
        rows = r.json()
        if not isinstance(rows, list):
            raise ValueError(f"OpenDOSM {dataset}: expected a list of rows, got {type(rows).__name__}")
        _DOSM_CACHE[dataset] = rows
        return rows
    raise ValueError(f"OpenDOSM {dataset}: throttled twice")


def pts_from(rows: list, value: str, period=month_of, **want) -> list:
    out = {}
    for r in rows:
        if all(str(r.get(k)) == v for k, v in want.items()) and r.get(value) not in (None, ""):
            out[period(r["date"])] = float(r[value])
    return sorted([[p, v] for p, v in out.items()])


def pct_change(points: list, lag: int, dp: int = 1) -> list:
    out = []
    for i in range(lag, len(points)):
        a, b = points[i - lag][1], points[i][1]
        if a:
            out.append([points[i][0], round((b / a - 1) * 100, dp)])
    return out


# ---------------------------------------------------------------- GDP
def fetch_gdp_level() -> list:
    pts = pts_from(dosm("gdp_qtr_nominal"), "value", quarter_of, series="abs")
    return require_current(pts, QUARTERLY_MAX_AGE, "OpenDOSM nominal GDP")


def fetch_gdp_real() -> list:
    pts = pts_from(dosm("gdp_qtr_real"), "value", quarter_of, series="abs")
    return require_current(pts, QUARTERLY_MAX_AGE, "OpenDOSM real GDP")


def fetch_gdp_growth_yoy() -> list:
    pts = pts_from(dosm("gdp_qtr_real"), "value", quarter_of, series="growth_yoy")
    return require_current(pts, QUARTERLY_MAX_AGE, "OpenDOSM real GDP growth y/y")


def qoq_basis(published: list, level: list) -> str:
    """'nsa' if the published q/q growth is just the change in the raw level
    (so it is NOT seasonally adjusted), else 'sa'. Decided on the last 8
    quarters where both exist."""
    raw = dict(pct_change(level, 1))
    both = [(v, raw[p]) for p, v in published[-8:] if p in raw]
    if len(both) < 4:
        return "unknown"
    return "nsa" if all(abs(a - b) <= 0.15 for a, b in both) else "sa"


def fetch_gdp_growth() -> tuple[list, str]:
    """Quarter-on-quarter real growth, seasonally adjusted.

    OpenDOSM's gdp_qtr_real_sa serves DOSM's seasonally adjusted real GDP
    LEVELS ("abs") only. The q/q rate DOSM headlines is the change in those
    levels, so it is computed from them to DOSM's one decimal place; the
    audit checks the result against the levels and Ciaran's spot-check
    against DOSM's release. The "growth_qoq" in gdp_qtr_real is the change
    in the UNADJUSTED level (21.1% in 2020-Q3), so it is used only if the
    adjusted table disappears, and then labelled not seasonally adjusted."""
    try:
        rows = dosm("gdp_qtr_real_sa")
        pub = pts_from(rows, "value", quarter_of, series="growth_qoq")
        if pub:
            return require_current(pub, QUARTERLY_MAX_AGE, "OpenDOSM real GDP growth q/q SA"), "sa"
        lvl = pts_from(rows, "value", quarter_of, series="abs")
        if len(lvl) >= 8:
            return require_current(pct_change(lvl, 1), QUARTERLY_MAX_AGE, "OpenDOSM SA real GDP"), "sa_derived"
    except Exception as exc:
        print(f"  [opendosm] gdp_qtr_real_sa unavailable ({exc}); using gdp_qtr_real")
    pts = pts_from(dosm("gdp_qtr_real"), "value", quarter_of, series="growth_qoq")
    basis = qoq_basis(pts, fetch_gdp_real())
    return require_current(pts, QUARTERLY_MAX_AGE, "OpenDOSM real GDP growth q/q"), basis


# ---------------------------------------------------------------- CPI
def fetch_cpi_index() -> list:
    pts = pts_from(dosm("cpi_headline"), "index", division="overall")
    return require_current(pts, MONTHLY_MAX_AGE, "OpenDOSM CPI index")


def fetch_cpi_rates() -> tuple[list, list, str]:
    """(yoy, mom, how): DOSM's published rates if served, else derived from
    DOSM's own index to DOSM's one decimal place."""
    try:
        rows = dosm("cpi_headline_inflation")
        yoy = pts_from(rows, "inflation_yoy", division="overall")
        mom = pts_from(rows, "inflation_mom", division="overall")
        if yoy and mom:
            return (require_current(yoy, MONTHLY_MAX_AGE, "OpenDOSM CPI y/y"),
                    require_current(mom, MONTHLY_MAX_AGE, "OpenDOSM CPI m/m"), "published")
        print("  [opendosm] cpi_headline_inflation has no overall rates; deriving from the index")
    except Exception as exc:
        print(f"  [opendosm] cpi_headline_inflation unavailable ({exc}); deriving from the index")
    ix = fetch_cpi_index()
    return pct_change(ix, 12), pct_change(ix, 1), "derived"


# ---------------------------------------------------------------- labour
LFS_START = "2011-01"
# The monthly labour series open in 2010 with a break: participation jumps
# 2.9pp and the employment ratio 2.8pp in Dec 2010 alone, which is a
# re-basing of the survey, not a change in the labour market (tools/audit_my.py,
# Oct 2026). The series start after it, so one consistent basis is shown.


def fetch_labour() -> tuple[dict, dict]:
    """(series, basis per key). Unemployment and participation from DOSM's
    seasonally adjusted table; the employment-to-population ratio is not in
    that table, so it comes from the unadjusted one and is labelled so."""
    out, basis = {}, {}
    try:
        sa = dosm("lfs_month_sa")
        for k, f in (("unemployment", "u_rate"), ("participation", "p_rate")):
            pts = [p for p in pts_from(sa, f) if p[0] >= LFS_START]
            if pts:
                out[k], basis[k] = require_current(pts, MONTHLY_MAX_AGE, f"OpenDOSM lfs_month_sa {k}"), "sa"
    except Exception as exc:
        print(f"  [opendosm] lfs_month_sa unavailable ({exc})")
    nsa = dosm("lfs_month")
    for k, f in (("unemployment", "u_rate"), ("participation", "p_rate"), ("employment", "ep_ratio")):
        if k in out:
            continue
        pts = [p for p in pts_from(nsa, f) if p[0] >= LFS_START]
        if pts:
            out[k], basis[k] = require_current(pts, MONTHLY_MAX_AGE, f"OpenDOSM lfs_month {k}"), "nsa"
    if not out:
        raise ValueError("no OpenDOSM labour force dataset served")
    return out, basis


# ---------------------------------------------------------------- trade
def fetch_trade() -> dict:
    rows = dosm("trade_sitc_1d")
    out = {}
    for k in ("exports", "imports"):
        pts = pts_from(rows, k, section="overall")
        out[k] = require_current([[p, round(v / 1e6, 1)] for p, v in pts], MONTHLY_MAX_AGE, f"OpenDOSM {k}")
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    return out


# ---------------------------------------------------------------- others
def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.MY status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = [p for p in pts if p[0] >= OPR_START]
    pts = bis_daily.extend(pts, "MY", "OPR")
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "BIS policy rate")


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
        month_end[o["date"][:7]] = float(o["value"])
    return sorted([[p, v] for p, v in month_end.items()])


# ---------------------------------------------------------------- labels
QOQ_LABEL = {
    "sa": "Real GDP growth, change on previous quarter, seasonally adjusted (DOSM, OpenDOSM gdp_qtr_real_sa)",
    "sa_derived": "Real GDP growth, change on previous quarter, seasonally adjusted, from DOSM's seasonally adjusted real GDP (OpenDOSM gdp_qtr_real_sa)",
    "nsa": "Real GDP growth, change on previous quarter, not seasonally adjusted (DOSM, OpenDOSM gdp_qtr_real)",
}
LABOUR_LABEL = {
    ("unemployment", "sa"): "Unemployment rate, seasonally adjusted (DOSM labour force survey, OpenDOSM lfs_month_sa)",
    ("unemployment", "nsa"): "Unemployment rate, not seasonally adjusted (DOSM labour force survey, OpenDOSM lfs_month)",
    ("participation", "sa"): "Labour force participation rate, seasonally adjusted (DOSM, OpenDOSM lfs_month_sa)",
    ("participation", "nsa"): "Labour force participation rate, not seasonally adjusted (DOSM, OpenDOSM lfs_month)",
    ("employment", "sa"): "Employment-to-population ratio, seasonally adjusted (DOSM, OpenDOSM lfs_month_sa)",
    ("employment", "nsa"): "Employment-to-population ratio, not seasonally adjusted (DOSM, OpenDOSM lfs_month)",
}
CPI_LABEL = {
    ("cpi", "published"): "CPI, all items, YoY, as published (DOSM, OpenDOSM cpi_headline_inflation)",
    ("cpi_mom", "published"): "CPI, all items, MoM, as published (DOSM, OpenDOSM cpi_headline_inflation)",
    ("cpi", "derived"): "CPI, all items, YoY, from DOSM's all-items index (OpenDOSM cpi_headline)",
    ("cpi_mom", "derived"): "CPI, all items, MoM, from DOSM's all-items index (OpenDOSM cpi_headline)",
}
TRADE_LABELS = {
    "exports": "Exports of goods, FOB (DOSM external trade, OpenDOSM trade_sitc_1d)",
    "imports": "Imports of goods, CIF (DOSM external trade, OpenDOSM trade_sitc_1d)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF (DOSM external trade)",
}
SERIES = [
    ("gdp_level", fetch_gdp_level, "GDP, current prices, not seasonally adjusted (DOSM, OpenDOSM gdp_qtr_nominal)",
     "MYRm", "quarters"),
    ("gdp_real", fetch_gdp_real, "Real GDP, constant prices (DOSM, OpenDOSM gdp_qtr_real)", "MYRm", "quarters"),
    ("gdp_growth_yoy", fetch_gdp_growth_yoy,
     "Real GDP growth, change on same quarter a year earlier (DOSM, OpenDOSM gdp_qtr_real)", "%", "quarters"),
    ("policy_rate", fetch_policy_rate,
     "Overnight policy rate (BIS central bank policy rates, M.MY, from May 2004)", "%", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT),
     "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT),
     "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
    ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
     "Current account balance, % of GDP (World Bank)", "%", "years"),
    ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"), "FDI net inflows, % of GDP (World Bank)", "%", "years"),
]


def put(out, key, pts, label, unit, freq):
    out["series"][key] = {"label": label, "unit": unit, "freq": freq, "points": pts}
    print(f"  ok  {key:<20} {len(pts):>5} observations ({pts[0][0]} to {pts[-1][0]}, {freq})")


def main() -> int:
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sample": False, "series": {}}
    failures = []

    for key, fn, label, unit, freq in SERIES:
        try:
            pts = fn()
            if not pts:
                raise ValueError("no usable response")
            put(out, key, pts, label, unit, freq)
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<20} {exc}")

    try:
        pts, basis = fetch_gdp_growth()
        if basis not in QOQ_LABEL:
            raise ValueError("could not tell whether q/q growth is seasonally adjusted; left out")
        put(out, "gdp_growth", pts, QOQ_LABEL[basis], "%", "quarters")
    except Exception as exc:
        failures.append("gdp_growth")
        print(f"FAIL  gdp_growth           {exc}")

    try:
        yoy, mom, how = fetch_cpi_rates()
        put(out, "cpi", yoy, CPI_LABEL[("cpi", how)], "%", "months")
        put(out, "cpi_mom", mom, CPI_LABEL[("cpi_mom", how)], "%", "months")
    except Exception as exc:
        failures += ["cpi", "cpi_mom"]
        print(f"FAIL  cpi                  {exc}")

    try:
        lab, basis = fetch_labour()
        for k, pts in lab.items():
            put(out, k, pts, LABOUR_LABEL[(k, basis[k])], "%", "months")
    except Exception as exc:
        failures += ["unemployment", "participation", "employment"]
        print(f"FAIL  labour               {exc}")

    try:
        for k, pts in fetch_trade().items():
            put(out, k, pts, TRADE_LABELS[k], "MYRm", "months")
    except Exception as exc:
        failures += ["exports", "imports", "trade_balance"]
        print(f"FAIL  trade                {exc}")

    try:
        with open(OUT_FILE) as f:
            prev_full = json.load(f)
    except Exception:
        prev_full = {}
    prev_series = prev_full.get("series", {})

    key = os.environ.get("FRED_API_KEY")
    try:
        fx = fetch_fred("DEXMAUS", key) if key else []
        src = "FRED DEXMAUS"
        if not fx:
            fx, src = fetch_worldbank("PA.NUS.FCRF"), "World Bank annual average"
        out["fx_to_usd"] = {"pair": "MYR/USD", "rate": fx[-1][1], "as_of": fx[-1][0],
                            "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} ({fx[-1][0]}, {src}), history from {fx[0][0]}")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")

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
