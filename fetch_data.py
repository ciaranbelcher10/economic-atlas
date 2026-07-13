"""Fetch UK economic series from the ONS API and write data.json.

Run:  python3 fetch_data.py
Needs only the `requests` package (pip install requests).
No API key required. Source: Office for National Statistics.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import requests

# key: (list of page URIs to try in order, label, unit)
# URIs verified against ons.gov.uk — first entry confirmed unless noted.
SERIES = {
    "gdp_level": (["/economy/grossdomesticproductgdp/timeseries/abmi/pn2"],
                  "GDP, chained volume measure (ABMI)", "£m"),
    "gdp_growth": (["/economy/grossdomesticproductgdp/timeseries/ihyq/pn2"],
                   "GDP growth, quarter on quarter (IHYQ)", "%"),
    "productivity": (["/employmentandlabourmarket/peopleinwork/labourproductivity/timeseries/lzvb/prdy"],
                     "Output per hour worked, index 2023=100 (LZVB)", "index"),
    "unemployment": (["/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms"],
                     "Unemployment rate, 16+, SA (MGSX)", "%"),
    "employment": (["/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/timeseries/lf24/lms"],
                   "Employment rate, 16-64, SA (LF24)", "%"),
    "inactivity": (["/employmentandlabourmarket/peoplenotinwork/economicinactivity/timeseries/lf2s/lms"],
                   "Economic inactivity rate, 16-64, SA (LF2S)", "%"),
    "cpi": (["/economy/inflationandpriceindices/timeseries/d7g7/mm23"],
            "CPI annual rate, all items (D7G7)", "%"),
    "cpih": (["/economy/inflationandpriceindices/timeseries/l55o/mm23"],
             "CPIH annual rate, all items (L55O)", "%"),
    "cpi_mom": (["/economy/inflationandpriceindices/timeseries/d7oe/mm23"],
                "CPI monthly rate, all items (D7OE)", "%"),
    "debt_gdp": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/hf6x/pusf"],
                 "Public sector net debt ex banks, % of GDP (HF6X)", "%"),
    "deficit": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/dzls/pusf"],
                "Public sector net borrowing ex banks (DZLS)", "£m"),
    # quarterly BOP first (unverified but harmless to try), annual Pink Book fallback (verified)
    "current_account": (["/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/bop",
                         "/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/pb"],
                        "Current account balance, % of GDP (AA6H)", "%"),
    "trade_balance": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbj/mret"],
                      "Total trade balance, goods and services, SA (IKBJ)", "£m"),
    "exports": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbh/mret"],
                "Total exports, goods and services, SA (IKBH)", "£m"),
    "imports": (["/economy/nationalaccounts/balanceofpayments/timeseries/ikbi/mret"],
                "Total imports, goods and services, SA (IKBI)", "£m"),
}

ENDPOINTS = [
    "https://api.beta.ons.gov.uk/v1/data?uri={uri}",
    "https://www.ons.gov.uk{uri}/data",
]

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def parse_date(raw: str, freq: str) -> str:
    """'1989 JAN' -> '1989-01'; '2024 Q1' -> '2024-Q1'; '1989' -> '1989'."""
    raw = raw.strip()
    if freq == "months":
        year, mon = raw.split()
        return f"{year}-{MONTHS[mon.upper()]:02d}"
    if freq == "quarters":
        return raw.replace(" ", "-")
    return raw


# --------------------------------------------------------------------------
# OECD business confidence (BCI) — free SDMX API, no key.
# Tries targeted keys first, then a broad pull filtered locally. Any failure
# just means the series is skipped; the page shows the tile as pending.
# --------------------------------------------------------------------------
OECD_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI"
OECD_QUERIES = [
    f"{OECD_BASE}/GBR.M.BCICP...AA...H?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/GBR.M.BCICP......?format=csvfile&startPeriod=1990",
    f"{OECD_BASE}/all?format=csvfile&startPeriod=2000",
]


def fetch_oecd_bci() -> tuple[str, list] | None:
    import csv
    import io
    for url in OECD_QUERIES:
        try:
            r = requests.get(url, timeout=60,
                             headers={"User-Agent": "economic-atlas/0.1"})
            r.raise_for_status()
        except Exception:
            continue
        try:
            reader = csv.DictReader(io.StringIO(r.text))
            rows = {}
            for row in reader:
                low = {k.upper(): (v or "") for k, v in row.items() if k}
                if low.get("REF_AREA", "GBR") != "GBR":
                    continue
                if low.get("MEASURE", "BCICP") != "BCICP":
                    continue
                freq = low.get("FREQ") or low.get("FREQUENCY") or "M"
                if freq != "M":
                    continue
                period = low.get("TIME_PERIOD", "")
                value = low.get("OBS_VALUE", "")
                if not period or not value:
                    continue
                try:
                    rows[period] = float(value)
                except ValueError:
                    continue
            if rows:
                points = sorted([[p, v] for p, v in rows.items()],
                                key=lambda x: x[0])
                return "months", points
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# World Bank FDI (net inflows, % of GDP, annual) — free API, no key.
# --------------------------------------------------------------------------
WB_FDI_URL = ("https://api.worldbank.org/v2/country/GBR/indicator/"
              "BX.KLT.DINV.WD.GD.ZS?format=json&per_page=200")


def fetch_worldbank_fdi() -> tuple[str, list] | None:
    r = requests.get(WB_FDI_URL, timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return None
    points = []
    for row in payload[1]:
        try:
            if row.get("value") is None:
                continue
            points.append([str(row["date"]), float(row["value"])])
        except (KeyError, ValueError, TypeError):
            continue
    if not points:
        return None
    points.sort(key=lambda p: p[0])
    return "years", points


# --------------------------------------------------------------------------
# Bank of England Bank Rate (IUDBEDR) — IADB CSV endpoint, no key.
# Daily series; reduced to end-of-month observations.
# --------------------------------------------------------------------------
BOE_URL = ("https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp"
           "?csv.x=yes&Datefrom=01/Jan/1975&Dateto=now"
           "&SeriesCodes=IUDBEDR&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")

BOE_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}


def fetch_boe_rate() -> tuple[str, list] | None:
    import csv
    import io
    r = requests.get(BOE_URL, timeout=60,
                     headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    reader = csv.reader(io.StringIO(r.text))
    monthly = {}
    for row in reader:
        if len(row) < 2:
            continue
        raw_date, raw_val = row[0].strip(), row[1].strip()
        try:
            value = float(raw_val)
        except ValueError:
            continue  # header or junk row
        # date like "31 Jan 2020" or "2020-01-31"
        period = None
        parts = raw_date.replace("-", " ").split()
        if len(parts) == 3:
            if parts[0].isdigit() and len(parts[0]) == 4:      # 2020 01 31
                period = f"{parts[0]}-{int(parts[1]):02d}"
            elif parts[2].isdigit() and len(parts[2]) == 4:    # 31 Jan 2020
                mon = BOE_MONTHS.get(parts[1][:3].upper())
                if mon:
                    period = f"{parts[2]}-{mon:02d}"
        if period:
            monthly[period] = value  # rows are chronological; keep last per month
    if not monthly:
        return None
    points = sorted([[p, v] for p, v in monthly.items()], key=lambda x: x[0])
    return "months", points


def fetch(uris: list[str]) -> tuple[str, list] | None:
    last_error = None
    for uri in uris:
        for template in ENDPOINTS:
            url = template.format(uri=uri)
            try:
                r = requests.get(url, timeout=30,
                                 headers={"User-Agent": "economic-atlas/0.1"})
                r.raise_for_status()
                payload = r.json()
            except Exception as exc:
                last_error = exc
                continue
            for freq in ("months", "quarters", "years"):
                obs = payload.get(freq)
                if obs:
                    points = []
                    for o in obs:
                        try:
                            points.append([parse_date(o["date"], freq),
                                           float(o["value"])])
                        except (KeyError, ValueError):
                            continue
                    points.sort(key=lambda p: p[0])
                    return freq, points
    if last_error:
        raise last_error
    return None


def load_previous() -> dict:
    """Latest periods from the existing data.json, for new-data detection."""
    try:
        with open("data.json") as f:
            old = json.load(f)
        return {k: v["points"][-1][0]
                for k, v in old.get("series", {}).items() if v.get("points")}
    except Exception:
        return {}


def main() -> int:
    previous = load_previous()
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sample": False,
        "series": {},
    }
    failures = []
    for key, (uris, label, unit) in SERIES.items():
        try:
            result = fetch(uris)
            if result is None:
                raise ValueError("no observations in response")
            freq, points = result
            out["series"][key] = {
                "label": label, "unit": unit, "freq": freq, "points": points,
            }
            print(f"  ok  {key:<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, {freq})")
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<16} {exc}")

    # Non-ONS sources, each independent and optional
    extras = [
        ("business_confidence", fetch_oecd_bci,
         "Business confidence indicator, LT avg = 100 (OECD BCICP)", "index"),
        ("fdi", fetch_worldbank_fdi,
         "FDI net inflows, % of GDP (World Bank BX.KLT.DINV.WD.GD.ZS)", "%"),
        ("boe_rate", fetch_boe_rate,
         "Official Bank Rate (Bank of England IUDBEDR)", "%"),
    ]
    for key, fn, label, unit in extras:
        try:
            result = fn()
            if result is None:
                raise ValueError("no usable response")
            freq, points = result
            out["series"][key] = {"label": label, "unit": unit,
                                  "freq": freq, "points": points}
            print(f"  ok  {key:<16} {len(points):>5} observations "
                  f"({points[0][0]} to {points[-1][0]}, {freq})")
        except Exception as exc:
            failures.append(key)
            print(f"FAIL  {key:<16} {exc}")

    if not out["series"]:
        print("\nNothing fetched — check your internet connection.")
        return 1

    # Series whose latest observation is newer than in the previous data.json
    out["new_points"] = {
        k: v["points"][-1][0] for k, v in out["series"].items()
        if k in previous and previous[k] != v["points"][-1][0]
    }
    if out["new_points"]:
        print("New data points: " + ", ".join(
            f"{k} ({p})" for k, p in out["new_points"].items()))

    with open("data.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
