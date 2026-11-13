#!/usr/bin/env python3
"""v1.9.127: the "Latest:" banner no longer pushes the page down when it appears.

generate_indicator_pages.py marks the banner data-expect when the hourly run sees a fresh release, and
style.css reserves its row from the first paint. This migration makes each country page's
renderNewDataBanner() drop that mark first, in the same task as filling the banner, so the reserved
row either fills in place or (nothing fresh any more) collapses before anything is painted with it.

Idempotent: run twice, expect "62 changed" then "0 changed".
"""
import glob, os, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MARK = "v1.9.127 newdata reserve"
OLD = "function renderNewDataBanner(meta){\n  if(!meta) return;"
NEW = ("function renderNewDataBanner(meta){\n"
       "  /* " + MARK + ": the reserved row (data-expect) is either filled below or released now */\n"
       "  const _nd=document.getElementById(\"newdata\"); if(_nd) _nd.removeAttribute(\"data-expect\");\n"
       "  if(!meta) return;")


def main():
    pages = sorted(f for f in glob.glob(os.path.join(ROOT, "*.html")) if "function renderNewDataBanner(meta){" in open(f, encoding="utf-8").read())
    changed = 0
    for f in pages:
        s = open(f, encoding="utf-8").read()
        if MARK in s:
            continue
        if s.count(OLD) != 1:
            raise SystemExit(f"{os.path.basename(f)}: anchor found {s.count(OLD)} times")
        open(f, "w", encoding="utf-8").write(s.replace(OLD, NEW))
        changed += 1
    print(f"{len(pages)} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
