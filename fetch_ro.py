"""Fetch Romania's economic series and write data-ro.json.

Run:  FRED_API_KEY=yourkey python3 fetch_ro.py
In GitHub Actions the key comes from the FRED_API_KEY repository secret.

Built v1.7.34 (step 3, before the probe) from fetch_cz.py (Czechia). Romania
is an EU member outside the euro area and outside the OECD: own currency (leu,
RON; redenominated in July 2005, 10,000 old lei = 1 new leu), own central bank
(National Bank of Romania, NBR), statistics office INS. Every currency figure
on the page is in lei.
Probed 9 Oct 2026 (probe_ro.txt); the real run and audit come next.

Sources, one per site key:
- gdp_level / gdp_real: Eurostat namq_10_gdp in national currency (CP_MNAC,
  CLV20_MNAC), SA; FRED CPMNACSCAB1GQRO / CLVMNACSCAB1GQRO fallback only.
- gdp_growth: derived q/q from the real series.
- unemployment: Eurostat une_rt_m, SA.
- cpi / cpi_mom: HICP (CP0000ROM086NEST), the EU-page rule. Romania's HICP
  and INS's national CPI differ by more than in most EU countries (weights).
- cpi_national: INS's national CPI via the IMF CPI dataset (YOY_PCH_PA_PT).
- policy_rate: NBR monetary policy rate, BIS WS_CBPOL M.RO, extended with BIS
  daily.
- bond_yield_10y: ECB IRS (convergence long-term rate) via ecb_irs.py.
- exports / imports / trade_balance: Eurostat ext_st_27_2020msbec, world
  partner, converted from euro to lei at each month's ECB reference rate
  (EXR M.RON.EUR.SP00.A). Romania runs a goods deficit every month.
- debt_gdp / deficit: Eurostat gov_10dd_edpt1, geo=RO (under the EU's
  excessive deficit procedure since 2020).
- fdi / current_account: World Bank, % of GDP.
- fx_to_usd: World Bank PA.NUS.FCRF, lei per US$, annual.
Probe of 9 Oct 2026: the OECD carries Romania's business confidence (BCICP,
served) and HICP but not its national CPI, so cpi_national comes from the IMF
CPI dataset (INS's index). No OECD or FRED 15-64 participation or employment
rates (not served). FRED has no 10-year yield for Romania; the ECB IRS
series is the only source.
"""

from __future__ import annotations

import csv
import io
import re
import oecd_turn
import json
import os
import sys
from datetime import datetime, timezone

import requests
import series_guard
import bis_daily
import ecb_exr
import ecb_irs
import eurostat_gdp
import eurostat_unemp
import inflation_sources

ALLOW_SHRINK = {}

# key: (fred_id, freq 'm'|'q'|'a', label, unit, transform None|'yoy'|'mom'|'qoq', scale)
FRED_SERIES = {
    "gdp_level": ("CPMNACSCAB1GQRO", "q", "Nominal GDP, current prices, SCA (Eurostat)", "RONm", None, 1.0),
    "gdp_real": ("CLVMNACSCAB1GQRO", "q", "Real GDP, chain-linked volumes, SCA (Eurostat)", "RONm", None, 1.0),
    "unemployment": ("LRHUTTTTROM156S", "m", "Unemployment rate, 15+, SA (OECD harmonized)", "%", None, 1.0),
    "bond_yield_10y": ("IRLTLT01ROM156N", "m", "10-year government bond yield", "%", None, 1.0),
}
HICP_ID = "CP0000ROM086NEST"

