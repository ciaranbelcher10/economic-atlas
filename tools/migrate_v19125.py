#!/usr/bin/env python3
"""v1.9.125: Cyprus population covers the same area as its GDP (Eurostat, government-controlled area).

The Cyprus country page named the World Bank as the population source in five places; it now names
Eurostat and says why. Only cyprus.html changes. Idempotent: run twice, expect "1 changed" then "0 changed".
"""
import os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARK = "v1.9.125 Cyprus population"
EDITS = [
    ('"Calculated: complete calendar years of GDP divided by that year\'s population (World Bank)"',
     '"Calculated: complete calendar years of GDP divided by that year\'s population (Eurostat, government-controlled area, the same area as GDP)"'),
    ('s.population,"line",fmtPeople,fmtPeople,"World Bank \\u00b7 Population, total (SP.POP.TOTL), mid-year estimates, annual");',
     's.population,"line",fmtPeople,fmtPeople,"Eurostat \\u00b7 Population, national accounts concept (nama_10_pe), government-controlled area, the same area as GDP");'),
    ('{fmt:fmtPeople,fmtD:fmtPeople,upIsGood:true,source:"World Bank \\u00b7 SP.POP.TOTL"});',
     '{fmt:fmtPeople,fmtD:fmtPeople,upIsGood:true,source:"Eurostat \\u00b7 nama_10_pe, government-controlled area"});'),
    ('+\'<p class="delta">The World Bank does not publish a population figure for this economy.</p>\';',
     '+\'<p class="delta">No population figure for the same area as Cyprus GDP is available yet.</p>\';'),
]
GPC_OLD = 'source:"GDP \\u00f7 World Bank population"});'
GPC_NEW = 'source:"GDP \\u00f7 Eurostat population (same area)"});'


def migrate(s):
    if MARK in s:
        return s, False
    for old, new in EDITS:
        if s.count(old) != 1:
            raise SystemExit(f"anchor found {s.count(old)} times: {old[:60]}")
        s = s.replace(old, new)
    if s.count(GPC_OLD) != 2:
        raise SystemExit(f"GDP per capita source found {s.count(GPC_OLD)} times, expected 2")
    s = s.replace(GPC_OLD, GPC_NEW)
    s = s.replace("/* v1.9.115 population */", "/* v1.9.115 population; " + MARK + ": Eurostat, same area as GDP */", 1)
    if MARK not in s:
        raise SystemExit("marker anchor missing")
    return s, True


def main():
    f = os.path.join(ROOT, "cyprus.html")
    s = open(f, encoding="utf-8").read()
    new, did = migrate(s)
    if did:
        open(f, "w", encoding="utf-8").write(new)
    print(f"1 page(s) checked, {1 if did else 0} changed")


if __name__ == "__main__":
    main()
