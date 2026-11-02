#!/usr/bin/env python3
"""v1.9.63: the banner logo and site name are larger on every page.

Checks style.css sets the logo to 34px and the name to 20px (30px / 18px on
phones), and that every root page's banner is the shared .brand link with the
logo image inside it, so the one stylesheet rule reaches all of them.
Run: python3 tools/test_brand_size.py
"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails, oks = [], 0
def check(cond, msg):
    global oks
    if cond: oks += 1
    else: fails.append(msg)

css = open(os.path.join(ROOT, "style.css"), encoding="utf-8").read()
brand = re.search(r"nav \.brand\{([^}]*)\}", css)
check(brand and re.search(r"font-size:20px", brand.group(1)), "desktop name is 20px")
check(re.search(r"nav \.brand img\{width:34px; height:34px;\}", css), "desktop logo is 34px")
phone = re.search(r"@media \(max-width:640px\)\{ nav \.brand\{font-size:18px;\} nav \.brand img\{width:30px; height:30px;\} \}", css)
check(phone, "phone name 18px and logo 30px")

pages = [p for p in glob.glob(os.path.join(ROOT, "*.html")) + glob.glob(os.path.join(ROOT, "indicators", "*.html"))]
for p in pages:
    h = open(p, encoding="utf-8").read()
    if 'class="brand"' not in h: continue
    m = re.search(r'<a class="brand"[^>]*>(.*?)</a>', h, re.S)
    check(m and "<img" in m.group(1) and "The Economic Atlas" in m.group(1), os.path.relpath(p, ROOT) + ": banner has logo and name inside .brand")
    check(re.search(r'href="(\.\./)?style\.css', h), os.path.relpath(p, ROOT) + ": loads style.css")

for f in fails: print("FAIL", f)
print(f"test_brand_size: {oks} ok, {len(fails)} failed")
sys.exit(1 if fails else 0)
