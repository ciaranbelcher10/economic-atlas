#!/usr/bin/env python3
"""v1.9.112 checks: Markets reserves each chart's space before it draws (shapes match the charts'
viewBoxes); the phone Home scroll-up "Jump to a country" bar is removed completely."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()
mc = read("mobile.css"); mj = read("mobile.js"); mk = read("markets.html")
cut = mc.index("@media (max-width:760px){"); g, ph = mc[:cut], mc[cut:]

# Markets: reserves match the viewBoxes the page draws (desktop and phone).
def vb(chart_id):
    m = re.search(r"#" + chart_id + r":empty\{ aspect-ratio:(\d+)/(\d+);", g); p = re.search(r"#" + chart_id + r":empty\{ aspect-ratio:(\d+)/(\d+);", ph)
    return (m.groups() if m else None, p.groups() if p else None)
for cid, desk, phone in (("cYields", ("900", "530"), ("360", "356")), ("cFx", ("520", "320"), ("360", "398")), ("cDaily", ("520", "300"), ("360", "250"))):
    d, p = vb(cid)
    check(d == desk, f"{cid} desktop reserve {d} (want {desk})")
    check(p == phone, f"{cid} phone reserve {p} (want {phone})")
# (the shapes were measured against the drawn charts in a browser at 7 widths; they are computed at runtime)
check("#cYields:empty{ aspect-ratio:900/530; margin-bottom:var(--mk-more-h, 0px); }" in g
      and "#cFx:empty{ aspect-ratio:520/320; margin-bottom:var(--mk-more-h, 0px); }" in g,
      "Show more button space must be a margin (border-box puts padding inside the ratio)")
check("#cYields, #cFx{ --mk-more-h:50px; }" in g and "#cYields, #cFx{ --mk-more-h:54px; }" in ph, "Show more heights 50/54px")
check("#mkYRegions:empty{ min-height:34px; }" in g, "region chips reserve")
check("#mkTicker:empty{ min-height:147px; }" in g and "@media (max-width:1180px){ #mkTicker:empty{ min-height:304px; } }" in g
      and "#mkTicker:empty{ min-height:82px; }" in ph, "ticker reserves 147/304/82px")
for idv in ("cYields", "cFx", "cDaily", "mkYRegions", "mkTicker"):
    check(re.search(r'id="' + idv + r'"[^>]*></div>', mk) is not None, f"markets.html #{idv} must start empty for :empty to apply")

# Scroll-up search bar removed completely.
for needle in ("initScrollCatch", "homeScrollCatch", "scrollCatch", "eatlas_scrollcatch_seen"):
    check(needle not in mj, f"mobile.js still mentions {needle}")
for needle in ("homeScrollCatch", "scrollCatch", ".sc-row", ".sc-results", ".sc-none"):
    check(needle not in mc, f"mobile.css still mentions {needle}")
check("function initHomeQuickNav" in mj or "homeQuickNav" in mj, "top search box must remain")

print(f"test_v19112: {checks} checks, {len(fails)} failed")
for f in fails[:20]: print("  FAIL", f)
sys.exit(1 if fails else 0)
