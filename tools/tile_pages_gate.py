#!/usr/bin/env python3
"""Every tile on every country page has its own indicator page (v1.6.38).

For each statTile() call that renders with the current data, the tile's page
key (opts.pageKey, else its key) must be in that page's INDICATOR_PAGE_SLUGS
and the page indicators/<country>-<slug>.html must exist. A tile with no page
key at all fails. Run after generate_indicator_pages.py.

    python3 tools/tile_pages_gate.py     # "N tiles, all with a page", exit 0
"""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import generate_indicator_pages as g

DERIVED_VARS = {"gdpYoY": "gdp_growth_yoy", "ti": "trade_intensity"}
src_all = json.load(open("data-metric-sources.json", encoding="utf-8"))
call = re.compile(r'if\(([^)]*)\)\s*statTile\(\s*\w+\s*,\s*("\w+"|null)\s*,\s*"([^"]+)"\s*,\s*([^,]+),\s*\{([^}]*)\}')
tiles = fails = 0
for country, (iso2, cslug, a2, reg) in g.COUNTRIES.items():
    page = f"{cslug}.html"
    if not os.path.exists(page):
        continue
    h = open(page, encoding="utf-8").read()
    m = re.search(r"const INDICATOR_PAGE_SLUGS = \{([^}]*)\}", h)
    slugs = dict(re.findall(r'(\w+):"([^"]+)"', m.group(1))) if m else {}
    data = json.load(open(g.data_file_for(iso2), encoding="utf-8"))
    dd, _ = g.add_derived(country, data, src_all.get(country, {}))
    have = set(dd["series"])
    for cond, key, title, arg, opts in call.findall(h):
        needed = re.findall(r"s\.(\w+)", cond) + [DERIVED_VARS[v] for v in re.findall(r"\b(\w+)\b", cond) if v in DERIVED_VARS]
        if needed and not all(n in have for n in needed):
            continue  # tile does not render for this country
        tiles += 1
        pk = re.search(r'pageKey:"(\w+)"', opts)
        k = pk.group(1) if pk else key.strip('"')
        if k == "null":
            fails += 1; print(f"FAIL {country}: tile '{title}' has no page key"); continue
        slug = slugs.get(k)
        if not slug:
            fails += 1; print(f"FAIL {country}: tile '{title}' key {k} not in INDICATOR_PAGE_SLUGS"); continue
        if not os.path.exists(f"indicators/{cslug}-{slug}.html"):
            fails += 1; print(f"FAIL {country}: tile '{title}' -> indicators/{cslug}-{slug}.html missing")
print(f"{tiles} tiles, {fails} without a page" if fails else f"{tiles} tiles, all with a page")
sys.exit(1 if fails else 0)
