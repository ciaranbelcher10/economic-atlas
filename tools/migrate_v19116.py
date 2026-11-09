#!/usr/bin/env python3
"""v1.9.116 country pages (GDP section): GDP per capita chart and tile; Population moved to the
end of the GDP tiles (v1.9.115 put it first). Order at the end of the section: ... GDP per capita,
Population. Page edit at deploy (the bot rewrites country pages); idempotent.
Run from the repo root:  python3 tools/migrate_v19116.py   (exits 1 if a page is left wrong)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
MARK = "/* v1.9.116 gdp per capita */"
TG = '  const tg=document.getElementById("tiles-gdp");\n'
TINF = '  const tinf=document.getElementById("tiles-inflation");\n'
POP_CHART = '  /* v1.9.115 population */\n'
import re
# The v1.9.115 Population tile, found by pattern and moved verbatim (never retyped).
POP_TILE_RE = re.compile(r'  if\(s\.population\) statTile\(tg,"population".*?\n    tg\.appendChild\(na\); \}\n', re.S)
GPC_CHART = (
    "  " + MARK + "\n"
    "  const perHeadSym=u=>curFmt(1,u+\"m\",0).replace(/^\\u2212/,\"\").replace(/1m$/,\"\");\n"
    "  const fmtPerHead=v=>{const g=v<0?\"\\u2212\":\"\";return g+perHeadSym(s.gdp_per_capita?s.gdp_per_capita.unit:\"\")+Math.round(Math.abs(v)).toLocaleString(\"en-GB\");};\n"
    "  if(s.gdp_per_capita) chartPanel(\"gdp_per_capita\",\"charts-gdp\",\"GDP per capita\",\n"
    "    \"The economy's output in a full calendar year divided by the number of people living there that year.\",\n"
    "    s.gdp_per_capita,\"line\",fmtPerHead,fmtPerHead,\"Calculated: complete calendar years of GDP divided by that year's population (World Bank)\");\n")
GPC_TILE = (
    "  if(s.gdp_per_capita) statTile(tg,\"gdp_per_capita\",\"GDP per capita\",s.gdp_per_capita,\n"
    "    {fmt:fmtPerHead,fmtD:fmtPerHead,upIsGood:true,source:\"GDP \\u00f7 World Bank population\"});\n")
SLUGS = "const INDICATOR_PAGE_SLUGS = {"
CK_OLD = 'const CURRENCY_KEYS = ["gdp_level","gdp_real","net_debt","deficit","debt_interest","trade_balance","exports","imports"];'
CK_NEW = 'const CURRENCY_KEYS = ["gdp_level","gdp_real","net_debt","deficit","debt_interest","trade_balance","exports","imports","gdp_per_capita"];'
CONV_ANCHOR = """        out[k] = isReal ? convertRealSeriesToUSD(out[k], fx) : convertSeriesToUSD(out[k], fx);
      }
    });
  }
  return out;
}
"""
CONV_NEW = """        out[k] = isReal ? convertRealSeriesToUSD(out[k], fx) : convertSeriesToUSD(out[k], fx);
      }
    });
  }
  /* v1.9.116: GDP per capita (whole currency units per person) converts with GDP, at each
     year's rate, and is already in US$ exactly when this country's GDP is. */
  if(TOGGLE_STATE.dollar && PAGE_DATA.fx_to_usd && out.gdp_per_capita){
    const gu = ((PAGE_DATA.series||{}).gdp_level||{}).unit || "";
    if(isCurrencyUnit(gu) && !isAlreadyUSD(gu, "gdp_level") && !foreignCurrencyOf(gu, PAGE_DATA.fx_to_usd))
      out.gdp_per_capita = {...convertSeriesToUSD(out.gdp_per_capita, PAGE_DATA.fx_to_usd), unit:"$"};
  }
  return out;
}
"""

def migrate(s):
    if MARK in s or POP_CHART not in s or TINF not in s or SLUGS not in s:
        return s
    m = POP_TILE_RE.search(s)
    if not m or s.find(TG) + len(TG) != m.start():
        return s                                               # not the v1.9.115 layout: leave alone
    pop_tile = m.group(0)
    s = s[:m.start()] + s[m.end():]                           # take Population out of first place
    s = s.replace(TINF, GPC_TILE + pop_tile + TINF, 1)        # ... and put it last, after GDP per capita
    s = s.replace(POP_CHART, GPC_CHART + POP_CHART, 1)        # GDP per capita chart before Population's
    s = s.replace(SLUGS, SLUGS + 'gdp_per_capita:"gdp-per-capita", ', 1)
    s = s.replace(CK_OLD, CK_NEW, 1)
    s = s.replace(CONV_ANCHOR, CONV_NEW, 1)      # every page but the US (its GDP is already US$)
    return s

def problems(s):
    out = []
    if MARK not in s: out.append("not migrated")
    if s.count('statTile(tg,"population"') != 1 or s.count('statTile(tg,"gdp_per_capita"') != 1: out.append("tile counts")
    i_pop, i_gpc, i_inf = s.find('statTile(tg,"population"'), s.find('statTile(tg,"gdp_per_capita"'), s.find(TINF)
    if not (0 < i_gpc < i_pop < i_inf): out.append("order: GDP per capita, then Population, at the end of the GDP tiles")
    if s.find(TG + '  if(s.population) statTile(tg,"population"') != -1: out.append("Population still first")
    if 'gdp_per_capita:"gdp-per-capita", ' not in s: out.append("slug map")
    if CK_NEW not in s: out.append("CURRENCY_KEYS")
    return out

def main():
    changed, bad = 0, []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        n = os.path.basename(f)
        if n in GENERATED: continue
        s = open(f, encoding="utf-8").read()
        if 'id="tiles-gdp"' not in s: continue
        new = migrate(s)
        if new != s: open(f, "w", encoding="utf-8").write(new); changed += 1
        bad += [n + ": " + p for p in problems(new)]
    print(f"migrate_v19116: {changed} page(s) changed")
    if bad: print("migrate_v19116: FAIL\n  " + "\n  ".join(bad[:20])); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
