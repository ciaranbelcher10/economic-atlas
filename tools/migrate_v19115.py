#!/usr/bin/env python3
"""v1.9.115: population on every country page (GDP section): a chart and a tile, from the
"population" series that merge_population.py adds to each data file. A page whose data has no
population (Taiwan: the World Bank does not publish it) shows a "Not available" tile instead.
Page edit at deploy (the bot rewrites country pages); idempotent.
Run from the repo root:  python3 tools/migrate_v19115.py   (exits 1 if a page is left without it)"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
ANCHOR = '  const tg=document.getElementById("tiles-gdp");\n'
MARK = "/* v1.9.115 population */"
BLOCK = (
    "  " + MARK + "\n"
    "  const fmtPeople=v=>{const a=Math.abs(v),g=v<0?\"\\u2212\":\"\";return g+(a>=1e9?(a/1e9).toFixed(2)+\"bn\":a>=1e6?(a/1e6).toFixed(1)+\"m\":a>=1e3?(a/1e3).toFixed(0)+\"k\":a.toFixed(0));};\n"
    "  if(s.population) chartPanel(\"population\",\"charts-gdp\",\"Population\",\n"
    "    \"The total number of people living in the economy at mid-year.\",\n"
    "    s.population,\"line\",fmtPeople,fmtPeople,\"World Bank \\u00b7 Population, total (SP.POP.TOTL), mid-year estimates, annual\");\n"
)
TILE_ANCHOR_RE = re.compile(r'(  const tg=document\.getElementById\("tiles-gdp"\);\n)')
TILE = (
    "  if(s.population) statTile(tg,\"population\",\"Population\",s.population,\n"
    "    {fmt:fmtPeople,fmtD:fmtPeople,upIsGood:true,source:\"World Bank \\u00b7 SP.POP.TOTL\"});\n"
    "  else if(tg){ const na=document.createElement(\"div\"); na.className=\"stat stat-na\";\n"
    "    na.innerHTML='<p class=\"label\">Population</p><p class=\"figure\">Not available</p>'\n"
    "      +'<p class=\"delta\">The World Bank does not publish a population figure for this economy.</p>';\n"
    "    tg.appendChild(na); }\n"
)

SLUGS = "const INDICATOR_PAGE_SLUGS = {"

def migrate(s):
    if MARK in s or ANCHOR not in s or SLUGS not in s:
        return s
    s = s.replace(SLUGS, SLUGS + 'population:"population", ', 1)
    return s.replace(ANCHOR, BLOCK + ANCHOR + TILE, 1)

def main():
    changed, bad = 0, []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        n = os.path.basename(f)
        if n in GENERATED: continue
        s = open(f, encoding="utf-8").read()
        if 'id="tiles-gdp"' not in s: continue
        new = migrate(s)
        if new != s: open(f, "w", encoding="utf-8").write(new); changed += 1
        if MARK not in new or new.count('statTile(tg,"population"') != 1 or 'INDICATOR_PAGE_SLUGS = {population:"population", ' not in new: bad.append(n)
    print(f"migrate_v19115: {changed} page(s) changed")
    if bad: print("migrate_v19115: FAIL " + ", ".join(bad)); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
