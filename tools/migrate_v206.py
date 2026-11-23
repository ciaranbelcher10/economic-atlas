#!/usr/bin/env python3
"""v2.0.6 migration. Idempotent; edits the tree as it stands.
1. fetch_il.py: series_guard exception so the year-end-only Israel debt series
   (v2.0.5) replaces the old one that ends in a part-year 2026 point.
   Remove the exception in the next release, once data-il.json ends at 2025.
2. israel.html: debt tile and chart credit BIS, not the World Bank.
3. Convert to USD$ popover wording: "using that point's OWN contemporaneous X
   rate" -> "at that period's own X rate" (15 country pages + metric sources).
Run from the repo root: python3 tools/migrate_v206.py"""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
changed = []
def edit(fn, fx):
    p = os.path.join(ROOT, fn); t = open(p, encoding="utf-8").read(); t2 = fx(t)
    if t2 != t:
        open(p, "w", encoding="utf-8").write(t2); changed.append(fn)

def il_fetch(t):
    if '"debt_gdp": "v2.0.6' in t: return t
    old = "ALLOW_SHRINK = {}\n"; assert t.count(old) == 1
    return t.replace(old, 'ALLOW_SHRINK = {"debt_gdp": "v2.0.6: year-end (Q4) readings only, so the part-year 2026 point is dropped"}\n')
edit("fetch_il.py", il_fetch)

def il_page(t):
    if "SRC_BIS" in t: return t
    a = 'const SRC_WB="World Bank \\u00b7 % of GDP, annual";'; assert t.count(a) == 1
    t = t.replace(a, a + ' const SRC_BIS="BIS credit statistics \\u00b7 % of GDP, end of year";')
    for old in ['s.debt_gdp,"line",v=>v+"%",pct,SRC_WB);',
                'statTile(tp,"debt_gdp","Gov. debt (% of GDP)",s.debt_gdp,\n    {fmt:pct,fmtD:pp,upIsGood:false,source:SRC_WB});',
                'statTile(hero,"debt_gdp","Gov. debt (% of GDP)",s.debt_gdp,\n    {fmt:pct,fmtD:pp,upIsGood:false,source:SRC_WB});']:
        assert t.count(old) == 1, old
        t = t.replace(old, old.replace("SRC_WB", "SRC_BIS"))
    return t
edit("israel.html", il_page)

PAT = re.compile(r"converts each historical point using that point's OWN contemporaneous ")
def own(t):
    t = PAT.sub("converts each point at that period's own ", t)
    return t.replace(" This is a considered approximation for those years, not a precise historical conversion.", " These years are an approximation.")
for fn in ("australia brazil canada denmark india japan mexico norway singapore southafrica "
           "southkorea sweden thailand uk").split():
    edit(fn + ".html", own)
edit("data-metric-sources.json", own)

print(f"migrate_v206: {len(changed)} files changed")
for c in changed: print("  " + c)