# Series served only from a given month. The National Bank of Romania adopted
# inflation targeting in August 2005, a month after the leu was redenominated
# (10,000 old lei = 1 new leu). 2005-08 is PROVISIONAL: confirm against the BIS
# WS_CBPOL M.RO series start and break note in the probe before the real run.
SERIES_START = {"policy_rate": "2005-08",
                # Inflation from 2002 (audit of 9 Oct 2026): 1997-2001 ran from
                # 40% to above 150% a year after price liberalisation, with
                # monthly swings of up to 58 points in the annual rate; that
                # history would flatten every later movement on the chart.
                "cpi": "2002-01", "cpi_mom": "2002-01", "cpi_national": "2002-01",
                # GDP from 2000 (audit 9 Oct 2026): Eurostat's 1995-99 quarterly
                # series swings implausibly (1996-Q1 +12.1% q/q between -5.3%
                # and -0.5%). Unemployment from January 2009: Eurostat's monthly
                # Romanian series steps by -1.6 points in February 2004 and +2.1
                # in January 2009, a month each, which reads as series splices
                # rather than labour-market moves.
                "gdp_level": "2000-Q1", "gdp_real": "2000-Q1", "gdp_growth": "2000-Q1",
                "unemployment": "2009-01"}

BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.RO?format=csv"
WB_URL = "https://api.worldbank.org/v2/country/ROU/indicator/{code}?format=json&per_page=200"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}

FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json"
            "&observation_start=1970-01-01")


