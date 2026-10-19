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
- exports / imports / trade_balance (v1.8.19): Statistics Iceland's own
  external trade table UTA06001 (PxWeb: exports FOB total, imports CIF
  total, balance of trade; krónur, monthly, from January 2011, published
  about a month after the reference month). Before 2011 Statistics Iceland's
  monthly goods tables carry no export or import levels, so January 2006 to
  December 2010 stays on the IMF international trade in goods (ITG), US
  dollars converted to krónur at the BIS monthly average rate (WS_XRU
  M.IS.ISK.A). The two parts join at January 2011 and the label says so.
  Why the issuer: the IMF mirror ran four months behind, dropped three real
  months (2013-03, 2013-04, 2026-01: imports and exports differ at source by
  a few krónur million) as "copied figures", and sat 3 to 19% off the
  issuer in some months (June 2021 imports). Probe of 19 Oct 2026 over 182
  overlapping months: exports 1.1% mean absolute gap, imports 0.3%. The
  splice is refused if the IMF-derived krónur differ from the issuer by
  more than SPLICE_MAX_MEAN_GAP on average (a unit or definition slip).
  The OECD trade dataflow does not answer for Iceland.
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
import itertools
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
ALLOW_SHRINK = {}   # v1.8.19: nothing may shrink; the three months once left out as "copied" are now served

QNA_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
           "Q..ISL..........?format=csvfile&startPeriod=1995-Q1")
LFS_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_LFS@DF_IALFS_UNE_M,1.0/"
           "ISL.UNE_LF_M.._Z.Y._T.Y_GE15..M?format=csvfile")
BIS_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/M.IS?format=csv"
BIS_FX_AVG_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_XRU/1.0/M.IS.ISK.A?format=csv"
ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "ISL.*.*.M?c[TIME_PERIOD]=ge:1995-M01")
WB_URL = "https://api.worldbank.org/v2/country/ISL/indicator/{code}?format=json&per_page=200"
PX_TRADE_URL = ("https://px.hagstofa.is/pxen/api/v1/en/Efnahagur/utanrikisverslun/"
                "1_voruvidskipti/01_voruskipti/UTA06001.px")
# row code and the exact text it must carry (a changed table fails loudly instead of serving the wrong row)
PX_ROWS = {"exports": ("XFRETTVx0", "Exports fob, total"),
           "imports": ("MNFLKM0", "Imports cif, total"),
           "balance": ("M_X_00", "Balance of trade")}
SI_START = "2011-01"          # first month of UTA06001; the IMF-derived months stop the month before
SPLICE_MAX_MEAN_GAP = 5.0     # % mean absolute gap, IMF-derived krónur vs the issuer (observed 1.1 exports, 0.3 imports)
BALANCE_TOLERANCE = 0.25      # ISK million: exports - imports vs the table's own balance (observed 0.1)
KEY_RATE_START = "2014-06"   # first full month of the term deposit rate (from 21 May 2014)
OECD_PAUSE = 2

MONTHLY_MAX_AGE = 120
QUARTERLY_MAX_AGE = 230
TRADE_MAX_AGE = 200       # probe, 19 Oct 2026: UTA06001 to Sep 2026 (the IMF mirror stopped at May 2026)


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
    # v1.8.1: as v1.8.0 did for NZ/SA, raise NotThisHour so an off-turn hour logs SKIP,
    # not "FAIL cpi  OECD CPI index: none".
    oecd_turn.check()
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


def _px_codes(dim: dict) -> list:
    idx = dim["category"]["index"]
    if isinstance(idx, dict):
        return [c for c, _ in sorted(idx.items(), key=lambda kv: kv[1])]
    return list(idx)


