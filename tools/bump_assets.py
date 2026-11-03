#!/usr/bin/env python3
"""Bump shared asset cache-busters on the hand-written root pages, in place.

The data bot rewrites the country pages every run, so packages that change a
shared asset ship this script rather than the pages themselves. Idempotent:
a page already on the new version is left alone. Generated pages (indicators/,
embed/, rankings/ and the generator-owned root pages) take their versions from
generate_indicator_pages.py and pick the bump up on the next data run.

Run from the repo root:  python3 tools/bump_assets.py mobile.css=16 mobile.js=18
"""
import os, re, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}

def main(argv):
    pairs = [a.split("=", 1) for a in argv if "=" in a]
    if not pairs:
        print(__doc__); return 2
    changed = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        if os.path.basename(f) in GENERATED:
            continue
        s = open(f, encoding="utf-8").read()
        new = s
        for asset, ver in pairs:
            new = re.sub(re.escape(asset) + r"\?v=\d+\b", f"{asset}?v={ver}", new)
        if new != s:
            open(f, "w", encoding="utf-8").write(new)
            changed.append(os.path.basename(f))
    print(f"bump_assets: {len(changed)} page(s) changed")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
