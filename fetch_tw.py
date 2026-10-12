"""Fetch Taiwan's economic series and write data-tw.json.

Run:  FRED_API_KEY=... python3 fetch_tw.py
In GitHub Actions this runs with the other fetchers.

PARTIAL COVERAGE, by decision (12 Oct 2026). Taiwan's statistics office
(DGBAS, stat.gov.tw) sits behind a Cloudflare bot challenge (403 from
GitHub runners, unreachable from the UK; probe 12 Oct 2026), and Taiwan is
not in World Bank, BIS, IMF CPI/QNA or OECD data. So GDP, inflation and
unemployment are the IMF World Economic Outlook's ANNUAL actuals, and the
page says so.
Built v1.7.50 from fetch_ph.py. Run 1 not yet made: every source below is
unconfirmed until the first real run and audit.

- gdp_level / gdp_real / gdp_growth / cpi / unemployment: IMF WEO actual
  years (NGDP, NGDP_R, NGDP_RPCH, PCPIPCH, LUR). The API returns NGDP and
  NGDP_R in NT$ (units, not billions: run 1, 12 Oct 2026, gave 2.57e13 for
  2024); they are scaled to NT$ million and must land in a plausible range.
- policy_rate: the Central Bank of the Republic of China (Taiwan)'s discount
  rate, from its open-data file WebF1.csv (policy rates by decision date),
  held from each decision to the next, one value per month. cbc.gov.tw is
  fetched over IPv4 only: requests fails on its IPv6 address.
- exports / imports / trade_balance: IMF ITG in US dollars, converted to NT$
  at the monthly average rate (FRED DEXTAUS, Federal Reserve H.10).
- debt_gdp / deficit: IMF WEO via imf_weo.py.
- fx_to_usd: FRED DEXTAUS, NT$ per US$, monthly average.
Not served: quarterly GDP, monthly CPI and labour data, current account and
FDI (no World Bank coverage), bond yield, business confidence.
"""
from __future__ import annotations

import redact_stream  # noqa: F401  (v1.7.42: masks api_key= in all output)
import csv
import io
import json
import os
import re
import socket
import ssl
import sys
from datetime import datetime, timezone

import requests

import imf_weo
import series_guard

ISO3 = "TWN"
OUT_FILE = "data-tw.json"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}
ALLOW_SHRINK = {}
MONTHLY_MAX_AGE = 120
ANNUAL_MAX_AGE = 800

ITG_URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
           "TWN.*.*.M?c[TIME_PERIOD]=ge:2000-M01")
CBC_RATES = "https://www.cbc.gov.tw/public/data/OpenData/WebF1.csv"
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations?series_id={sid}"
            "&api_key={key}&file_type=json&observation_start=1990-01-01")
WB_URL = ""  # Taiwan is not in World Bank data
SERIES_START = {"policy_rate": "1990-01"}

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


# ---------------------------------------------------------------- sources
def _ipv4_get(url: str):
    """cbc.gov.tw: requests fails on the IPv6 address, so resolve IPv4 only."""
    import urllib3.util.connection as uc
    old = uc.allowed_gai_family
    uc.allowed_gai_family = lambda: socket.AF_INET
    try:
        with requests.Session() as s:
            s.mount("https://", _CbcAdapter())
            return s.get(url, timeout=60, headers=UA)
    finally:
        uc.allowed_gai_family = old


class _CbcAdapter(requests.adapters.HTTPAdapter):
    """Run 1 (12 Oct 2026): Python 3.13 rejects cbc.gov.tw's certificate
    chain under VERIFY_X509_STRICT ("Missing Subject Key Identifier").
    The chain is still fully verified against certifi's roots; only the
    strict RFC 5280 profile check is relaxed, for this host only."""

    def init_poolmanager(self, *a, **kw):
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        kw["ssl_context"] = ctx
        return super().init_poolmanager(*a, **kw)


def weo(indicator: str, scale: float = 1.0) -> list:
    pts = imf_weo.fetch(ISO3, indicator)
    if not pts:
        raise ValueError(f"IMF WEO {indicator}: nothing returned")
    pts = [[p, round(v * scale, 1)] for p, v in pts]
    return require_current(pts, ANNUAL_MAX_AGE, f"IMF WEO {indicator}")


def weo_level(indicator: str) -> list:
    """NT$ to NT$ million; fails if the scale is not what run 1 found."""
    pts = weo(indicator, 1e-6)
    if not 1e6 < pts[-1][1] < 1e8:
        raise ValueError(f"IMF WEO {indicator}: {pts[-1]} NT$m is not a plausible GDP; check the unit")
    return pts


