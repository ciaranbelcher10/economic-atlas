#!/usr/bin/env python3
"""Coverage-claims gate (v2.0.4).

Every country page's footer and section notes say which series are NOT
available. Those sentences went stale as series were added (the UK footer
said there was no 10-year gilt yield while the page showed one). This gate
reads each "not available" sentence, maps it to the metric keys it talks
about, and fails if the page's data file (or its data-bond-XX.json) actually
carries that metric.

Run: python3 tools/coverage_claims_gate.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# phrase in a "not available" sentence -> keys whose presence contradicts it
TOPICS = [
    (r"exports and imports", ["exports", "imports"]),
    (r"10-year government bond yield|10-year bond yield", ["bond_yield_10y", "@bond10"]),
    (r"policy (interest )?rate|interest rate on this page", ["policy_rate", "boe_rate", "ecb_rate", "boj_rate",
                                                             "overnight_rate", "fed_funds_upper", "fed_funds"]),
    (r"current account", ["current_account"]),
    (r"labour force participation|participation rates?", ["participation_rate", "participation"]),
    (r"employment rate|employment and participation", ["employment_rate", "employment"]),
    (r"fiscal deficit", ["deficit"]),
    (r"productivity", ["productivity"]),
    (r"business confidence", ["business_confidence"]),
    (r"goods trade series", ["trade_balance", "exports"]),
    (r"foreign-exchange rate|convert to usd", ["@fx"]),
]
NEGATIVE = re.compile(r"\bno\b|not available|not shown|isn't|aren't|not yet|unavailable|only tracked", re.I)


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", t) if s.strip()]


def main():
    checked = fails = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        page = os.path.basename(path)
        t = open(path, encoding="utf-8").read()
        m = re.search(r'fetch\("(data(?:-([a-z]{2}))?\.json)"', t)
        if not m or 'id="charts-' not in t:
            continue
        code = m.group(2) or "uk"
        data = json.load(open(os.path.join(ROOT, m.group(1)), encoding="utf-8"))
        keys = set((data.get("series") or {}).keys())
        bond_path = os.path.join(ROOT, f"data-bond-{code}.json")
        if os.path.exists(bond_path):
            bond = json.load(open(bond_path, encoding="utf-8"))
            if bond.get("key") == "bond_yield_10y" or "10-year" in (bond.get("title") or "").lower():
                keys.add("@bond10")
        if os.path.exists(os.path.join(ROOT, f"data-fx-{code}.json")):
            keys.add("@fx")
        blocks = re.findall(r'<p class="secnote"[^>]*>(.*?)</p>', t, re.S)
        a = t.rfind("<footer>")
        if a != -1:
            blocks.append(t[a:t.find("</footer>", a)])
        for blk in blocks:
            for s in sentences(text(blk)):
                if not NEGATIVE.search(s):
                    continue
                for pat, ks in TOPICS:
                    if not re.search(pat, s, re.I):
                        continue
                    checked += 1
                    # "Exports and imports" claims hold only if BOTH are missing
                    present = [k for k in ks if k in keys]
                    if pat == "exports and imports":
                        present = present if set(ks) <= keys else []
                    if present:
                        fails += 1
                        print(f"FAIL {page}: says not available but data has {present}: {s[:160]}")
    print(f"coverage-claims gate: {checked} claims checked, {fails} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
