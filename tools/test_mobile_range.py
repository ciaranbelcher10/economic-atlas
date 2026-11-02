#!/usr/bin/env python3
"""v1.9.66: on phones an indicator chart opens on 10 years, with Max one tap away.
Run: python3 tools/test_mobile_range.py"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
k = open(os.path.join(ROOT, "indicator-kit.js"), encoding="utf-8").read()
g = open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read()
fails, oks = [], 0
def check(c, m):
    global oks
    if c: oks += 1
    else: fails.append(m)
m = re.search(r'var b10 = document\.querySelector\(\'\[data-range="10"\]\'\);\s*if\(b10 && window\.matchMedia && window\.matchMedia\("\(max-width: (\d+)px\)"\)\.matches\) b10\.click\(\);', k)
check(m, "kit clicks the 10Y button on phones")
check(m and int(m.group(1)) <= 760, "the phone breakpoint is a phone width")
check(m and k.index("b10.click()") > k.index('document.querySelectorAll("[data-range]").forEach'), "10Y is chosen after the range buttons are wired")
check('data-range="10"' in g and 'data-range="max" class="active"' in g, "desktop still opens on Max, 10Y button exists")
check(re.search(r'KIT_VERSION = "(\d+)"', g) and int(re.search(r'KIT_VERSION = "(\d+)"', g).group(1)) >= 9, "kit cache-buster bumped")
print(f"{oks} ok, {len(fails)} failed")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
