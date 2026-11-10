#!/usr/bin/env python3
"""v1.9.118 country pages (62):
  1. Miscellaneous gets the same freshness key (Up to date / Awaiting update) as every other section.
  2. The Latest banner names GDP per capita and Population properly ("UK GDP per capita updated",
     not "UK Gdp per capita"), and its fallback keeps GDP / CPI / FDI / PPI / PCE / CPIH upper case.
Page edit at deploy (the bot rewrites country pages); idempotent.
Run from the repo root:  python3 tools/migrate_v19118.py   (exits 1 if a page is left wrong)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEY = ('<p class="lightskey compact" aria-label="Key to freshness lights"><span><span class="led green" '
       'aria-hidden="true"></span>&nbsp;Up to date</span><span><span class="led orange" aria-hidden="true">'
       '</span>&nbsp;Awaiting update</span></p>\n')
MISC_OLD = ' <div class="hero mini" id="tiles-misc"></div>\n <div class="grid" id="charts-misc"></div>\n'
MISC_NEW = ' <div class="hero mini" id="tiles-misc"></div>\n ' + KEY + ' <div class="grid" id="charts-misc"></div>\n'

NAMES_OLD = 'fed_funds_lower:"Fed funds rate (lower)"};'
NAMES_NEW = 'fed_funds_lower:"Fed funds rate (lower)",\n  gdp_per_capita:"GDP per capita",population:"Population"};'

FALL_OLD = '  return t.charAt(0).toUpperCase()+t.slice(1);\n'
FALL_NEW = ('  return (t.charAt(0).toUpperCase()+t.slice(1)).replace(/\\b(gdp|cpih|cpi|fdi|ppi|pce)\\b/gi,'
            ' function(w){ return w.toUpperCase(); });  // v1.9.118\n')

def pages():
    return sorted(p for p in glob.glob(os.path.join(ROOT, "*.html"))
                  if 'prefix.textContent="Latest:"' in open(p, encoding="utf-8").read())

def migrate(s):
    if MISC_NEW not in s:
        assert s.count(MISC_OLD) == 1, "misc section anchor"
        s = s.replace(MISC_OLD, MISC_NEW)
    if NAMES_NEW not in s:
        assert s.count(NAMES_OLD) == 1, "_KEY_NAMES anchor"
        s = s.replace(NAMES_OLD, NAMES_NEW)
    if FALL_NEW not in s:
        assert s.count(FALL_OLD) == 1, "_nameOf fallback anchor"
        s = s.replace(FALL_OLD, FALL_NEW)
    return s

def check(s):
    i = s.index('<section class="sec" id="sec-misc"'); j = s.index("</section>", i)
    return s[i:j].count('class="lightskey') == 1 and NAMES_NEW in s and FALL_NEW in s

def main():
    ps = pages(); changed = 0; bad = []
    for p in ps:
        s = open(p, encoding="utf-8").read()
        try: t = migrate(s)
        except AssertionError as e: bad.append(f"{os.path.basename(p)}: {e}"); continue
        if t != s:
            open(p, "w", encoding="utf-8").write(t); changed += 1
        if not check(t): bad.append(os.path.basename(p) + ": check failed")
    print(f"migrate_v19118: {len(ps)} pages, {changed} changed, {len(bad)} wrong")
    for b in bad: print("  " + b)
    if len(ps) != 62 or bad: sys.exit(1)

if __name__ == "__main__":
    main()
