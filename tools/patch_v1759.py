#!/usr/bin/env python3
"""v1.7.59: the Markets FX tile and chart get the (i) button every other tile has.

statTile()/chartPanel() show (i) only when INFO_CONTENT has the tile's key, and
no page had entries for its FX pair keys (fx_hkd_usd, fx_pen_usd, ...), so no
FX tile or chart on any page had one. renderFxMarkets() now registers an entry
per pair from the pair's own description and source, so new pairs and pages
are covered without hand-written text. Idempotent.
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
ANCHOR = "    if(!p || !Array.isArray(p.points) || p.points.length<2) return;\n"
ADD = ANCHOR + '''    // v1.7.59: (i) for the FX tile and chart, built from the pair's own text
    if(typeof INFO_CONTENT === "object" && !INFO_CONTENT[p.key]) INFO_CONTENT[p.key] = {
      description: p.description,
      source: p.source || p.source_short || "",
      dollar: "An exchange rate, not a value in the home currency. \\u201cDollarise\\u201d has no effect on it."};
'''
changed = bad = 0
for f in sorted(ROOT.glob("*.html")):
    t = f.read_text(encoding="utf-8")
    if "function renderFxMarkets" not in t or "v1.7.59: (i) for the FX tile" in t:
        continue
    body = t[t.index("function renderFxMarkets"):]
    if ANCHOR not in body:
        print("FAIL", f.name); bad += 1; continue
    i = t.index("function renderFxMarkets") + body.index(ANCHOR)
    f.write_text(t[:i] + ADD + t[i + len(ANCHOR):], encoding="utf-8"); changed += 1
print(f"v1.7.59: patched {changed} page(s)")
sys.exit(1 if bad else 0)
