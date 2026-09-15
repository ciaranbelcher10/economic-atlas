#!/usr/bin/env python3
"""
Workstream 3 harness: extract a named IIFE or function from a page and run it
under Node with a stubbed DOM, so failure branches can actually be exercised
rather than read.

Usage: python3 run_surface.py <page.html> <symbol>
Writes the extracted source to scratch/_extracted.js and prints it.
"""
import re, sys, os

import os as _os
REPO = _os.environ.get("ATLAS_REPO") or _os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))


def extract_iife(src, symbol):
    """Grab `window.SYMBOL = (function(){ ... })();` by brace matching."""
    m = re.search(r"window\.%s\s*=\s*\(function\s*\(\s*\)\s*\{" % re.escape(symbol), src)
    if not m:
        return None
    i = src.index("{", m.end() - 1)
    depth, j = 0, i
    in_s, esc, q = False, False, ""
    while j < len(src):
        ch = src[j]
        if in_s:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == q:
                in_s = False
        else:
            if ch in "\"'`":
                in_s, q = True, ch
            elif ch == "/" and src[j:j+2] == "//":
                j = src.index("\n", j)
            elif ch == "/" and src[j:j+2] == "/*":
                j = src.index("*/", j) + 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
        j += 1
    tail = src[j:j+40]
    end = j + tail.index(";") + 1 if ";" in tail else j + 1
    return src[m.start():end]


if __name__ == "__main__":
    page, symbol = sys.argv[1], sys.argv[2]
    src = open(os.path.join(REPO, page), encoding="utf-8").read()
    code = extract_iife(src, symbol)
    if not code:
        print(f"could not locate window.{symbol} in {page}")
        sys.exit(1)
    out = os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_extracted.js")
    open(out, "w", encoding="utf-8").write(code)
    print(f"extracted {len(code)} bytes of window.{symbol} from {page} -> {out}")
    print(f"lines: {code.count(chr(10))+1}")
