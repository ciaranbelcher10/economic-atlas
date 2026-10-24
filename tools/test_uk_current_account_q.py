#!/usr/bin/env python3
"""UK quarterly current account (v1.9.8): the contract.

  1. `current_account` (annual) is untouched: still the bop and pb URIs, never
     the quarterly PNBP dataset, so Rankings, Compare and the indicator page
     keep ranking a completed year.
  2. `current_account_q` reads AA6H from PNBP only.
  3. A quarterly ONS payload parses to "YYYY-Qn" periods and freq "quarters".
  4. Only uk.html (and the data/info files) may mention the new key: Compare,
     ChartMaker, Dashboard, the generator and the rankings must not read it.
  5. uk.html guards the chart on the series existing, and INFO_CONTENT in
     uk.html equals data-metric-sources.json["UK"] for the new key.

Run from the repo root:  python3 tools/test_uk_current_account_q.py
"""
import json
import re
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_data  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


S = fetch_data.UK_SERIES
annual_uris, _, annual_unit = S["current_account"]
check(annual_uris == [
    "/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/bop",
    "/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/pb"],
    f"annual current_account URIs changed: {annual_uris}")
check(not any("pnbp" in u for u in annual_uris), "annual series must not use pnbp")

check("current_account_q" in S, "current_account_q missing from UK_SERIES")
q_uris, q_label, q_unit = S.get("current_account_q", ([], "", ""))
check(q_uris == ["/economy/nationalaccounts/balanceofpayments/timeseries/aa6h/pnbp"],
      f"quarterly URIs wrong: {q_uris}")
check(q_unit == "%", f"quarterly unit wrong: {q_unit}")
check("quarterly" in q_label.lower() and "AA6H" in q_label, f"label wrong: {q_label}")

payload = {"quarters": [{"date": "2025 Q1", "value": "-2.1"},
                        {"date": "2025 Q2", "value": "-3.8"},
                        {"date": "2024 Q4", "value": "-1.9"}],
           "description": {"nextRelease": "31 December 2026"}}


class R:
    def raise_for_status(self):
        pass

    def json(self):
        return payload


seen = []


def fake_get(url, **kw):
    seen.append(url)
    return R()


with mock.patch.object(fetch_data.requests, "get", fake_get):
    res = fetch_data.fetch_ons(q_uris)
check(res is not None, "fetch_ons returned None on a quarterly payload")
if res:
    freq, pts, nxt = res
    check(freq == "quarters", f"freq {freq!r}, expected 'quarters'")
    check(pts == [["2024-Q4", -1.9], ["2025-Q1", -2.1], ["2025-Q2", -3.8]],
          f"points wrong or unsorted: {pts}")
    check(nxt == "31 December 2026", f"nextRelease lost: {nxt!r}")
check(seen and "/aa6h/pnbp" in seen[0], f"did not request pnbp first: {seen[:1]}")

# 4. nobody else reads the key
KEY = "current_account_q"
allowed = {"fetch_data.py", "uk.html", "data-metric-sources.json",
           "tools/test_uk_current_account_q.py",
           "tools/test_uk_current_account_q_render.js"}
for p in list(ROOT.glob("*.html")) + list(ROOT.glob("*.py")) + list(ROOT.glob("*.js")) \
        + list((ROOT / "tools").glob("*")):
    rel = str(p.relative_to(ROOT))
    if rel in allowed or not p.is_file():
        continue
    try:
        txt = p.read_text(encoding="utf-8")
    except Exception:
        continue
    check(KEY not in txt, f"{rel} mentions {KEY}; the quarterly series is UK page only")

# 5. page guard and info text
uk = (ROOT / "uk.html").read_text(encoding="utf-8")
check("if(s.current_account_q) chartPanel(" in uk, "uk.html chart not guarded on the series")
check("statTile(hero,\"current_account_q\"" not in uk,
      "no hero tile: the hero is capped at 10 and already full")
meta = json.loads((ROOT / "data-metric-sources.json").read_text(encoding="utf-8"))["UK"]
m = re.search(r"  current_account_q: \{\n(.*?)\n  \},", uk, re.S)
check(bool(m), "INFO_CONTENT entry missing in uk.html")
if m:
    body = "{\n" + m.group(1) + "\n}"
    body = re.sub(r"(\n\s*)(description|source|dollar):", r'\1"\2":', body)
    page = json.loads(body)
    check(page == meta.get("current_account_q"),
          "INFO_CONTENT differs from data-metric-sources.json")

print("test_uk_current_account_q:", "FAILED" if fails else "ok", f"({len(fails)} failures)")
sys.exit(1 if fails else 0)
