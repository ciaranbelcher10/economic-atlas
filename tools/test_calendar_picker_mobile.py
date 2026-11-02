#!/usr/bin/env python3
"""v1.9.65: the calendar tracking picker must not overlap itself on phones.

At max-width 760px the picker stacks its two columns. When .ctp-body stayed a
grid and .ctp-col kept min-height:0, the implicit rows shrank below their
content and the countries list drew over the Releases column. The phone rule
must make .ctp-body a block and give .ctp-col min-height:auto.
Run: python3 tools/test_calendar_picker_mobile.py
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
h = open(os.path.join(ROOT, "calendar.html"), encoding="utf-8").read()
fails, oks = [], 0
def check(c, m):
    global oks
    if c: oks += 1
    else: fails.append(m)
m = re.search(r"@media \(max-width:760px\)\{([^@]*?\.ctp-body\{[^}]*\}[^@]*?)\}\s*\n", h)
check(m, "phone rule for the picker found")
rule = m.group(1) if m else ""
def decl(sel):
    x = re.search(re.escape(sel) + r"\{([^}]*)\}", rule)
    return x.group(1) if x else ""
body, col = decl(".ctp-body"), decl(".ctp-col")
check("display:block" in body, ".ctp-body is a block on phones")
check("overflow:auto" in body, ".ctp-body scrolls on phones")
check("min-height:auto" in col, ".ctp-col keeps its content height on phones")
check("min-height:0" not in col, ".ctp-col has no min-height:0 on phones")
check("grid-template-columns" not in body, "no grid left on .ctp-body on phones")
print(f"{oks} ok, {len(fails)} failed")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