def parse_px(js: dict, prod_id: str, time_id: str) -> dict:
    """json-stat2 reply -> {row code: {"YYYY-MM": value}}; empty cells are skipped."""
    ids, sizes = js["id"], js["size"]
    cats = [_px_codes(js["dimension"][i]) for i in ids]
    if [len(c) for c in cats] != list(sizes) or len(js["value"]) != len(list(itertools.product(*cats))):
        raise ValueError("Statistics Iceland reply: dimension sizes do not match the value list")
    ip, it = ids.index(prod_id), ids.index(time_id)
    out: dict = {}
    for combo, v in zip(itertools.product(*cats), js["value"]):
        if v is None:
            continue
        m = re.fullmatch(r"(\d{4})M(\d{2})", combo[it])
        if not m:
            raise ValueError(f"Statistics Iceland reply: unexpected month code {combo[it]!r}")
        out.setdefault(combo[ip], {})[f"{m.group(1)}-{m.group(2)}"] = float(v)
    return out


def fetch_trade_si() -> dict:
    """Statistics Iceland UTA06001, krónur million: exports FOB, imports CIF, balance, monthly."""
    r = requests.get(PX_TRADE_URL, timeout=60, headers=UA)
    print(f"  [statice] UTA06001 layout status={r.status_code}")
    r.raise_for_status()
    meta = r.json()
    tv = [v for v in meta["variables"] if v.get("time")]
    pv = [v for v in meta["variables"] if not v.get("time")]
    if len(tv) != 1 or len(pv) != 1:
        raise ValueError("UTA06001 layout changed: expected one product and one month variable")
    tv, pv = tv[0], pv[0]
    texts = dict(zip(pv["values"], pv["valueTexts"]))
    for key, (code, text) in PX_ROWS.items():
        if texts.get(code, "").strip().lower() != text.lower():
            raise ValueError(f"UTA06001 row {code} reads {texts.get(code)!r}, expected {text!r}")
    query = [{"code": pv["code"], "selection": {"filter": "item", "values": [c for c, _ in PX_ROWS.values()]}},
             {"code": tv["code"], "selection": {"filter": "item", "values": tv["values"]}}]
    r = requests.post(PX_TRADE_URL, json={"query": query, "response": {"format": "json-stat2"}},
                      timeout=120, headers=UA)
    print(f"  [statice] UTA06001 data status={r.status_code}")
    r.raise_for_status()
    rows = parse_px(r.json(), pv["code"], tv["code"])
    got = {key: sorted(rows.get(code, {}).items()) for key, (code, _) in PX_ROWS.items()}
    for key, pts in got.items():
        if not pts:
            raise ValueError(f"UTA06001 {key}: no observations")
        if pts[0][0] > SI_START:
            raise ValueError(f"UTA06001 {key} starts {pts[0][0]}, after {SI_START}: the join would leave a gap")
        if any(v <= 0 for _, v in pts if key != "balance"):
            raise ValueError(f"UTA06001 {key}: non-positive level")
    ex, im, bal = (dict(got[k]) for k in ("exports", "imports", "balance"))
    bad = [p for p in bal if p in ex and p in im and abs(ex[p] - im[p] - bal[p]) > BALANCE_TOLERANCE]
    if bad:
        raise ValueError(f"UTA06001: exports less imports differs from the table's own balance in {len(bad)} month(s), e.g. {bad[0]}")
    recent = sorted(v for _, v in got["exports"][-12:])
    if not 1e4 <= recent[len(recent) // 2] <= 3e5:
        raise ValueError(f"UTA06001 exports: recent median {recent[len(recent) // 2]} is outside ISK 10bn to 300bn a month (unit change?)")
    out = {}
    for key in ("exports", "imports", "balance"):
        out[key] = require_current([[p, v] for p, v in got[key]], TRADE_MAX_AGE, f"Statistics Iceland {key}")
        print(f"  [statice] {key}: {len(out[key])} months, {out[key][0][0]} to {out[key][-1][0]}")
    return out


def overlap_check(usd: dict, rate: dict, si: dict) -> dict:
    """IMF-derived krónur against the issuer over every month both cover.
    Refuses the splice when they disagree on average by more than
    SPLICE_MAX_MEAN_GAP %: that is a unit or definition slip, not revision noise."""
    stats = {}
    for key in ("exports", "imports"):
        imf, src = dict(usd_to_isk(usd[key], rate)), dict(si[key])
        gaps = [abs(imf[p] / src[p] - 1) * 100 for p in src if p in imf and src[p]]
        if not gaps:
            raise ValueError(f"no month in common between the IMF and Statistics Iceland {key}")
        mean = sum(gaps) / len(gaps)
        stats[key] = (len(gaps), round(mean, 2), round(max(gaps), 1))
        print(f"  [splice] {key}: IMF-derived vs Statistics Iceland over {len(gaps)} months, "
              f"mean gap {mean:.2f}%, largest {max(gaps):.1f}%")
        if mean > SPLICE_MAX_MEAN_GAP:
            raise ValueError(f"{key}: IMF-derived krónur sit {mean:.1f}% from Statistics Iceland on average "
                             f"(limit {SPLICE_MAX_MEAN_GAP}%); refusing to join the two")
    return stats


def build_trade(si: dict, prev_full: dict) -> dict:
    """Pre-2011 months from the IMF (or, if the IMF is down, from the previous run), 2011 on from the issuer."""
    try:
        usd, rate = fetch_trade_usd(), fetch_bis_fx_avg()
    except Exception as exc:
        usd = rate = None
        print(f"NOTE  trade history before {SI_START}: IMF or BIS unavailable ({exc}); "
              f"using the months stored by the previous run")
    if usd:
        overlap_check(usd, rate, si)               # raises: nothing is joined to an issuer series that fails it
        isk = {k: usd_to_isk(v, rate) for k, v in usd.items()}
        head = {k: [q for q in v if q[0] < SI_START] for k, v in isk.items()}
    else:
        prev = (prev_full or {}).get("series", {})
        head = {k: [q for q in (prev.get(k, {}).get("points") or []) if q[0] < SI_START]
                for k in ("exports", "imports")}
    common = set(dict(head["exports"])) & set(dict(head["imports"]))
    head = {k: [q for q in v if q[0] in common] for k, v in head.items()}
    if not head["exports"]:
        raise ValueError(f"no trade history before {SI_START} from the IMF or from the previous run")
    out = {k: head[k] + [q for q in si[k] if q[0] >= SI_START] for k in ("exports", "imports")}
    # All series end at the last month both flows are published, so the Trade tiles describe one month.
    common = set(dict(out["exports"])) & set(dict(out["imports"]))
    out = {k: [q for q in v if q[0] in common] for k, v in out.items()}
    m = dict(out["imports"])
    out["trade_balance"] = [[p, round(v - m[p], 1)] for p, v in out["exports"] if p in m]
    return out


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
    "exports": "Exports of goods, FOB, krónur (Statistics Iceland external trade from January 2011; 2006 to 2010 from the IMF's US$ figures converted at the BIS monthly average rate)",
    "imports": "Imports of goods, CIF, krónur (Statistics Iceland external trade from January 2011; 2006 to 2010 from the IMF's US$ figures converted at the BIS monthly average rate)",
    "trade_balance": "Trade balance, goods, exports FOB less imports CIF, krónur (Statistics Iceland from January 2011; 2006 to 2010 from the IMF's US$ figures converted at the BIS monthly average rate)",
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

    # Trade (v1.8.19): Statistics Iceland from 2011, the IMF's US$ (converted at BIS's monthly
    # average rate) before it. If the issuer fails, or the join fails its check, trade is left out
    # and carried over, never half-replaced.
    si = attempt("trade", fetch_trade_si)
    isk = attempt("trade", lambda: build_trade(si, prev_full)) if si else None
    if isk:
        if isk["trade_balance"]:
            for k, v in isk.items():
                put(out, k, v, TRADE_LABEL[k], "ISKm", "months")
        else:
            failures.append("trade")
            print("FAIL  trade                no month with exports and imports")

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
