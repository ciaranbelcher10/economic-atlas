#!/usr/bin/env python3
"""v1.9.129: three fixes to v1.9.128.

1. (i) popovers: the "Per capita:" label takes the per capita glow colour (#E06A5A, the coral on
   tiles and the button), as "Adjust for inflation" and "Convert to USD$" take theirs.
   One CSS rule on each of the 62 country pages.
2. Map hint: phones only (style.css; no page markup changes).
3. Phone map card: tap to enlarge, shrinks by itself when scrolled off screen or on a tap elsewhere,
   no Collapse button, homepage and country pages alike (mobile.js, mobile.css).

The pages also request the new builds: style.css v63, mobile.css v48, mobile.js v45.

Idempotent: run twice, expect "74 changed" then "0 changed".
"""
import glob, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DOLLAR = ".infoPopoverToggleNote.dollar strong{color:var(--navy-2);}\n"
CAPITA = ".infoPopoverToggleNote.capita strong{color:#E06A5A;}   /* v1.9.129: per capita glow colour */\n"
BUMPS = [("style.css?v=62", "style.css?v=63"), ("mobile.css?v=47", "mobile.css?v=48"), ("mobile.js?v=44", "mobile.js?v=45")]


def main():
    changed = checked = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        s0 = s = open(f, encoding="utf-8").read()
        if not any(o in s or n in s for o, n in BUMPS) and "const INFO_CONTENT = {" not in s:
            continue
        checked += 1
        for old, new in BUMPS:
            if s.count(old) > 1:
                raise SystemExit(f"{os.path.basename(f)}: {old} found {s.count(old)} times")
            s = s.replace(old, new)
        if "const INFO_CONTENT = {" in s and CAPITA not in s:
            if s.count(DOLLAR) != 1:
                raise SystemExit(f"{os.path.basename(f)}: popover colour anchor found {s.count(DOLLAR)} times")
            s = s.replace(DOLLAR, DOLLAR + CAPITA)
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"{checked} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
