"""Monthly goods trade from the IMF's International Trade in Goods dataset (ITG), in US$ million.

v1.9.138 (verification, 15 Nov 2026): Brazil, Canada, Denmark, Korea and Mexico showed a quarterly trade balance
from the OECD's seasonally adjusted merchandise series on FRED (XTNTVA01..Q667S). Those quarters did not match the
national customs figures: Mexico 2025-Q3 -8bn pesos on the site against -173bn from the IMF's monthly data;
Denmark about 3.5 times the IMF's figure. This module serves the route already used for China, Egypt, New Zealand,
the Philippines, Pakistan, Saudi Arabia, Taiwan and Vietnam: exports free on board, imports cost, insurance and
freight, as each country reports them to the IMF, not seasonally adjusted. The calling script converts them to its
own currency at each month's average rate.

series(iso3) -> {"exports": [[YYYY-MM, US$m], ...], "imports": [...], "trade_balance": [...]}, ending at the last
month both flows are published, so the three always describe the same month. Raises on failure.
"""
from __future__ import annotations

import csv
import io
import time

import requests

URL = ("https://api.imf.org/external/sdmx/3.0/data/dataflow/IMF.STA/ITG/~/"
       "{iso3}.*.*.M?c%5BTIME_PERIOD%5D=ge:1990-M01")
UA = {"User-Agent": "economic-atlas/0.1", "Accept": "text/csv"}
LABEL = {
    "exports": "Exports of goods, free on board (IMF international trade in goods, not seasonally adjusted)",
    "imports": "Imports of goods, cost, insurance and freight (IMF international trade in goods, not seasonally adjusted)",
    "trade_balance": "Trade balance, goods, exports free on board less imports cost, insurance and freight "
                     "(IMF international trade in goods, not seasonally adjusted)",
}
MIN_MONTHS = 60


def _period(tp: str) -> str | None:
    tp = (tp or "").strip()
    if len(tp) == 8 and tp[4:6] == "-M":
        return f"{tp[:4]}-{tp[6:]}"
    if len(tp) == 7 and tp[4] == "-" and tp[5:].isdigit():
        return tp
    return None


def series(iso3: str) -> dict:
    last = None
    for attempt in (1, 2):
        try:
            r = requests.get(URL.format(iso3=iso3), timeout=90, headers=UA)
            print(f"  [imf-itg] {iso3} status={r.status_code}")
            r.raise_for_status()
            break
        except Exception as exc:
            last = exc
            if attempt == 1:
                time.sleep(5)
    else:
        raise last
    flows = {"XG": {}, "MG": {}}
    for row in csv.DictReader(io.StringIO(r.text)):
        ind = row.get("INDICATOR")
        if ind not in flows or row.get("UNIT") != "USD":
            continue
        if (ind, row.get("VALUATION")) not in (("XG", "FOB"), ("MG", "CIF")):
            continue
        p = _period(row.get("TIME_PERIOD"))
        try:
            v = float(row.get("OBS_VALUE") or "")
        except ValueError:
            continue
        if p:
            flows[ind][p] = v / 1e6          # raw US dollars -> US$ million
    common = sorted(set(flows["XG"]) & set(flows["MG"]))
    if len(common) < MIN_MONTHS:
        raise ValueError(f"IMF ITG {iso3}: only {len(common)} months with both flows")
    return {
        "exports": [[p, round(flows["XG"][p], 1)] for p in common],
        "imports": [[p, round(flows["MG"][p], 1)] for p in common],
        "trade_balance": [[p, round(flows["XG"][p] - flows["MG"][p], 1)] for p in common],
    }
