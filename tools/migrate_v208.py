#!/usr/bin/env python3
"""v2.0.8 migration: square bars sitewide. Idempotent.
Every Chart.js bar dataset's borderRadius becomes 0 on each root page (country pages, Dashboard and
the rest), and dashboard.html loads chooser.js?v=3. chartmaker.html, compare.html and chooser.js
ship whole in the package. Run from the repo root: python3 tools/migrate_v208.py"""
import glob, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
changed = []
for p in sorted(glob.glob(os.path.join(ROOT, "*.html")) + glob.glob(os.path.join(ROOT, "*.js"))):
    t = open(p, encoding="utf-8").read()
    t2 = re.sub(r"borderRadius:(\s*)[1-9]\d*", r"borderRadius:\g<1>0", t)
    if os.path.basename(p) == "dashboard.html":
        t2 = t2.replace("chooser.js?v=2", "chooser.js?v=3")
    if t2 != t:
        open(p, "w", encoding="utf-8").write(t2); changed.append(os.path.basename(p))
print(f"migrate_v208: {len(changed)} files changed")
