#!/usr/bin/env python3
"""v1.9.117 country pages (62): Headline = the first 10 of one priority list the country has;
new Miscellaneous section (FDI, Business confidence, Population: tiles and charts); no "++".

Headline priority (decided 9 Nov 2026):
   1 GDP  2 GDP growth  3 CPI  4 Unemployment  5 Policy rate  6 10-year yield  7 Debt % GDP
   8 Exchange rate vs US$  9 Current account  10 Trade balance
   backfill: 11 GDP per capita  12 Core inflation  13 Employment rate  14 Budget balance
             15 Real GDP growth, year on year
Each tile is the page's OWN existing tile statement (Headline first, else its section tile),
lifted verbatim and re-targeted at the Headline: labels, formats and sources never retyped.
FDI and Business confidence leave the Headline; their charts move from Headline to
Miscellaneous; Population's tile and chart move from GDP to Miscellaneous.
Page edit at deploy (the bot rewrites country pages); idempotent.
Run from the repo root:  python3 tools/migrate_v19117.py   (exits 1 if a page is left wrong)"""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
MARK = "/* v1.9.117 headline */"
HERO = '  const hero=document.getElementById("hero");\n'
FX_LINE = '  renderFxMarkets(document.getElementById("tiles-markets"));\n'
PRIORITY = [  # (group, candidate keys in preference order)
    ("gdp", ["gdp_level"]), ("growth", ["gdp_growth"]), ("cpi", ["cpi", "cpi_national"]),
    ("unemployment", ["unemployment"]),
    ("policy", ["boe_rate", "fed_funds", "ecb_rate", "boj_rate", "overnight_rate", "policy_rate"]),
    ("bond", ["bond_yield_10y"]), ("debt", ["debt_gdp"]), ("fx", ["@fx"]),
    ("ca", ["current_account"]), ("trade", ["trade_balance"]),
    ("gpc", ["gdp_per_capita"]), ("core", ["core_cpi"]), ("emp", ["employment_rate", "employment"]),
    ("deficit", ["deficit"]), ("yoy", ["gdp_growth_yoy"]),
]
MISC = ["fdi", "business_confidence"]

def _match(s, i, open_ch, close_ch):
    """Index just past the bracket closing the one at s[i]; skips strings and template literals."""
    depth, j, q = 0, i, None
    while j < len(s):
        c = s[j]
        if q:
            if c == "\\": j += 2; continue
            if c == q: q = None
        elif c in "\"'`": q = c
        elif c == open_ch: depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0: return j + 1
        j += 1
    raise ValueError("unbalanced")

def statements(s, lo, hi):
    """Tile statements in s[lo:hi]: `  if(COND) statTile(...);` or `  if(COND){ ... statTile ... }`.
    Returns dicts: start, end, cond, body, container, key."""
    out, i = [], lo
    rx = re.compile(r"^  if\(", re.M)
    while True:
        m = rx.search(s, i, hi)
        if not m: break
        a = m.start()                                 # s[a+4] is the "(" of if(
        try: c_end = _match(s, a + 4, "(", ")")
        except ValueError: i = m.end(); continue
        cond = s[a + 5:c_end - 1]
        k = c_end
        while s[k] == " ": k += 1
        if s[k] == "{":
            b_end = _match(s, k, "{", "}")
            body = s[k + 1:b_end - 1]; end = b_end
        else:
            if not s.startswith("statTile(", k): i = m.end(); continue
            call_end = _match(s, k + 8, "(", ")")
            if s[call_end] != ";": i = m.end(); continue
            body = s[k:call_end + 1]; end = call_end + 1
        if s[end] == "\n": end += 1
        t = re.search(r"statTile\((\w+),(null|\"([a-z_0-9]+)\")", body)
        if not t or "else" in s[end:end + 8]: i = end; continue
        key = t.group(3)
        if key is None:
            pk = re.search(r'pageKey:"([a-z_0-9]+)"', body); key = pk.group(1) if pk else None
        out.append(dict(start=a, end=end, cond=cond, body=body, container=t.group(1), key=key))
        i = end
    return out

def retarget(body, container, new):
    return body.replace("statTile(" + container + ",", "statTile(" + new + ",")

FX_HELPER = r'''
/* v1.9.117: the Headline's exchange-rate tile: the home currency's pair against the US dollar
   (absent for the US itself), drawn exactly as renderFxMarkets() draws it in Markets. */
function headlineFxPair(){
  if(!FX_DATA || !Array.isArray(FX_DATA.pairs)) return null;
  return FX_DATA.pairs.find(p=>p && p.quote==="USD" && Array.isArray(p.points) && p.points.length>=2) || null;
}
function renderFxHeadline(el){
  const p=headlineFxPair(); if(!p) return;
  const q=p.quote_symbol, b=p.base_unit;
  const daily=Array.isArray(p.daily) && p.daily.length>=2;
  const ts=daily ? {points:p.daily,freq:"days",confirmed_at:p.confirmed_at} : {points:p.points,freq:p.freq,confirmed_at:p.confirmed_at};
  const prevV=ts.points[ts.points.length-2][1];
  statTile(el,p.key,p.title,ts,
    {fmt:v=>q+fxNum(v)+'<span class="fxper">per '+b+'</span>',
     fmtD:v=>{const pc=prevV ? v/prevV*100 : 0; return (Math.abs(pc)<0.005?"":(pc<0?"\u2212":"+"))+Math.abs(pc).toFixed(2)+"%";},dDp:8,
     upIsGood:true,signed:true,source:p.source_short,
     vsText:daily?"vs prior day":(p.freq==="years"?"vs prior year":"vs prior month")});
}
'''
DELTA_OLD = '${dShow>0&&!opts.signed?"+":""}${tileNum(opts.fmtD(dShow))}'
DELTA_NEW = '${(d=>((dShow>0&&!opts.signed&&String(d).charAt(0)!=="+")?"+":"")+tileNum(d))(opts.fmtD(dShow))}'
NAV_OLD = ' <button data-sec="markets">Markets</button>\n'
NAV_NEW = NAV_OLD + ' <button data-sec="misc">Miscellaneous</button>\n'
SEC_HTML = ('<section class="sec" id="sec-misc" hidden>\n <div class="hero mini" id="tiles-misc"></div>\n'
            ' <div class="grid" id="charts-misc"></div>\n'
            ' <p class="secnote">Foreign direct investment, business confidence and population: useful context that sits outside the headline figures.</p>\n</section>\n')
