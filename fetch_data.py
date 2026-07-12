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
    "debt_gdp": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/hf6x/pusf"],
                 "Public sector net debt ex banks, % of GDP (HF6X)", "%"),
    "deficit": (["/economy/governmentpublicsectorandtaxes/publicsectorfinance/timeseries/dzls/pusf"],
                "Public sector net borrowing ex banks (DZLS)", "£m"),
    # quarterly BOP first (unverified but harmless to try), annual Pink Book fallback (verified)
    "current_account": (["/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/bop",
                         "/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/pb"],
                        "Current account balance, % of GDP (AA6H)", "%"),
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


def main() -> int:
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

    if not out["series"]:
        print("\nNothing fetched — check your internet connection.")
        return 1

    with open("data.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote data.json with {len(out['series'])} series.")
    if failures:
        print(f"Missing: {', '.join(failures)} — the page will still render.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
