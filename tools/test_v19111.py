#!/usr/bin/env python3
"""v1.9.111 checks (run after tools/migrate_v19111.py): layout-shift reserves, non-blocking font,
one main landmark per page, headline tile rows, tile names, contrast and tap-target fixes."""
import glob, math, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
FONT_URL = "https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700&display=swap"
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()

def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
def ratio(a, b):
    a, b = lum(a), lum(b); return (max(a, b) + 0.05) / (min(a, b) + 0.05)
def over(alpha, bg):  # white at alpha over bg
    return "#" + "".join("%02x" % round(alpha * 255 + (1 - alpha) * int(bg[i:i + 2], 16)) for i in (1, 3, 5))

# ---- pages -------------------------------------------------------------------------------
pages = []
for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
    n = os.path.basename(f)
    if n in GENERATED: continue
    s = open(f, encoding="utf-8").read()
    if FONT_URL in s: pages.append((n, s))
check(len(pages) >= 74, f"expected 74+ site pages with the font, found {len(pages)}")
for n, s in pages:
    blocking = re.findall(r'<link href="' + re.escape(FONT_URL) + r'" rel="stylesheet">', s)
    check(len(blocking) == 1 and '<noscript><link href="' + FONT_URL + '" rel="stylesheet"></noscript>' in s,
          f"{n}: font stylesheet must only block inside <noscript>")
    check(('media="print" onload="this.media=\'all\'"' in s) and ('rel="preload" as="style" href="' + FONT_URL in s),
          f"{n}: non-blocking font load missing")
    mains = s.count('role="main"') + len(re.findall(r"<main[\s>]", s))
    check(mains == 1, f"{n}: {mains} main landmarks (want 1)")
    i = s.find('role="main"')
    if i > 0: check(s.rfind("<nav", 0, i) < s.rfind("</nav>", 0, i) or s.rfind("<nav", 0, i) == -1, f"{n}: main landmark is inside a <nav>")
    if 'id="hero"' in s:
        rows = math.ceil(s.count("statTile(hero,") / 2)
        check(re.search(r'id="hero" aria-label="Headline figures" style="--hero-rows:\d+"', s) is not None,
              f"{n}: hero rows reserve present (v1.9.117 sets the count; see test_v19117)")
        check('title+", view chart"' not in s, f"{n}: tile aria-label override still present")
idx = read("index.html")
check('<span class="sl-full">' in idx and '<span class="sl-short">Official data for 62 economies.</span>' in idx,
      "index: both intro texts must ship in the page")
check("border-radius:6px; opacity:.75;}" not in idx, "index: zoom hint still at 75% opacity")
check("onload=\"this.media='all'\"" in read("generate_indicator_pages.py"), "generator: font still blocking")

# ---- chartmaker ----------------------------------------------------------------------------
cm = read("chartmaker.html")
body = cm.index("<body>")
check(re.search(r'<body>\n<script>[^<]*matchMedia\("\(max-width:760px\)"\)\.matches\)document\.body\.classList\.add\("cm-m"\)', cm) is not None,
      "chartmaker: phone class must be set right after <body>")
gate = cm.find('<div id="cmMobileGate">'); lay = cm.find('<div class="cm-layout show" id="cmLayout">')
check(body < gate < lay, "chartmaker: static gallery markup must sit just before the visible layout")
check('<button type="button" class="cm-m-send">' in cm and '<div class="cm-m-ex" role="group"' in cm,
      "chartmaker: gallery markup incomplete")
check("body:not(.cm-m) #cmMobileGate{display:none;}" in cm, "chartmaker: gallery must be hidden off phones")
check('<div class="wrap cm-wrap" role="main">' in cm, "chartmaker: main landmark on the page wrapper")

# ---- mobile.js -----------------------------------------------------------------------------
mj = read("mobile.js")
check("if(gate && gate.dataset.wired){" in mj and 'gate.dataset.wired = "1";' in mj and "if(!gate){" in mj,
      "mobile.js: gate must reuse the page's markup and wire it once")
check('if(el.querySelector(".sl-short")) return;' in mj, "mobile.js: intro swap must skip pages shipping both texts")

# ---- mobile.css ----------------------------------------------------------------------------
mc = read("mobile.css")
ph = mc[mc.index("@media (max-width:760px){"):]
glob_part = mc[:mc.index("@media (max-width:760px){")]
check("#homeQuickNav{ margin:0 0 6px; padding-top:10px;" in glob_part, "search box: padding, not a collapsing margin")
check(re.search(r"#homeQuickNav\{ margin-top:0 !important; padding-top:24px; \}", mc) is not None, "search box desktop: padding")
sp = re.findall(r'\.wrap:has\(> header\.page > \.hero-h1\):not\(:has\(> #homeQuickNav\)\)::before\{ (?:content:""; display:block; )?height:(\d+)px; \}', mc)
check(sp == ["62", "76"], f"search box spacer heights {sp} (want 62 then 76 for >900px)")
check("header.page:has(> .hero-h1):not(:has(#homeTicker)) > .subline{ padding-bottom:57px; }" in glob_part
      and "header.page:has(> .hero-h1):not(:has(#homeTicker)) > .subline{ padding-bottom:60px; }" in ph,
      "ticker reserve 57px desktop / 60px phone")
check("nav.cat:not(:has(+ .sec-swipehint)){ margin-bottom:55px !important; }" in ph, "swipe dots reserve")
check("#hero:empty{ min-height:max(0px, calc(var(--hero-rows, 0) * 176px + (var(--hero-rows, 0) - 1) * 8px)); }" in ph,
      "hero tile reserve")
check("body.cm-m .cm-chart-outer{ min-height:300px; }" in ph, "chartmaker chart reserve")
check("body:has(> nav.top) h1.hero-h1{" in ph and "body.mob-tabbar h1" not in mc, "phone heading size from first paint")
check(".subline .sl-short{ display:none; }" in glob_part and ".subline .sl-full{ display:none; } .subline .sl-short{ display:inline; }" in ph,
      "intro text per width")
m = re.search(r"#mobToolbar a\{[^}]*color:rgba\(255,255,255,(\.\d+)\)", mc)
check(m is not None and ratio(over(float(m.group(1)), "#2a5a82"), "#2a5a82") >= 4.5, "toolbar text contrast >= 4.5")
check("body .rangepresets button.active{ color:#0b1d2c; }" in glob_part, "active range button dark text")
for sel in ['.cm-m-chip[aria-pressed="true"]{', ".cm-m-send{"]:
    i = mc.find("  " + sel); check(i > 0 and "color:#0b1d2c;" in mc[i:mc.index("}", i)], f"{sel} dark text")
for bg in ("#5CA8DE", "#4796CE"):
    check(ratio("#0b1d2c", bg) >= 4.5, f"dark text on {bg} contrast")
check("width:24px !important; height:24px !important;" in mc[mc.index(".hero .stat .statPageLink{"):][:200],
      "stat page links 24px")

print(f"test_v19111: {checks} checks, {len(fails)} failed")
for f in fails[:25]: print("  FAIL", f)
sys.exit(1 if fails else 0)