POP_TILE_RE = re.compile(r'  if\(s\.population\) statTile\(tg,"population".*?\n    tg\.appendChild\(na\); \}\n', re.S)

def migrate(s):
    if MARK in s: return s
    a = s.index(HERO); fx = s.index(FX_LINE)
    st = statements(s, a, fx)
    hero = {x["key"]: x for x in st if x["container"] == "hero" and x["key"]}
    sect = {}
    for x in st:
        if x["container"] != "hero" and x["key"] and x["key"] not in sect: sect[x["key"]] = x
    def src(k):
        if k in hero: return hero[k]["cond"], retarget(hero[k]["body"], "hero", "hero")
        if k in sect: return sect[k]["cond"], retarget(sect[k]["body"], sect[k]["container"], "hero")
        return None
    entries = []
    for g, keys in PRIORITY:
        if keys == ["@fx"]:
            entries.append(f"    // {g}\n    [()=>!!headlineFxPair(), ()=>renderFxHeadline(hero)],\n"); continue
        alts = [(k, src(k)) for k in keys if src(k)]
        if not alts: continue
        ok = " || ".join(f"({c})" for _, (c, _b) in alts)
        draw = " else ".join(f"if({c}){{\n      {b.strip()}\n    }}" for _, (c, b) in alts)
        entries.append(f"    // {g}\n    [()=>!!({ok}), ()=>{{\n    {draw}\n    }}],\n")
    misc = []
    for k in MISC:
        if k in hero: misc.append(f"  if({hero[k]['cond']}) {retarget(hero[k]['body'], 'hero', 'tmisc').strip()}\n")
    # remove every Headline statement (rebuilt below), last first so offsets hold
    for x in sorted([x for x in st if x["container"] == "hero"], key=lambda x: -x["start"]):
        s = s[:x["start"]] + s[x["end"]:]
    # Population tile: GDP section -> Miscellaneous
    m = POP_TILE_RE.search(s)
    pop = ""
    if m:
        pop = m.group(0).replace("statTile(tg,", "statTile(tmisc,").replace("else if(tg){", "else if(tmisc){").replace("tg.appendChild(na)", "tmisc.appendChild(na)")
        s = s[:m.start()] + s[m.end():]
    block = ("  " + MARK + "\n"
             "  // Miscellaneous: FDI, Business confidence, Population\n"
             '  const tmisc=document.getElementById("tiles-misc");\n' + "".join(misc) + pop +
             "  // Headline: the first 10 of one priority list (see tools/migrate_v19117.py)\n"
             "  const HEADLINE_TILES=[\n" + "".join(entries) + "  ];\n"
             "  {let n=0; for(const [ok,draw] of HEADLINE_TILES){ if(n>=10) break; if(ok()){ draw(); n++; } }}\n")
    s = s.replace(FX_LINE, FX_LINE + block, 1)
    # charts
    for k in ("fdi", "business_confidence"):
        s = s.replace(f'chartPanel("{k}","charts-headline"', f'chartPanel("{k}","charts-misc"', 1)
    s = s.replace('chartPanel("population","charts-gdp"', 'chartPanel("population","charts-misc"', 1)
    # section, nav, SEC_OF, helper, delta
    s = s.replace(NAV_OLD, NAV_NEW, 1)
    i = s.index('<section class="sec" id="sec-markets" hidden>'); j = s.index("</section>\n", i) + len("</section>\n")
    s = s[:j] + SEC_HTML + s[j:]
    s = s.replace('"charts-markets":"markets"', '"charts-markets":"markets","charts-misc":"misc"', 1)
    s = s.replace("function renderFxMarkets(tm){", FX_HELPER.lstrip("\n") + "function renderFxMarkets(tm){", 1)
    s = s.replace(DELTA_OLD, DELTA_NEW, 1)
    # phones reserve the Headline's height before it renders (v1.9.111): rows of two tiles
    n = min(10, len(entries))
    s = re.sub(r'(id="hero" aria-label="Headline figures" style="--hero-rows:)\d+(")', lambda m: m.group(1) + str((n + 1) // 2) + m.group(2), s, count=1)
    return s

def problems(s):
    out = []
    for need in (MARK, NAV_NEW, 'id="sec-misc"', '"charts-misc":"misc"', "function renderFxHeadline(", DELTA_NEW, "const HEADLINE_TILES=["):
        if need not in s: out.append("missing " + need[:40].strip())
    if re.search(r"statTile\(hero,", s.split(MARK)[0]): out.append("Headline tile left outside the priority list")
    for k in ("fdi", "business_confidence"):
        if f'chartPanel("{k}","charts-headline"' in s: out.append(k + " chart still in Headline")
    if 'chartPanel("population","charts-gdp"' in s or 'statTile(tg,"population"' in s: out.append("population still in GDP")
    if DELTA_OLD in s: out.append("double-sign delta")
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
    print(f"migrate_v19117: {changed} page(s) changed")
    if bad: print("migrate_v19117: FAIL\n  " + "\n  ".join(bad[:25])); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
