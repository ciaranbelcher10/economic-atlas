"""Extend a BIS monthly policy-rate series with BIS's daily series (v1.7.13).

BIS's monthly WS_CBPOL series lags rate decisions by up to a month (on 6 Oct
2026 New Zealand's monthly series ended at August though the OCR rose on
2 September). The daily series D.<area> runs ahead. Months after the last
monthly value are filled from it: each month's last daily observation, the
current month showing the latest, as the exchange rate does.

Safety rule: the daily series must agree with the monthly one at the last
monthly month (same month-end value). If it does not, or that month is
missing from the daily data, the two are not the same measure (or the data
is broken) and the monthly series is returned unchanged. This matters for
China, where BIS's monthly series switched from the official lending rate to
the loan prime rate in Aug 2019. Any failure leaves the monthly series as is.
"""
from __future__ import annotations

import csv
import io
import re

import requests

DAILY_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{area}?format=csv&startPeriod={start}"
UA = {"User-Agent": "economic-atlas/0.1 (+https://theeconomicatlas.com)"}


def extend(monthly: list, area: str, label: str = "policy rate") -> list:
    if not monthly:
        return monthly
    last, last_v = monthly[-1][0], monthly[-1][1]
    try:
        r = requests.get(DAILY_URL.format(area=area, start=last + "-01"), timeout=60,
                         headers=dict(UA, Accept="text/csv"))
        print(f"  [bis] WS_CBPOL D.{area} status={r.status_code}")
        r.raise_for_status()
        by_month = {}
        for row in sorted(csv.DictReader(io.StringIO(r.text)), key=lambda x: x.get("TIME_PERIOD", "")):
            v, d = row.get("OBS_VALUE"), row.get("TIME_PERIOD") or ""
            if v not in (None, "", "NaN") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                by_month[d[:7]] = float(v)
        if last not in by_month:
            print(f"  [bis] daily {label} has no {last} to check against the monthly series; monthly series as is")
            return monthly
        if abs(by_month[last] - last_v) > 1e-9:
            print(f"  [bis] daily {label} {by_month[last]} disagrees with monthly {last_v} at {last}; monthly series as is")
            return monthly
        extra = [[m, v] for m, v in sorted(by_month.items()) if m > last]
        if extra:
            print(f"  [bis] daily extends the {label} from {last} to {extra[-1][0]} ({extra[-1][1]}%)")
        return monthly + extra
    except Exception as exc:
        print(f"  [bis] daily {label} unavailable ({exc}); monthly series as is")
        return monthly