def _period_back_n(per, n: int):
    """The period label n periods earlier, in the period's own unit."""
    s = str(per)
    if re.fullmatch(r"\d{4}-\d{2}", s):
        t = int(s[:4]) * 12 + (int(s[5:]) - 1) - n
        return "{}-{:02d}".format(t // 12, t % 12 + 1)
    if re.fullmatch(r"\d{4}-Q[1-4]", s):
        t = int(s[:4]) * 4 + (int(s[6]) - 1) - n
        return "{}-Q{}".format(t // 4, t % 4 + 1)
    if re.fullmatch(r"\d{4}", s):
        return str(int(s) - n)
    return None


def fred_period(date: str, freq: str) -> str:
    y, m = date[:4], int(date[5:7])
    if freq == "a":
        return y
    if freq == "q":
        return f"{y}-Q{(m - 1) // 3 + 1}"
    return f"{y}-{m:02d}"


def fetch_fred(sid: str, freq: str, key: str) -> list:
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    points = []
    for o in r.json().get("observations", []):
        if o.get("value") in (None, "", "."):
            continue
        try:
            points.append([fred_period(o["date"], freq), float(o["value"])])
        except (KeyError, ValueError):
            continue
    dedup = {}
    for p, v in sorted(points, key=lambda x: x[0]):
        dedup[p] = v
    return sorted([[p, v] for p, v in dedup.items()], key=lambda x: x[0])


def gdp_growth_from_level(points: list) -> list:
    """Period-on-period growth, matched by period rather than list position."""
    by_period = {p[0]: p[1] for p in points}
    out = []
    for per, val in points:
        prev = _period_back_n(per, 1)
        base = by_period.get(prev) if prev else None
        if base:
            out.append([per, round((val / base - 1) * 100, 4)])
    return out


EUROSTAT_STATS_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _parse_jsonstat(text: str, tag: str) -> list | None:
    data = json.loads(text)
    if "dimension" not in data or "time" not in data.get("dimension", {}):
        print(f"  [{tag}] response has no time dimension; top-level keys: {list(data.keys())}")
        return None
    for dname, dim in data["dimension"].items():
        if dname == "time" or not isinstance(dim, dict):
            continue
        idx = dim.get("category", {}).get("index", {})
        if isinstance(idx, dict) and len(idx) > 1:
            print(f"  [{tag}] dimension {dname!r} has {len(idx)} categories "
                  f"({list(idx)[:5]}...) -- query is under-filtered, refusing "
                  f"to parse a multi-series response")
            return None
    time_index = data["dimension"]["time"]["category"]["index"]
    pos_to_period = {v: k for k, v in time_index.items()}
    value = data.get("value")
    points = {}
    if isinstance(value, dict):
        for pos_str, val in value.items():
            try:
                pos = int(pos_str)
            except ValueError:
                continue
            if pos in pos_to_period and val is not None:
                points[pos_to_period[pos]] = float(val)
    elif isinstance(value, list):
        for pos, val in enumerate(value):
            if val is not None and pos in pos_to_period:
                points[pos_to_period[pos]] = float(val)
    if not points:
        print(f"  [{tag}] parsed JSON-stat but got 0 points")
        return None
    pts = sorted([[p, v] for p, v in points.items()], key=lambda x: x[0])
    print(f"  [{tag}] SUCCESS: {len(pts)} points, {pts[0][0]} to {pts[-1][0]}")
    return pts


def _eurostat(url: str, tag: str) -> list | None:
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [{tag}] status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [{tag}] request failed: {exc}")
        return None
    try:
        return _parse_jsonstat(r.text, tag)
    except Exception as exc:
        print(f"  [{tag}] parsing failed: {exc}; first 300 chars: {r.text[:300]!r}")
        return None


def fetch_eurostat_govfinance(na_item: str) -> list | None:
    return _eurostat(f"{EUROSTAT_STATS_BASE}/gov_10dd_edpt1?format=JSON&lang=EN"
                     f"&geo=RO&sector=S13&unit=PC_GDP&na_item={na_item}&sinceTimePeriod=2000",
                     f"eurostat-gov-{na_item}-RO")


def fetch_eurostat_trade_world(stk_flow: str) -> list | None:
    """Romania's monthly world-partner goods trade, one flow, euro millions
    (Eurostat EXT_ST_27_2020MSBEC, the dataset every EU page uses)."""
    return _eurostat(f"{EUROSTAT_STATS_BASE}/ext_st_27_2020msbec?format=JSON&lang=EN"
                     f"&geo=RO&partner=WORLD&indic_et=TRD_VAL&bclas_bec=TOTAL"
                     f"&stk_flow={stk_flow}&sinceTimePeriod=2015",
                     f"eurostat-trade-world-{stk_flow}-RO")


def fetch_trade() -> dict:
    """exports, imports and trade_balance in leu millions, each month
    converted at that month's ECB reference rate. Raises if anything is
    missing: a balance from one flow, or at a borrowed rate, would be wrong."""
    exp = fetch_eurostat_trade_world("EXP")
    imp = fetch_eurostat_trade_world("IMP")
    if not exp or not imp:
        raise ValueError("Eurostat returned no exports or no imports")
    rates = ecb_exr.fetch_monthly("RON")
    if not rates:
        raise ValueError("no ECB leu reference rates to convert with")
    ex = ecb_exr.to_national(exp, rates)
    im = ecb_exr.to_national(imp, rates)
    im_by = dict(im)
    bal = [[p, round(v - im_by[p], 1)] for p, v in ex if p in im_by]
    if not (ex and im and bal):
        raise ValueError("no months with both flows and a reference rate")
    note = "Eurostat, world partner, converted from euro at each month's ECB reference rate"
    return {
        "exports": {"label": f"Exports, goods ({note})", "unit": "RONm", "freq": "months", "points": ex},
        "imports": {"label": f"Imports, goods ({note})", "unit": "RONm", "freq": "months", "points": im},
        "trade_balance": {"label": f"Trade balance, goods ({note}, exports less imports)",
                          "unit": "RONm", "freq": "months", "points": bal},
    }


def align_trade(series: dict) -> None:
    """Exports, imports and the balance all end at the last month both are
    published, so the Trade tiles describe the same month (as China, New
    Zealand). Runs after series_guard so a trimmed month is not read as a shrink."""
    ex, im = series.get("exports"), series.get("imports")
    if not (ex and im):
        return
    common = set(dict(ex["points"])) & set(dict(im["points"]))
    for k in ("exports", "imports", "trade_balance"):
        s = series.get(k)
        if s:
            kept = [p for p in s["points"] if p[0] in common]
            if len(kept) != len(s["points"]) and kept:
                print(f"  note {k:<20} ends at {kept[-1][0]}, the last month with both exports and imports")
            s["points"] = kept


OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/ROU.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/ROU.M.BCICP......?format=csvfile&startPeriod=1990",
]


def fetch_oecd_bci() -> list | None:
    oecd_turn.check()  # rotate OECD requests across groups; see oecd_turn.py
    for url in OECD_QUERIES:
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
            print(f"  [oecd-bci] status={r.status_code}")
            r.raise_for_status()
        except Exception as exc:
            print(f"  [oecd-bci] request failed: {exc}")
            continue
        rows = {}
        for row in csv.DictReader(io.StringIO(r.text)):
            low = {k.upper(): (v or "") for k, v in row.items() if k}
            if low.get("REF_AREA", "ROU") != "ROU" or low.get("MEASURE", "BCICP") != "BCICP":
                continue
            if (low.get("FREQ") or "M") != "M":
                continue
            period, value = low.get("TIME_PERIOD", ""), low.get("OBS_VALUE", "")
            if period and value:
                try:
                    rows[period] = float(value)
                except ValueError:
                    continue
        if rows:
            return sorted([[p, v] for p, v in rows.items()], key=lambda x: x[0])
        print("  [oecd-bci] 0 matching rows after filtering")
    return None


def fetch_policy_rate() -> list:
    r = requests.get(BIS_URL, timeout=60, headers=dict(UA, Accept="text/csv"))
    print(f"  [bis] WS_CBPOL M.RO status={r.status_code}")
    r.raise_for_status()
    pts = sorted([[row["TIME_PERIOD"], float(row["OBS_VALUE"])]
                  for row in csv.DictReader(io.StringIO(r.text))
                  if row.get("OBS_VALUE") not in (None, "", "NaN")])
    pts = bis_daily.extend(pts, "RO", "NBR monetary policy rate")
    pts = [p for p in pts if p[0] >= SERIES_START["policy_rate"]]
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"BIS policy rate: implausible value {bad[0]}")
    if not pts:
        raise ValueError("BIS policy rate: no observations from 2005-08")
    return pts


