#!/usr/bin/env python3
"""v1.9.117 checks: Headline = first 10 of the priority list (each page's own tiles), Miscellaneous
section (FDI, Business confidence, Population: tiles and charts), no "++", uniform tiles."""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import migrate_v19117 as M  # noqa: E402
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()

ORDER = ["gdp", "growth", "cpi", "unemployment", "policy", "bond", "debt", "fx", "ca", "trade", "gpc", "core", "emp", "deficit", "yoy"]
check([g for g, _ in M.PRIORITY] == ORDER, "priority list is the agreed order (exchange rate 8th, budget balance in backfill)")
GEN = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html", "unemployment-by-country.html", "data-status.html"}
pages = [f for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))) if os.path.basename(f) not in GEN and 'id="tiles-gdp"' in open(f, encoding="utf-8").read()]
check(len(pages) >= 62, "62 country pages")
for f in pages:
    s = open(f, encoding="utf-8").read(); n = os.path.basename(f)
    i = s.find(M.MARK); j = s.find("  ];\n", i)
    check(i > 0 and j > i, f"{n}: Headline block present"); 
    if i < 0 or j < 0: continue
    groups = re.findall(r"^    // ([a-z]+)\n", s[i:j], re.M)
    check(groups == [g for g in ORDER if g in groups], f"{n}: Headline groups in priority order ({groups})")
    check("fx" in groups, f"{n}: exchange rate in the Headline list (the US finds no US$ pair at runtime and skips it)")
    check("{let n=0; for(const [ok,draw] of HEADLINE_TILES){ if(n>=10) break; if(ok()){ draw(); n++; } }}" in s, f"{n}: at most 10, first available")
    before = s[:i]
    check(not re.search(r"statTile\(hero,", before), f"{n}: no Headline tile outside the list")
    check(not re.search(r'statTile\(hero,"(fdi|business_confidence|population)"', s), f"{n}: FDI, confidence and population not in the Headline")
    check(all(f'chartPanel("{k}","charts-headline"' not in s for k in ("fdi", "business_confidence")), f"{n}: their charts left the Headline")
    for k in ("fdi", "business_confidence"):
        if f'chartPanel("{k}",' in s: check(f'chartPanel("{k}","charts-misc"' in s, f"{n}: {k} chart in Miscellaneous")
    check('chartPanel("population","charts-misc"' in s and 'statTile(tmisc,"population"' in s, f"{n}: population chart and tile in Miscellaneous")
    check('statTile(tg,"population"' not in s and 'chartPanel("population","charts-gdp"' not in s, f"{n}: population left GDP")
    check(' <button data-sec="markets">Markets</button>\n <button data-sec="misc">Miscellaneous</button>\n' in s, f"{n}: Miscellaneous tab after Markets")
    check('<section class="sec" id="sec-misc" hidden>' in s and '"charts-misc":"misc"' in s, f"{n}: Miscellaneous section wired")
    check(M.DELTA_NEW in s and M.DELTA_OLD not in s, f"{n}: tile deltas never show ++")
    m = re.search(r'aria-label="Headline figures" style="--hero-rows:(\d+)"', s)
    check(bool(m) and int(m.group(1)) == (min(10, len(groups)) + 1) // 2, f"{n}: phone reserve matches the Headline rows")
mc = read("mobile.css")
check("body .hero, body .hero.mini{ display:grid !important; grid-template-columns:repeat(5,minmax(0,1fr)); grid-auto-rows:1fr;" in mc, "desktop: five equal tiles per row, equal rows")
check("body .hero, body .hero.mini{ grid-auto-rows:176px; }" in mc and "height:176px;" in mc, "phone: every tile 176px")
check("* 176px + (var(--hero-rows, 0) - 1) * 8px" in mc and "* 143px" not in mc, "phone reserve uses the same 176px")
print(f"test_v19117: {checks} checks, {len(fails)} failed")
for x in fails[:20]: print("  FAIL", x)
sys.exit(1 if fails else 0)
