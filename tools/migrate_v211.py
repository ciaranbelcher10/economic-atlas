#!/usr/bin/env python3
"""v2.0.11 migration: bump the mobile.css and mobile.js cache-busters together on every page and in the
indicator page generator (mobile.css -> v=50, mobile.js -> v=48). Idempotent.
Run from the repo root: python3 tools/migrate_v211.py"""
import glob, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
changed = 0
files = [f for f in glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True) if os.sep + "_archive" + os.sep not in f]
files.append(os.path.join(ROOT, "generate_indicator_pages.py"))
for p in files:
    t = open(p, encoding="utf-8").read()
    t2 = re.sub(r"mobile\.css\?v=(?!50\b)\d+", "mobile.css?v=50", t)
    t2 = re.sub(r"mobile\.js\?v=(?!48\b)\d+", "mobile.js?v=48", t2)
    if t2 != t:
        open(p, "w", encoding="utf-8").write(t2); changed += 1
print(f"migrate_v211: {changed} files changed")