IMF_CPI_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/CPI/~/ROU.*.*.*.M"
               "?c[TIME_PERIOD]=ge:1996-M01")


def fetch_imf_national_cpi(get=None) -> dict | None:
    """INS's national CPI, annual rate, from the IMF CPI dataset (INDEX_TYPE CPI,
    all items, YOY_PCH_PA_PT). The OECD prices system carries only Romania's
    HICP (probe 9 Oct 2026), so the national CPI comes from the IMF, which
    takes it from INS. Refused if short or stale."""
    get = get or requests.get
    try:
        r = get(IMF_CPI_URL, timeout=90, headers=dict(UA, Accept="text/csv"))
        print(f"  [imf-cpi] ROU status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [imf-cpi] ROU failed: {exc}")
        return None
    pts = {}
    for row in csv.DictReader(io.StringIO(r.text)):
        if (row.get("INDEX_TYPE"), row.get("COICOP_1999"), row.get("TYPE_OF_TRANSFORMATION")) != ("CPI", "_T", "YOY_PCH_PA_PT"):
            continue
        per, val = (row.get("TIME_PERIOD") or "").replace("-M", "-"), row.get("OBS_VALUE")
        if re.fullmatch(r"\d{4}-\d{2}", per) and val not in (None, ""):
            pts[per] = round(float(val), 4)
    out = sorted([[p, v] for p, v in pts.items()])
    now = datetime.now(timezone.utc)
    if len(out) < 24:
        print(f"  [imf-cpi] ROU rejected: {len(out)} months")
        return None
    lag = (now.year * 12 + now.month) - (int(out[-1][0][:4]) * 12 + int(out[-1][0][5:]))
    if lag > 5:
        print(f"  [imf-cpi] ROU rejected stale: ends {out[-1][0]}")
        return None
    print(f"  [imf-cpi] ROU ok: {len(out)} months, {out[0][0]} to {out[-1][0]}")
    return {"label": "CPI, national definition, all items, YoY (IMF CPI dataset, from INS)",
            "unit": "%", "freq": "months", "points": out}


