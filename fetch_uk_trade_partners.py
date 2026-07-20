"""Fetch UK bilateral goods-trade values from UN Comtrade and write
data-uk-trade-partners.json, consumed by the trade partner map on uk.html.

Run:  COMTRADE_API_KEY=yourkey python3 fetch_uk_trade_partners.py
In GitHub Actions the key comes from the COMTRADE_API_KEY repository secret.

API STRUCTURE -- confirmed against a real recorded Comtrade API v1 request
(via the comtradr R package's own test fixtures, not guessed from docs
alone): base URL is
  https://comtradeapi.un.org/data/v1/get/{typeCode}/{freqCode}/{clCode}
with typeCode=C (commodities/goods), freqCode=A (annual), clCode=HS, and
query params reporterCode, partnerCode (comma-separated list of ISO numeric
codes), cmdCode=TOTAL (all commodities), flowCode (X=export, M=import),
motCode=0 (all modes of transport), partner2Code=0, customsCode=C00.

NOT personally confirmed (first live run is the real test, per this repo's
standing practice):
  - The auth mechanism. Comtrade's API sits behind Azure API Management
    (visible from its response headers -- "Request-Context: appId=cid-v1:..."
    is an Azure APIM signature), and Azure APIM's own default convention is
    the "Ocp-Apim-Subscription-Key" HTTP header, so that's what's used here.
    If this is wrong the fetch will fail with 401/403 -- check the
    [comtrade] log lines.
  - The exact JSON field name for the trade value. Comtrade's documented
    schema uses camelCase ("primaryValue"), but third-party wrappers
    sometimes show snake_case after their own renaming, so this defensively
    checks a few likely variants.
  - Which annual period is the latest with real (non-empty) data for the UK
    as reporter -- tries a few recent years and keeps whichever has rows.

SCOPE: this covers a curated list of 14 major partners (the same list
already shown in the illustrative prototype), not a true "top N of all ~200
partners" ranking -- that would need Comtrade's separate trade-matrix
endpoint. Good enough for v1; flagged as a possible future enhancement.

Values are left in US dollars, Comtrade's native reporting currency,
rather than converted to GBP -- avoids depending on a separately-fetched FX
rate in what is otherwise a standalone script.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

COMTRADE_BASE = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
UK_REPORTER = "826"

# name, ISO-3166 numeric code (matches the world-atlas ids already used in
# uk.html's map), Comtrade partner code, region (for the "order by region"
# dropdown). CONFIRMED live (2026-07-20): 5 of 14 partners came back with
# "no data in either flow" on the first real run -- United States, France,
# Switzerland, Norway, India. Traced to a real, documented cause: Comtrade
# uses its own historical M49-derived codes for these five specifically,
# which diverge from standard ISO-3166 numeric (confirmed against Comtrade's
# own reference docs and the comtradr package's country code table) --
# these aren't guesses, all 5 mismatches are confirmed divergences:
#   US 840->842, France 250->251, Switzerland 756->757, Norway 578->579,
#   India 356->699.
# The ISO code is kept separately because uk.html's map uses world-atlas
# topojson, which uses standard ISO numeric ids -- only the API query needs
# Comtrade's own code.
PARTNERS = [
    ("United States", "840", "842", "Americas"),
    ("Germany", "276", "276", "Europe"),
    ("China", "156", "156", "Asia"),
    ("Netherlands", "528", "528", "Europe"),
    ("France", "250", "251", "Europe"),
    ("Ireland", "372", "372", "Europe"),
    ("Switzerland", "756", "757", "Europe"),
    ("Belgium", "056", "056", "Europe"),
    ("Spain", "724", "724", "Europe"),
    ("Italy", "380", "380", "Europe"),
    ("Norway", "578", "579", "Europe"),
    ("India", "356", "699", "Asia"),
    ("United Arab Emirates", "784", "784", "Middle East"),
    ("South Korea", "410", "410", "Asia"),
]
PARTNER_CODES = ",".join(p[2] for p in PARTNERS)


def _value(row: dict) -> float | None:
    """Comtrade's documented field is camelCase; defensively check variants
    in case a differently-cased schema comes back."""
    for key in ("primaryValue", "PrimaryValue", "primary_value", "fobvalue", "cifvalue"):
        v = row.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _get(params: dict, key: str) -> requests.Response:
    headers = {
        "User-Agent": "economic-atlas/0.1",
        "Ocp-Apim-Subscription-Key": key,
    }
    return requests.get(COMTRADE_BASE, params=params, headers=headers, timeout=60)


def fetch_flow(reporter: str, partner_codes: str, flow: str, period: str, key: str) -> list | None:
    params = {
        "reporterCode": reporter,
        "partnerCode": partner_codes,
        "period": period,
        "cmdCode": "TOTAL",
        "flowCode": flow,
        "motCode": "0",
        "partner2Code": "0",
        "customsCode": "C00",
        "includeDesc": "true",
    }
    # CONFIRMED on a live run (2026-07-20): the free tier's daily quota
    # (500 calls/day) isn't what bit us -- a burst/per-second rate limit
    # is. Firing two calls back-to-back got the second one 429'd every
    # time, across three different periods. Space calls out and retry
    # once on 429 with a longer pause before giving up on this call.
    for attempt in range(3):
        try:
            r = _get(params, key)
            print(f"  [comtrade] reporter={reporter} partner={partner_codes[:20]}{'...' if len(partner_codes) > 20 else ''} "
                  f"flow={flow} period={period} attempt={attempt+1} status={r.status_code}")
            if r.status_code == 429:
                wait = 8 * (attempt + 1)
                print(f"  [comtrade] rate limited, waiting {wait}s before retry")
                time.sleep(wait)
                continue
            r.raise_for_status()
        except Exception as exc:
            print(f"  [comtrade] request failed: {exc}")
            return None
        try:
            payload = r.json()
        except Exception as exc:
            print(f"  [comtrade] response wasn't JSON: {exc}; first 300 chars: {r.text[:300]!r}")
            return None
        rows = payload.get("data")
        if rows is None:
            print(f"  [comtrade] no 'data' key in response; top-level keys: {list(payload.keys())}")
            return None
        return rows
    print(f"  [comtrade] still rate limited after retries for flow={flow} period={period}")
    return None


def main() -> int:
    key = os.environ.get("COMTRADE_API_KEY")
    if not key:
        print("WARN  no COMTRADE_API_KEY set — skipping, prototype data stays on the page.")
        return 0

    periods_to_try = ["2025", "2024", "2023"]
    exp_rows = imp_rows = None
    used_period = None
    for period in periods_to_try:
        exp_rows = fetch_flow(UK_REPORTER, PARTNER_CODES, "X", period, key)
        time.sleep(3)  # space out calls -- confirmed live that firing these
                       # back-to-back triggers a 429 burst limit
        imp_rows = fetch_flow(UK_REPORTER, PARTNER_CODES, "M", period, key)
        if exp_rows and imp_rows:
            used_period = period
            break
        print(f"  [comtrade] period {period} incomplete — trying an earlier year")
        time.sleep(3)

    if not used_period:
        print("FAIL  comtrade  no usable response for any tried period — "
              "leaving any previously-fetched file in place, not overwriting with nothing")
        return 0

    exp_by_partner: dict[str, float] = {}
    for row in exp_rows:
        code = str(row.get("partnerCode", "")).zfill(3)
        v = _value(row)
        if v is not None:
            exp_by_partner[code] = exp_by_partner.get(code, 0.0) + v

    imp_by_partner: dict[str, float] = {}
    for row in imp_rows:
        code = str(row.get("partnerCode", "")).zfill(3)
        v = _value(row)
        if v is not None:
            imp_by_partner[code] = imp_by_partner.get(code, 0.0) + v

    partners_out = []
    for name, iso_code, comtrade_code, region in PARTNERS:
        exp = exp_by_partner.get(comtrade_code, 0.0)
        imp = imp_by_partner.get(comtrade_code, 0.0)
        total = exp + imp
        if total <= 0:
            print(f"  [comtrade] {name} (iso={iso_code}, comtrade={comtrade_code}): "
                  f"no data in either flow — skipped")
            continue
        partners_out.append({
            "name": name, "code": iso_code, "region": region,
            "exports_usd": round(exp, 0), "imports_usd": round(imp, 0),
            "value_usd": round(total, 0),
        })

    if not partners_out:
        print("FAIL  comtrade  parsed responses but no partner had usable data — "
              "leaving any previously-fetched file in place")
        return 0

    grand_total = sum(p["value_usd"] for p in partners_out)
    for p in partners_out:
        p["share_pct"] = round(p["value_usd"] / grand_total * 100, 1) if grand_total else 0.0
    partners_out.sort(key=lambda p: p["value_usd"], reverse=True)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": used_period,
        "reporter": "United Kingdom",
        "currency": "USD",
        "source": "UN Comtrade (comtradeapi.un.org)",
        "partners": partners_out,
    }
    with open("data-uk-trade-partners.json", "w") as f:
        json.dump(out, f)
    print(f"  ok  comtrade  {len(partners_out)} partners, period {used_period}")
    print(f"\nWrote data-uk-trade-partners.json with {len(partners_out)} partners.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
