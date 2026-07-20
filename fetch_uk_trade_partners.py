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
from datetime import datetime, timezone

import requests

COMTRADE_BASE = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
UK_REPORTER = "826"

# name, ISO-3166 numeric code (matches the world-atlas ids already used in
# uk.html's map), region (for the "order by region" dropdown)
PARTNERS = [
    ("United States", "840", "Americas"),
    ("Germany", "276", "Europe"),
    ("China", "156", "Asia"),
    ("Netherlands", "528", "Europe"),
    ("France", "250", "Europe"),
    ("Ireland", "372", "Europe"),
    ("Switzerland", "756", "Europe"),
    ("Belgium", "056", "Europe"),
    ("Spain", "724", "Europe"),
    ("Italy", "380", "Europe"),
    ("Norway", "578", "Europe"),
    ("India", "356", "Asia"),
    ("United Arab Emirates", "784", "Middle East"),
    ("South Korea", "410", "Asia"),
]
PARTNER_CODES = ",".join(p[1] for p in PARTNERS)


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
    r = requests.get(COMTRADE_BASE, params=params, headers=headers, timeout=60)
    return r


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
    try:
        r = _get(params, key)
        print(f"  [comtrade] reporter={reporter} partner={partner_codes[:20]}{'...' if len(partner_codes) > 20 else ''} "
              f"flow={flow} period={period} status={r.status_code}")
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
        imp_rows = fetch_flow(UK_REPORTER, PARTNER_CODES, "M", period, key)
        if exp_rows and imp_rows:
            used_period = period
            break
        print(f"  [comtrade] period {period} incomplete — trying an earlier year")

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
    for name, code, region in PARTNERS:
        exp = exp_by_partner.get(code, 0.0)
        imp = imp_by_partner.get(code, 0.0)
        total = exp + imp
        if total <= 0:
            print(f"  [comtrade] {name} ({code}): no data in either flow — skipped")
            continue
        partners_out.append({
            "name": name, "code": code, "region": region,
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
