#!/usr/bin/env python3
"""v1.9.66: a figure that rounds to zero is never shown with a sign ("0.0%", not "−0.0%").
Run: python3 tools/test_negative_zero.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import generate_indicator_pages as g
fails, oks = [], 0
def check(c, m):
    global oks
    if c: oks += 1
    else: fails.append(m)
M = g.MINUS
cases = [(-0.04, "%", "gdp_growth", "value", "0.0%"), (-0.004, "%", "boe_rate", "value", "0.00%"),
         (-0.04, "%", "cpi", "delta", "0.0pp"), (0.04, "%", "cpi", "delta", "0.0pp"),
         (-0.04, "index", "x", "value", "0.0"), (-0.4, "%", "gdp_growth", "value", M + "0.4%"),
         (0.3, "%", "cpi", "delta", "+0.3pp"), (-1.26, "%", "cpi", "value", M + "1.3%")]
for v, u, k, mode, want in cases:
    got = g.fmt_num(v, u, k, "Germany", mode)
    check(got == want, f"fmt_num({v}, {u}, {k}, {mode}) = {got!r}, want {want!r}")
print(f"{oks} ok, {len(fails)} failed")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