def fred(sid: str) -> list:
    """Daily FRED series averaged to calendar months. Run 1: EXTAUS (the
    monthly series) returned 400; DEXTAUS (daily, H.10) works."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise ValueError("FRED_API_KEY not set")
    r = requests.get(FRED_URL.format(sid=sid, key=key), timeout=60, headers=UA)
    r.raise_for_status()
    by: dict = {}
    for o in r.json().get("observations", []):
        if o.get("value") not in (None, "", "."):
            by.setdefault(o["date"][:7], []).append(float(o["value"]))
    pts = [[p, round(sum(v) / len(v), 4)] for p, v in sorted(by.items())]
    return require_current(pts, MONTHLY_MAX_AGE, f"FRED {sid}")


_FX: list = []


def fx_monthly() -> list:
    if not _FX:
        _FX.extend(fred("DEXTAUS"))
    return _FX


def _cbc_date(s: str) -> str | None:
    """'2025/09/19', '20250919' or ROC '114/09/19' to 'YYYY-MM-DD'."""
    m = re.fullmatch(r"\s*(\d{2,4})[/.-]?(\d{1,2})[/.-]?(\d{1,2})\s*", s or "")
    if not m:
        return None
    y = int(m.group(1))
    y = y + 1911 if y < 1911 else y
    return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_cbc_rates(text: str) -> list:
    """Decision dates and the discount rate (重貼現率) from WebF1.csv, then
    one value per month: the rate in force at the end of each month."""
    rows = list(csv.reader(io.StringIO(text)))
    head_i = next((i for i, r in enumerate(rows) if any("重貼現" in c for c in r)), None)
    if head_i is None:
        raise ValueError(f"CBC WebF1: no discount-rate column; first rows {rows[:4]}")
    head = rows[head_i]
    col = next(i for i, c in enumerate(head) if "重貼現" in c)
    steps = []
    for r in rows[head_i + 1:]:
        if len(r) <= col:
            continue
        d = next((_cbc_date(c) for c in r if _cbc_date(c)), None)
        try:
            v = float(r[col])
        except ValueError:
            continue
        if d:
            steps.append((d, v))
    if not steps:
        raise ValueError(f"CBC WebF1: no dated rows; header {head}")
    steps.sort()
    now = datetime.now(timezone.utc)
    y, m = int(steps[0][0][:4]), int(steps[0][0][5:7])
    out, i, cur = [], 0, None
    while (y, m) <= (now.year, now.month):
        per = f"{y}-{m:02d}"
        while i < len(steps) and steps[i][0][:7] <= per:
            cur = steps[i][1]
            i += 1
        out.append([per, cur])
        y, m = (y + (m == 12), m % 12 + 1)
    return [p for p in out if p[0] >= SERIES_START["policy_rate"]]


def fetch_policy_rate() -> list:
    r = _ipv4_get(CBC_RATES)
    print(f"  [cbc] WebF1.csv status={r.status_code} bytes={len(r.content)}")
    r.raise_for_status()
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            text = r.content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    pts = parse_cbc_rates(text)
    bad = [p for p in pts if not (0 <= p[1] < 20)]
    if bad:
        raise ValueError(f"CBC discount rate: implausible value {bad[0]}")
    return require_current(pts, MONTHLY_MAX_AGE, "CBC discount rate")


def fetch_trade() -> dict:
    return trade_from_usd(imf_csv(ITG_URL, "ITG TWN"), dict(fx_monthly()), "NT$")


SERIES = [
    ("gdp_level", lambda: weo_level("NGDP"), "GDP, current prices, annual, actual years (IMF World Economic Outlook)", "TWDm", "years"),
    ("gdp_real", lambda: weo_level("NGDP_R"), "Real GDP, constant prices, annual, actual years (IMF World Economic Outlook)", "TWDm", "years"),
    ("gdp_growth", lambda: weo("NGDP_RPCH"), "Real GDP growth, change on previous year (IMF World Economic Outlook)", "%", "years"),
    ("cpi", lambda: weo("PCPIPCH"), "Consumer prices, annual average change (IMF World Economic Outlook)", "%", "years"),
    ("unemployment", lambda: weo("LUR"), "Unemployment rate, annual (IMF World Economic Outlook)", "%", "years"),
    ("policy_rate", fetch_policy_rate, "Central bank discount rate, end of month (Central Bank of the Republic of China (Taiwan), open data WebF1)", "%", "months"),
    ("trade", fetch_trade, {
        "exports": "Exports of goods, FOB, US$ converted to NT$ at the monthly average rate (IMF international trade in goods; Federal Reserve H.10)",
        "imports": "Imports of goods, CIF, US$ converted to NT$ at the monthly average rate (IMF international trade in goods; Federal Reserve H.10)",
        "trade_balance": "Trade balance, goods, exports less imports, NT$ (IMF ITG, converted at the H.10 daily rate, averaged by month rate)",
    }, "TWDm", "months"),
    ("debt_gdp", lambda: imf_weo.fetch(ISO3, imf_weo.DEBT), "General government gross debt, % of GDP (IMF WEO)", "%", "years"),
    ("deficit", lambda: imf_weo.fetch(ISO3, imf_weo.DEFICIT), "General government net lending/borrowing, % of GDP (IMF WEO)", "%", "years"),
]


def extra(out: dict, prev_full: dict) -> None:
    try:
        fx = fx_monthly()
        out["fx_to_usd"] = {"pair": "TWD/USD", "rate": fx[-1][1], "as_of": fx[-1][0], "direction": "divide", "history": fx}
        print(f"  ok  fx_to_usd            {fx[-1][1]} NT$ per US$ ({fx[-1][0]}, FRED DEXTAUS monthly average)")
    except Exception as exc:
        print(f"FAIL  fx_to_usd            {exc}")
    if not out.get("fx_to_usd") and prev_full.get("fx_to_usd"):
        out["fx_to_usd"] = prev_full["fx_to_usd"]
        print("CARRIED OVER fx_to_usd from previous run")


def main() -> int:
    return run(SERIES, extra)


if __name__ == "__main__":
    sys.exit(main())
