#!/usr/bin/env python3
"""v1.9.130: smoother phone map card. mobile.js animates the card's real height and mobile.css fades
the legend in; pages request the new builds: mobile.css v49, mobile.js v46.

Skips the root pages the indicator page generator writes (data-status.html, methodology-by-economy.html):
the bot regenerates those from generate_indicator_pages.py, which this package also bumps.

Idempotent: run twice, expect "N changed" then "0 changed".
"""
import glob, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GENERATED_ROOT = {"methodology-by-economy.html", "data-status.html"}
BUMPS = [("mobile.css?v=48", "mobile.css?v=49"), ("mobile.js?v=45", "mobile.js?v=46")]


def main():
    changed = checked = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        if os.path.basename(f) in GENERATED_ROOT:
            continue
        s0 = s = open(f, encoding="utf-8").read()
        if not any(o in s or n in s for o, n in BUMPS):
            continue
        checked += 1
        for old, new in BUMPS:
            if s.count(old) > 1:
                raise SystemExit(f"{os.path.basename(f)}: {old} found {s.count(old)} times")
            s = s.replace(old, new)
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"{checked} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
