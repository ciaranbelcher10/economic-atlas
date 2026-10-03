#!/usr/bin/env python3
"""Every indicator page's preview image exists (v1.6.40).

Run after generate_indicator_pages.py and generate_og_images.py. Fails when
a page's og:image points at a file missing from og/ (v1.6.38 added 32 pages
whose cards were never drawn, because generate_og_images.py did not see
the derived series).
    python3 tools/og_gate.py    # "N pages, all with a preview image"
"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
pages = sorted(f for f in os.listdir("indicators") if f.endswith(".html") and f != "index.html")
missing = []
for f in pages:
    h = open(os.path.join("indicators", f), encoding="utf-8").read(6000)
    m = re.search(r'property="og:image" content="https://theeconomicatlas\.com/(og/[^"]+)"', h) or \
        re.search(r'og:image" content="https://theeconomicatlas\.com/(og/[^"]+)"', h)
    if m and not os.path.exists(m.group(1)):
        missing.append(f"{f} -> {m.group(1)}")
for x in missing[:20]:
    print("MISSING", x)
print(f"{len(pages)} pages, {len(missing)} without a preview image" if missing else f"{len(pages)} pages, all with a preview image")
sys.exit(1 if missing else 0)