# World Bank PA.NUS.FCRF for Romania runs from 1960 in new lei (back-converted
# from the old leu: values below 0.01 before 1990). Served from 1995, the
# first year of the GDP series it converts.
FX_START = "1995"


def fetch_worldbank(code: str) -> list | None:
    r = requests.get(WB_URL.format(code=code), timeout=60, headers=UA)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    pts = []
    for row in payload[1]:
        try:
            if row.get("value") is not None:
                pts.append([str(row["date"]), float(row["value"])])
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(pts) or None


def main() -> int:
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": False,
        "series": {},
    }
    failures = []

    # Direct sources first; FRED copies only if these fail.
    es_gdp = eurostat_gdp.fetch_levels("RO", "MNAC", "RONm")
    out["series"].update(es_gdp)
    es_unemp = eurostat_unemp.fetch("RO")
    out["series"].update(es_unemp)
    ecb_yield = ecb_irs.fetch("RO", "RON")
    out["series"].update(ecb_yield)
    direct = {**es_gdp, **es_unemp, **ecb_yield}

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("WARN  no FRED_API_KEY set; FRED series will be skipped.")
    else:
        for name, (sid, freq, label, unit, tf, scale) in FRED_SERIES.items():
            if name in direct:
                continue
            try:
                points = fetch_fred(sid, freq, key)
                if not points:
                    raise ValueError("no observations")
                fr = {"m": "months", "q": "quarters", "a": "years"}[freq]
                out["series"][name] = {"label": f"{label} ({sid})", "unit": unit,
                                       "freq": fr, "points": points}
                print(f"  ok  {name:<16} {len(points):>5} observations "
                      f"({points[0][0]} to {points[-1][0]}, {fr})")
            except Exception as exc:
                failures.append(name)
                print(f"FAIL  {name:<16} {exc}")

    if "gdp_real" in out["series"]:
        growth = gdp_growth_from_level(out["series"]["gdp_real"]["points"])
        if growth:
            out["series"]["gdp_growth"] = {
                "label": f"Real GDP growth, QoQ, SCA (derived from {eurostat_gdp.source_tag(out['series']['gdp_real'])})",
                "unit": "%", "freq": "quarters", "points": growth}
            print(f"  ok  gdp_growth       {len(growth):>5} observations (derived)")

    # Inflation: HICP under cpi (the EU rule), CZSO's national CPI beside it.
    _hicp = inflation_sources.fetch_hicp(fetch_fred, "CP0000ROM086NEST", key)
    if _hicp:
        out["series"]["cpi"] = _hicp
    else:
        failures.append("cpi")
    _hicp_mom = inflation_sources.fetch_hicp_mom(fetch_fred, "CP0000ROM086NEST", key)
    if _hicp_mom:
        out["series"]["cpi_mom"] = _hicp_mom
    else:
        failures.append("cpi_mom")
    _cpi_national = fetch_imf_national_cpi()
    if _cpi_national:
        out["series"]["cpi_national"] = _cpi_national
    else:
        failures.append("cpi_national")

    try:
        trade = fetch_trade()
        out["series"].update(trade)
        for k, v in trade.items():
            print(f"  ok  {k:<16} {len(v['points']):>5} observations "
                  f"({v['points'][0][0]} to {v['points'][-1][0]}, months, leu)")
    except Exception as exc:
        failures += ["exports", "imports", "trade_balance"]
        print(f"FAIL  trade            {exc}")

    extras = [
        ("business_confidence", fetch_oecd_bci,
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index", "months"),
        ("policy_rate", fetch_policy_rate,
         "NBR monetary policy rate, end of month (BIS WS_CBPOL M.RO)", "%", "months"),
        ("debt_gdp", lambda: fetch_eurostat_govfinance("GD"),
         "General government gross debt, % of GDP (Eurostat)", "%", "years"),
        ("deficit", lambda: fetch_eurostat_govfinance("B9"),
         "General government net lending/borrowing, % of GDP (Eurostat)", "%", "years"),
        ("fdi", lambda: fetch_worldbank("BX.KLT.DINV.WD.GD.ZS"),
         "Foreign direct investment, net inflows, % of GDP (World Bank BX.KLT.DINV.WD.GD.ZS)", "%", "years"),
        ("current_account", lambda: fetch_worldbank("BN.CAB.XOKA.GD.ZS"),
         "Current account balance, % of GDP (World Bank BN.CAB.XOKA.GD.ZS)", "%", "years"),
    ]
    for name, fn, label, unit, fr in extras:
        try:
            points = fn()
            if not points:
                raise ValueError("no usable response")
            out["series"][name] = {"label": label, "unit": unit, "freq": fr, "points": points}
            print(f"  ok  {name:<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, {fr})")
        except Exception as exc:
            failures.append(name)
            print(f"FAIL  {name:<16} {exc}")

    # fx_to_usd: leu per US$, annual average (World Bank PA.NUS.FCRF), as
    # Poland. Used by Dollarise and the exchange-rate tiles (fx_config ANNUAL).
    try:
        fx_pts = fetch_worldbank("PA.NUS.FCRF")
        fx_pts = [p for p in (fx_pts or []) if p[0] >= FX_START] or None
        if fx_pts:
            fx_period, fx_rate = fx_pts[-1]
            out["fx_to_usd"] = {"pair": "RON/USD", "rate": fx_rate, "as_of": fx_period,
                                "direction": "divide", "history": fx_pts}
            print(f"  ok  fx_to_usd        1 observation ({fx_period}, {fx_rate}), "
                  f"history {fx_pts[0][0]} to {fx_period} ({len(fx_pts)} points, annual)")
        else:
            print("note  fx_to_usd: no observations returned")
    except Exception as exc:
        print(f"FAIL  fx_to_usd        {exc}")

    try:
        with open("data-ro.json") as f:
            _prev_for_merge = json.load(f)
    except Exception:
        _prev_for_merge = {}
    for _k, _start in SERIES_START.items():
        if _k != "policy_rate" and _k in out["series"]:
            out["series"][_k]["points"] = [p for p in out["series"][_k]["points"] if p[0] >= _start]
    series_guard.apply_guard(out["series"], _prev_for_merge.get("series", {}),
                             allow_shrink=ALLOW_SHRINK)
    align_trade(out["series"])
    if not out.get("fx_to_usd") and _prev_for_merge.get("fx_to_usd"):
        out["fx_to_usd"] = _prev_for_merge["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")

    if not out["series"]:
        print("\nNothing fetched.")
        return 1

    prev_meta = _prev_for_merge.get("new_points_meta")
    migrating = prev_meta is None
    backdate = _prev_for_merge.get("updated")
    prev_meta = prev_meta or {}
    now_iso = out["updated"]
    new_meta = {}
    for k, v in out["series"].items():
        if not v.get("points"):
            continue
        period = v["points"][-1][0]
        prior = prev_meta.get(k)
        if prior and prior.get("period") == period:
            new_meta[k] = {"period": period, "first_seen": prior["first_seen"]}
        elif migrating and backdate:
            new_meta[k] = {"period": period, "first_seen": backdate}
        else:
            new_meta[k] = {"period": period, "first_seen": now_iso}
    out["new_points_meta"] = new_meta

    def _age_days(iso):
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - t).total_seconds() / 86400
        except Exception:
            return 999

    out["new_points"] = {k: m["period"] for k, m in new_meta.items() if _age_days(m["first_seen"]) < 2}
    if out["new_points"]:
        print("Fresh (< 2 days old): " + ", ".join(f"{k} ({p})" for k, p in out["new_points"].items()))

    with open("data-ro.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data-ro.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)}; the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
