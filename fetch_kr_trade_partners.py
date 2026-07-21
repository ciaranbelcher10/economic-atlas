"""Fetch South Korea bilateral goods-trade values from UN Comtrade for EVERY partner
Comtrade has data for (not a curated shortlist), and write
data-kr-trade-partners.json, consumed by the trade partner map on southkorea.html.
The frontend decides how many to actually display (e.g. top 20 on the
radial view, all of them on the geographic map, top 20 + "show more" on the
ranking list) -- this script's job is just to hand over the full dataset.

Run:  COMTRADE_API_KEY=yourkey python3 fetch_uk_trade_partners.py
In GitHub Actions the key comes from the COMTRADE_API_KEY repository secret.

API STRUCTURE -- confirmed against a real recorded Comtrade API v1 request
(via the comtradr R package's own test fixtures, not guessed from docs
alone): base URL is
  https://comtradeapi.un.org/data/v1/get/{typeCode}/{freqCode}/{clCode}
with typeCode=C (commodities/goods), freqCode=A (annual), clCode=HS, and
query params reporterCode, cmdCode=TOTAL (all commodities), flowCode
(X=export, M=import), motCode=0 (all modes of transport), partner2Code=0,
customsCode=C00. Confirmed live (2026-07-20) with auth via the
"Ocp-Apim-Subscription-Key" header and pinned partnerCode lists -- that part
works.

UPDATE (post-8.5.0): switched from a 14-country curated partnerCode list to
OMITTING partnerCode entirely. NOT yet confirmed live -- the expectation,
based on how Comtrade's data model works (each row is naturally one
reporter-partner-period-flow combination), is that leaving partnerCode
unset returns one row per partner Comtrade holds data for, rather than a
single aggregated "World" row. If that assumption is wrong, this will come
back with just 1-2 rows instead of ~100+ -- check the "X rows" count in the
[comtrade] log lines on the first live run and adjust if so (e.g. try
partnerCode=all as a literal string, or breakdownMode=plus).

COUNTRY CODE MAPPING: Comtrade uses its own historical M49-derived partner
codes, which are usually identical to ISO-3166 numeric but confirmed to
diverge for at least 5 countries (US 842, France 251, Switzerland 757,
Norway 579, India 699 -- all confirmed via a previous live run + Comtrade's
own reference docs). southkorea.html's map needs standard ISO codes to match
world-atlas topojson ids. Rather than build a full ~200-country crosswalk
(which would need Comtrade's own reference file,
comtradeapi.un.org/files/v1/app/reference/partnerAreas.json, cross-checked
against an ISO list), this applies the 5 known overrides and assumes
Comtrade's code equals the ISO code for everyone else. Partners without a
matching world-atlas feature id simply won't get an arc on the map --
harmless, they'll still appear correctly in the ranking list and radial
view, which don't depend on the map at all. If more mismatches turn up
(silently missing arcs for a country that should have one), add it to
COMTRADE_TO_ISO_OVERRIDES below.

NON-COUNTRY CODES: Comtrade's partner list includes aggregates that aren't
real bilateral partners -- "0" (World total) and a handful of historical
grouping codes (documented via a UN FAO crosswalk: 473, 490, 527, 568, 577,
637, 711, 837, 838, 839, 899 -- "Areas, nes", regional groupings, etc.).
These are excluded. There may be others not on this list; if an obviously
non-country name shows up in the output, add its code here.

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
REPORTER = "410"  # South Korea, Comtrade code (confirmed against official examples/prior research where possible; first live run confirms if not)

COMTRADE_TO_ISO_OVERRIDES = {
    "842": "840",  # United States
    "251": "250",  # France
    "757": "756",  # Switzerland
    "579": "578",  # Norway
    "699": "356",  # India
}
# CONFIRMED live (2026-07-20): the no-partnerCode approach worked -- 231
# rows came back for a single call, real per-partner breakdown as hoped.
# Two real issues surfaced in that same run, both now fixed below:
#   1. "World" (code 0) was NOT excluded despite being in this set -- because
#      `code` gets zero-padded to "000" via zfill(3) before the membership
#      check, but this set had a bare "0". They never matched. Fixed by
#      zero-padding these codes the same way.
#   2. On the UK's own version of this script, the reporter itself appeared as a
#      partner ($19.9bn) in one live run -- this is
#      a real, documented Comtrade phenomenon ("trade with itself", usually
#      re-exports or free-zone misclassification), not a parsing bug. A
#      country trading with itself isn't a meaningful "partner" for this
#      feature, so the reporter's own code is now explicitly excluded too.
NON_COUNTRY_CODES = {c.zfill(3) for c in
    ("0", "473", "490", "527", "568", "577", "637", "711", "837", "838", "839", "899")}


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


def _name(row: dict) -> str | None:
    for key in ("partnerDesc", "PartnerDesc", "partner_desc"):
        v = row.get(key)
        if v:
            return str(v)
    return None


def _get(params: dict, key: str) -> requests.Response:
    headers = {
        "User-Agent": "economic-atlas/0.1",
        "Ocp-Apim-Subscription-Key": key,
    }
    return requests.get(COMTRADE_BASE, params=params, headers=headers, timeout=60)


def fetch_flow(reporter: str, flow: str, period: str, key: str) -> list | None:
    params = {
        "reporterCode": reporter,
        "period": period,
        "cmdCode": "TOTAL",
        "flowCode": flow,
        "motCode": "0",
        "partner2Code": "0",
        "customsCode": "C00",
        "includeDesc": "true",
        # partnerCode intentionally omitted -- see module docstring.
    }
    for attempt in range(3):
        try:
            r = _get(params, key)
            print(f"  [comtrade] reporter={reporter} flow={flow} period={period} "
                  f"attempt={attempt+1} status={r.status_code}")
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
        print(f"  [comtrade] {flow} {period}: {len(rows)} rows returned")
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
        exp_rows = fetch_flow(REPORTER, "X", period, key)
        time.sleep(3)  # space out calls -- confirmed live that firing these
                       # back-to-back triggers a 429 burst limit
        imp_rows = fetch_flow(REPORTER, "M", period, key)
        if exp_rows and imp_rows:
            used_period = period
            break
        print(f"  [comtrade] period {period} incomplete — trying an earlier year")
        time.sleep(3)

    if not used_period:
        print("FAIL  comtrade  no usable response for any tried period — "
              "leaving any previously-fetched file in place, not overwriting with nothing")
        return 0

    # code -> {"name":..., "exports":..., "imports":...}
    by_partner: dict[str, dict] = {}

    for row in exp_rows:
        code = str(row.get("partnerCode", "")).zfill(3)
        if code in NON_COUNTRY_CODES or code == REPORTER:
            continue
        v = _value(row)
        if v is None:
            continue
        entry = by_partner.setdefault(code, {"name": _name(row) or code, "exports": 0.0, "imports": 0.0})
        entry["exports"] += v

    for row in imp_rows:
        code = str(row.get("partnerCode", "")).zfill(3)
        if code in NON_COUNTRY_CODES or code == REPORTER:
            continue
        v = _value(row)
        if v is None:
            continue
        entry = by_partner.setdefault(code, {"name": _name(row) or code, "exports": 0.0, "imports": 0.0})
        entry["imports"] += v
        if not entry["name"] or entry["name"] == code:
            entry["name"] = _name(row) or code

    if not by_partner:
        print("FAIL  comtrade  parsed responses but found no usable partner rows — "
              "leaving any previously-fetched file in place")
        return 0

    partners_out = []
    for comtrade_code, entry in by_partner.items():
        exp = entry["exports"]
        imp = entry["imports"]
        total = exp + imp
        if total <= 0:
            continue
        iso_code = COMTRADE_TO_ISO_OVERRIDES.get(comtrade_code, comtrade_code)
        partners_out.append({
            "name": entry["name"], "code": iso_code,
            "exports_usd": round(exp, 0), "imports_usd": round(imp, 0),
            "value_usd": round(total, 0),
        })

    grand_total = sum(p["value_usd"] for p in partners_out)
    grand_exports = sum(p["exports_usd"] for p in partners_out)
    grand_imports = sum(p["imports_usd"] for p in partners_out)
    for p in partners_out:
        p["share_pct"] = round(p["value_usd"] / grand_total * 100, 1) if grand_total else 0.0
        p["export_share_pct"] = round(p["exports_usd"] / grand_exports * 100, 1) if grand_exports else 0.0
        p["import_share_pct"] = round(p["imports_usd"] / grand_imports * 100, 1) if grand_imports else 0.0
    partners_out.sort(key=lambda p: p["value_usd"], reverse=True)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": used_period,
        "reporter": "South Korea",
        "currency": "USD",
        "source": "UN Comtrade (comtradeapi.un.org)",
        "partners": partners_out,
    }
    with open("data-kr-trade-partners.json", "w") as f:
        json.dump(out, f)
    print(f"  ok  comtrade  {len(partners_out)} partners, period {used_period}")
    print(f"\nWrote data-kr-trade-partners.json with {len(partners_out)} partners.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
