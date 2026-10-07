#!/usr/bin/env python3
"""Generate a new country's page from its spec, its data file and its citations.

    python3 tools/build_country_page.py tools/country_specs/my.json [--force]

Template: china.html, the most recently built page (v1.7.x: shrink-to-fit
tiles, ISO currency glyphs, LPR-style labelled rates, Make-it-real source
switch). Everything country-specific is regenerated, never hand-edited:

  * render(): built from CATALOG below, ONLY for keys the data file serves,
    so a tile or chart can never point at a series that does not exist, and
    every served key gets a tile and a chart (coverage_gate.js checks).
    A served key missing from CATALOG stops the build: decide where it goes.
  * INFO_CONTENT: copied verbatim from data-metric-sources.json[name], so the
    (i) panel and the popover can never drift (citation_provider.py checks).
  * Chart explanations reuse the same citation descriptions. Tile and chart
    source lines are the citation text up to its first " \u00b7 ".
  * sampleData(): anchored on the real data file, so a failed fetch shows
    this country's shapes, not another's.
  * Trade-partner fallback is EMPTY: no invented figures. Until the live
    Comtrade file exists the partner block stays hidden.

Lessons from China baked in: the hero holds at most 10 tiles, so the order
below puts tiles with no other home (business confidence, FDI) inside the
cap; the GDP tile cites the real series while "Make it real" is on; the
template's leftover-name check refuses to write a page still naming China.
"""
from __future__ import annotations

import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = "china.html"
T_NAME, T_ADJ, T_SLUG, T_CODE, T_NUM, T_ISO2 = "China", "Chinese", "china", "cn", "156", "CN"

# key: (chart section or None, chart title, chart kind, fmt, upIsGood, zero line, tile sections, tile label)
CATALOG = {
    "business_confidence": ("headline", "Business confidence", "line", "idx", True, 100, ["hero"], "Business confidence"),
    "fdi": ("headline", "Foreign direct investment", "line", "pct", True, None, ["hero"], "FDI (net inflows)"),
    "gdp_level": ("gdp", "GDP", "line", "cur2", True, None, ["hero", "gdp"], "GDP (annual)"),
    "gdp_real": (None, None, None, None, None, None, [], None),   # served through "Make it real"
    "gdp_growth": ("gdp", "Real GDP growth, quarter on quarter", "bar", "pct", True, 0, ["gdp"], "Growth (QoQ)"),
    "gdp_growth_yoy": ("gdp", "Real GDP growth, year on year", "bar", "pct", True, 0, ["hero", "gdp"], "GDP growth (YoY)"),
    "cpi": ("inflation", "CPI inflation, annual rate", "line", "pct", False, 0, ["hero", "inflation"], "CPI inflation"),
    "cpi_mom": (None, None, None, "pct", False, None, ["inflation"], "CPI (MoM)"),   # a basis of the CPI chart
    "cpi_qoq": (None, None, None, "pct", False, None, ["inflation"], "CPI (QoQ)"),
    "POLICY": ("inflation", None, "line", "pct2", False, None, ["hero", "inflation"], None),
    "bond_yield_10y": ("markets", "10-year government bond yield", "line", "pct2", False, None, ["hero", "markets"], "10Y bond yield"),
    "unemployment": ("labour", "Unemployment rate", "line", "pct", False, None, ["hero", "labour"], "Unemployment"),
    "employment": ("labour", "Employment rate", "line", "pct", True, None, ["labour"], "Employment rate"),
    "participation": ("labour", "Participation rate", "line", "pct", True, None, ["labour"], "Participation rate"),
    # Eurozone data files name the OECD 15-64 rates this way (v1.7.18, Belgium).
    "employment_rate": ("labour", "Employment rate, ages 15-64", "line", "pct", True, None, ["labour"], "Employment rate"),
    "participation_rate": ("labour", "Participation rate, ages 15-64", "line", "pct", True, None, ["labour"], "Participation rate"),
    "trade_balance": ("trade", "Trade balance, goods", "bar", "cur1", True, 0, ["trade"], "Trade balance"),
    "exports": ("trade", "Exports, goods", "line", "cur1", True, None, ["trade"], "Exports"),
    "imports": ("trade", "Imports, goods", "line", "cur1", False, None, ["trade"], "Imports"),
    "current_account": ("trade", "Current account", "line", "pct", True, 0, ["trade"], "Current account"),
    "debt_gdp": ("public", "General government debt, % of GDP", "line", "pct", False, None, ["hero", "public"], "Gov. debt (% of GDP)"),
    "deficit": ("public", "General government net lending/borrowing, % of GDP", "bar", "pct", True, 0, ["hero", "public"], "Gov. balance"),
}
HERO_ORDER = ["gdp_level", "gdp_growth_yoy", "cpi", "POLICY", "bond_yield_10y", "unemployment",
              "deficit", "debt_gdp", "business_confidence", "fdi"]
SECTION_ORDER = ["gdp_level", "gdp_growth", "gdp_growth_yoy", "cpi", "cpi_mom", "cpi_qoq", "POLICY", "bond_yield_10y",
                 "unemployment", "employment", "participation", "employment_rate", "participation_rate", "trade_balance", "exports", "imports",
                 "current_account", "debt_gdp", "deficit", "business_confidence", "fdi"]
FMT = {"pct": ("pct", "pp"), "pct2": ('v=>v.toFixed(2)+"%"', 'v=>v.toFixed(2)+"pp"'), "idx": ("idx", 'v=>v.toFixed(1)+"pt"'),
       "cur1": ("v=>curFmt(v,UNIT,1)", "v=>curFmt(v,UNIT,1)"), "cur2": ("v=>curFmt(v,UNIT,1)", "v=>curFmt(v,UNIT,1)")}   # GDP tile 1dp, as every page since v1.7.13
CHART_FMT = {"pct": ('v=>v+"%"', "pct"), "pct2": ('v=>v+"%"', 'v=>v.toFixed(2)+"%"'), "idx": ("idx", 'v=>idx(v)+" (avg = 100)"'),
             "cur1": ("v=>curFmt(v,UNIT,0)", "v=>curFmt(v,UNIT,1)"), "cur2": ("v=>curFmt(v,UNIT,2)", "v=>curFmt(v,UNIT,2)")}
LEFTOVER = re.compile(r"\bChina\b|\bChinese\b|\byuan\b|\bCNY\b|data-cn|\"cn\"|Lunar|People's Bank|loan prime", re.I)
ALLOWED_LEFTOVER = ('href="china"', 'CNc=new Set', 'CNc.has(id)', '"156":"CN"', 'CNY:"CN', "CN\\u00a5")


def die(m):
    sys.exit("build_country_page: " + m)


def js(x):
    return json.dumps(x, ensure_ascii=True)


def short(src):
    return src.split(" \u00b7 ")[0]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec = json.load(open(args[0], encoding="utf-8"))
    N, ADJ, SLUG, CODE, NUM = spec["name"], spec.get("adj", spec["name"]), spec["slug"], spec["code"], spec["isonum"]
    out = ROOT / f"{SLUG}.html"
    if out.exists() and "--force" not in sys.argv:
        die(f"{out.name} exists; pass --force to regenerate it")
    data = json.load(open(ROOT / f"data-{CODE}.json", encoding="utf-8"))["series"]
    src_all = json.load(open(ROOT / "data-metric-sources.json", encoding="utf-8"))
    if N not in src_all:
        die(f'no data-metric-sources.json["{N}"]')
    SRC = src_all[N]
    pk = spec.get("policy_rate_key")
    served = set(data)
    unknown = sorted(k for k in served if k not in CATALOG and k != pk)
    if unknown:
        die(f"served keys with no CATALOG entry: {unknown}. Add them to CATALOG (section, title, format) first.")
    missing_src = sorted(k for k in served if k not in SRC)
    if missing_src:
        die(f"served keys with no citation in data-metric-sources.json: {missing_src}")

    s = (ROOT / TEMPLATE).read_text(encoding="utf-8")

    def sub(a, b, n=1):
        nonlocal s
        c = s.count(a)
        if c != n:
            die(f"template anchor found {c}x (expected {n}): {a[:70]!r}")
        s = s.replace(a, b)

    def sub_re(p, r, n=1, flags=re.S):
        nonlocal s
        # A plain-string replacement is literal text: the sample data of a euro
        # page carries "\\u20ac", which re would read as an escape (v1.7.18).
        rep = r if callable(r) else (lambda _m, _r=r: _r)
        new, c = re.subn(p, rep, s, flags=flags)
        if c != n:
            die(f"template pattern matched {c}x (expected {n}): {p[:70]!r}")
        s = new

    # ---------- head ----------
    rate_word = spec.get("policy_rate_label", "interest rate")
    have = [w for k, w in (("gdp_level", f"{N} GDP"), ("cpi", f"{ADJ} inflation rate"), (pk, rate_word),
                           ("bond_yield_10y", "10-year bond yield"), ("unemployment", "unemployment rate"),
                           ("exports", "exports"), ("imports", "imports"), ("trade_balance", "trade balance"),
                           ("debt_gdp", "government debt")) if k and k in served]
    desc = spec.get("seo_description") or ("Live " + ", ".join(have[:-1]) + " and " + have[-1] + ", official statistics, checked hourly.")
    title = spec.get("seo_title") or f"{N} Economy: GDP, Inflation, Interest Rate &amp; Trade Data"
    sub_re(r"<title>China Economy:[^<]*</title>", f"<title>{title} | The Economic Atlas</title>")
    for tag in ('meta name="description"', 'meta property="og:description"', 'meta name="twitter:description"'):
        sub_re(r"(<" + re.escape(tag) + r' content=")[^"]*(")', lambda m: m.group(1) + desc + m.group(2))
    for tag in ('meta property="og:title"', 'meta name="twitter:title"'):
        sub_re(r"(<" + re.escape(tag) + r' content=")[^"]*(")', lambda m: m.group(1) + title + m.group(2))
    sub_re(r'(  "description": )"Live China[^"]*"', lambda m: m.group(1) + js(desc))
    sub('"name": "China economic data"', f'"name": "{N} economic data"')
    sub("https://theeconomicatlas.com/china\"", f"https://theeconomicatlas.com/{SLUG}\"", 3)
    kws = spec.get("keywords") or [f"{N} GDP", f"{N} inflation rate", f"{N} interest rate", f"{N} unemployment rate",
                                   f"{N} trade balance", f"{N} economy", f"{N} economic data"]
    sub_re(r'"keywords": \[.*?\]', '"keywords": [\n' + ",\n".join("    " + js(k) for k in kws) + "\n  ]")
    sub_re(r'("spatialCoverage": \{[^}]*"name": )"China"', lambda m: m.group(1) + js(N))
    import datetime
    sub_re(r'"dateModified": "\d{4}-\d{2}-\d{2}"', '"dateModified": "' + datetime.date.today().isoformat() + '"')
    sub('{"@type": "ListItem", "position": 3, "name": "China"}', '{"@type": "ListItem", "position": 3, "name": ' + js(N) + "}")

    # ---------- nav, map, heading ----------
    sub(' <a href="china" class="active">China</a>\n', ' <a href="china">China</a>\n')
    if f' <a href="{SLUG}">{N}</a>\n' not in s:
        die(f"{N} is not in the template's nav: run tools/add_country.py first")
    sub(f' <a href="{SLUG}">{N}</a>\n', f' <a href="{SLUG}" class="active">{N}</a>\n')
    sub('var CURRENT=new Set(["156"]);', f'var CURRENT=new Set(["{NUM}"]);')
    sub("<h1>China <span", f"<h1>{N} <span")

    # ---------- section notes (spec text, else none) ----------
    notes = spec.get("notes", {})
    for sec in ("inflation", "labour", "trade", "public", "markets"):
        m = re.search(r'(<section class="sec" id="sec-' + sec + r'".*?)(</section>)', s, re.S)
        if not m:
            die(f"template has no sec-{sec}")
        block = m.group(1)
        if sec == "trade":
            # notes sit before the partner block in the trade section
            block = re.sub(r' <p class="secnote">[^\n]*</p>\n(?= <div class="tpm-head">)', "", block, count=1)
            if notes.get(sec):
                block = block.replace(' <div class="tpm-head">', f' <p class="secnote">{notes[sec]}</p>\n <div class="tpm-head">', 1)
        else:
            block = re.sub(r' {1,2}<p class="secnote">[^\n]*</p>\n', "", block)
            if notes.get(sec):
                block += f' <p class="secnote">{notes[sec]}</p>\n'
        s = s[:m.start(1)] + block + s[m.start(2):]

    # ---------- trade partners: empty fallback, block hidden until live ----------
    sub_re(r'<div class="tpm-head"><h3>China goods trade: top partners</h3></div>',
           f'<div id="tpmBlock"><div class="tpm-head"><h3>{N} goods trade: top partners</h3></div>')
    m = re.search(r'(<div id="tpmBlock">.*?)(\n</section>)', s, re.S)
    s = s[:m.end(1)] + "\n</div>" + s[m.end(1):]
    sub_re(r"// Illustrative fallback only.*?var FALLBACK_PARTNERS = \[.*?\];\n",
           "// No fallback figures: nothing invented. Until data-" + CODE + "-trade-partners.json exists\n"
           "// (UN Comtrade, update-trade-data.yml) the partner block is hidden.\nvar FALLBACK_PARTNERS = [];\n")
    sub('var UK_ID = "156"; // China', f'var UK_ID = "{NUM}"; // {N}')
    sub('return currentMetric === "exports" ? "China goods exports"', f'return currentMetric === "exports" ? "{N} goods exports"')
    sub(': currentMetric === "imports" ? "China goods imports"', f': currentMetric === "imports" ? "{N} goods imports"')
    sub(': "China goods trade";', f': "{N} goods trade";')
    sub('.text("CN");', f'.text("{spec["iso2"]}");')
    sub("partners UN Comtrade reports China goods trade", f"partners UN Comtrade reports {N} goods trade")
    sub('fetch("data-cn-trade-partners.json"', f'fetch("data-{CODE}-trade-partners.json"')
    sub("""  var livePayload = results[1];
  applyLivePartners(livePayload);""", """  var livePayload = results[1];
  if(!livePayload && !FALLBACK_PARTNERS.length){
    var tb = document.getElementById("tpmBlock"); if(tb) tb.hidden = true;
    dataReady = true; return;
  }
  applyLivePartners(livePayload);""")
    sub("not China's own currency", f"not {N}'s own currency")

    # ---------- footer ----------
    provs = []
    blob = " ".join(v.get("source", "") for v in SRC.values())
    for word, html in (("Eurostat", '<a href="https://ec.europa.eu/eurostat">Eurostat</a>'),
                       ("OECD", 'the <a href="https://www.oecd.org">OECD</a>'), ("IMF", 'the <a href="https://www.imf.org">IMF</a>'),
                       ("BIS", 'the <a href="https://www.bis.org">Bank for International Settlements</a>'),
                       ("World Bank", 'the <a href="https://data.worldbank.org">World Bank</a>')):
        if word in blob:
            provs.append(html)
    for nat in spec.get("national_sources", []):
        provs.append(f'<a href="{nat["url"]}">{nat["name"]}</a>')
    # FRED is credited for exchange rates only, unless it also serves data series (eurozone pages).
    fred_more = any("FRED" in v.get("source", "") for k, v in SRC.items() if not k.startswith("fx_") and k in served)
    provs.append('<a href="https://fred.stlouisfed.org">FRED, Federal Reserve Bank of St. Louis</a>'
                 + ("" if fred_more else " (exchange rates)"))
    credits = ", ".join(provs[:-1]) + " and " + provs[-1] if len(provs) > 1 else provs[0]
    sub_re(r" Data: the <a href=\"https://www.oecd.org\">OECD</a>.*?\(exchange rates\)\.",
           " Data: " + credits + ".")
    sub("not yet for China.", f"not yet for {N}.")

    # ---------- NAMES, label, data files ----------
    names = {"gdp_level": "GDP", "gdp_real": "Real GDP", "gdp_growth": "GDP growth", "gdp_growth_yoy": "GDP growth (y/y)",
             "cpi": "CPI inflation", "cpi_mom": "CPI (m/m)", "cpi_qoq": "CPI (q/q)", "bond_yield_10y": "10-year bond yield",
             "debt_gdp": "Government debt", "deficit": "Gov. deficit", "current_account": "Current account",
             "trade_balance": "Trade balance", "exports": "Exports", "imports": "Imports", "business_confidence": "Business confidence",
             "fdi": "FDI", "unemployment": "Unemployment", "employment": "Employment rate", "participation": "Participation rate",
             "employment_rate": "Employment rate", "participation_rate": "Participation rate"}
    if pk:
        names[pk] = spec.get("policy_rate_name", rate_word[:1].upper() + rate_word[1:])
    sub_re(r"const NAMES=\{.*?\};", "const NAMES={" + ",".join(f"{k}:{js(v)}" for k, v in names.items() if k in served) + "};")
    sub('const COUNTRY_LABEL="China";', f"const COUNTRY_LABEL={js(N)};")
    sub("page load from data-cn.json)", f"page load from data-{CODE}.json)")
    sub('fetch("data-fx-cn.json"', f'fetch("data-fx-{CODE}.json"')
    sub('fetch("data-cn.json"', f'fetch("data-{CODE}.json"')
    sub('.eq("country_code", "cn")', f'.eq("country_code", "{CODE}")')
    sub('country_code: "cn",', f'country_code: "{CODE}",')
    if pk and pk != "policy_rate":
        sub('policy_rate:"interest-rate"', f'{pk}:"interest-rate"')
    # The template only lists slugs for the series China serves; add the
    # generator's slugs for the rest of the catalogue (tile_pages_gate checks).
    extra_slugs = {"employment": "employment-rate", "participation": "labour-force-participation-rate",
                   "employment_rate": "employment-rate", "participation_rate": "labour-force-participation-rate"}
    m = re.search(r"const INDICATOR_PAGE_SLUGS = \{(.*?)\};", s)
    add = ", ".join(f'{k}:"{v}"' for k, v in extra_slugs.items() if k in served and not re.search(r"(?<![a-z_])" + k + ":", m.group(1)))
    if add:
        s = s[:m.end(1)] + ", " + add + s[m.end(1):]

    # ---------- sampleData from the real file ----------
    def anchors(k, step):
        p = [x for x in data[k]["points"] if x[1] is not None]
        pick = p[::step]
        if pick[-1] != p[-1]:
            pick.append(p[-1])
        return pick

    def periods(k):
        a, b, f = data[k]["points"][0][0], data[k]["points"][-1][0], data[k].get("freq")
        return {"months": f'monthsBetween("{a}","{b}")', "quarters": f'quartersBetween("{a}","{b}")'}.get(f, f"yearsBetween({a},{b})")

    lines = ["function sampleData(){",
             f"  // Shapes anchored on the real data-{CODE}.json at build time, so a failed",
             f"  // fetch shows {N}-shaped placeholders rather than another country's.",
             "  const S=(label,unit,freq,points)=>({label,unit,freq,points});",
             "  return { updated:new Date().toISOString(), sample:true,",
             "    series:{"]
    for k in sorted(served):
        d = data[k]
        step = {"months": 12, "quarters": 4}.get(d.get("freq"), 3)
        lines.append(f'    {k}:S({js(d.get("label", k))},{js(d.get("unit", ""))},{js(d.get("freq", "years"))},interp(\n'
                     f"      {js(anchors(k, step))},{periods(k)})),")
    lines += ["  }};", "}"]
    sub_re(r"function sampleData\(\)\{.*?\n  \}\};\n\}\n", "\n".join(lines) + "\n")

    # ---------- render() ----------
    def key_of(cat):
        return pk if cat == "POLICY" else cat

    def src_line(k):
        return js(short(SRC[k]["source"]))

    body = ["  const gdpAnnual = s.gdp_level ? annualGDP(s.gdp_level) : null;",
            '  const pct=v=>v.toFixed(1)+"%", pp=v=>v.toFixed(1)+"pp";',
            "  const idx=v=>v.toFixed(1);"]
    if "gdp_real" in served and "gdp_level" in served:
        body.append(f"  // \"Make it real\" swaps gdp_level for gdp_real: cite whichever is on screen.\n"
                    f"  const SRC_GDP = TOGGLE_STATE.real ? {src_line('gdp_real')} : {src_line('gdp_level')};")
    elif "gdp_level" in served:
        body.append(f"  const SRC_GDP = {src_line('gdp_level')};")

    def srcexpr(k):
        return "SRC_GDP" if k == "gdp_level" else src_line(k)

    # charts
    for cat in SECTION_ORDER:
        k = key_of(cat)
        if not k or k not in served:
            continue
        sec, title, kind, fmt, up, zero, tiles, label = CATALOG[cat]
        if cat == "POLICY":
            title = spec.get("policy_rate_title", rate_word[:1].upper() + rate_word[1:])
        if not sec or not title:
            continue
        unit = f"s.{k}.unit" if not fmt.startswith("cur") else ("s.gdp_level.unit" if k == "gdp_level" else f"s.{k}.unit")
        fy, ft = (x.replace("UNIT", unit) for x in CHART_FMT[fmt])
        series = "gdpAnnual" if k == "gdp_level" else f"s.{k}"
        expl = js(SRC[k].get("description", ""))
        extra = ""
        if k == "cpi":
            bases = ['{id:"yoy", label:"Year on year", series:s.cpi, srcNote:' + src_line("cpi") + ", expl:" + expl + "}"]
            for b, lab in (("cpi_mom", "Month on month"), ("cpi_qoq", "Quarter on quarter")):
                if b in served:
                    bases.append(f'{{id:"{b[4:]}", label:"{lab}", series:s.{b}, srcNote:{src_line(b)}, expl:{js(SRC[b].get("description", ""))}}}')
            extra = f",undefined,{0 if zero == 0 else 'undefined'},undefined,\n    basesFor([\n      " + ",\n      ".join(bases) + "\n    ])"
        elif zero is not None:
            extra = f",undefined,{zero}"
        body.append(f'  if({series}) chartPanel("{k}","charts-{sec}",{js(title)},\n    {expl},\n'
                    f'    {series},"{kind}",{fy},{ft},{srcexpr(k)}{extra});')
    # tiles
    def tile(cont, k, label, fmt, up):
        a, d = (x.replace("UNIT", "s.gdp_level.unit" if k == "gdp_level" else f"s.{k}.unit") for x in FMT[fmt])
        series = "gdpAnnual" if k == "gdp_level" else f"s.{k}"
        # A series with no chart of its own (cpi_mom, cpi_qoq: bases of the CPI
        # chart) passes a null key, as brazil.html does, so the tile does not try
        # to scroll to a missing chart; pageKey still links its indicator page.
        own = CATALOG.get(k, (None,) * 8)[1] is not None or k == pk
        keyarg = f'"{k}"' if own else "null"
        extra = "" if own else f'pageKey:"{k}",'
        return (f'  if({series}) statTile({cont},{keyarg},{js(label)},{series},\n'
                f"    {{{extra}fmt:{a},fmtD:{d},upIsGood:{str(up).lower()},source:{srcexpr(k)},infoKey:\"{k}\"}});")
    body.append('  const hero=document.getElementById("hero");')
    for cat in HERO_ORDER:
        k = key_of(cat)
        if not k or k not in served:
            continue
        sec, title, kind, fmt, up, zero, tiles, label = CATALOG[cat]
        if cat == "POLICY":
            label = spec.get("policy_rate_tile", names.get(pk, "Policy rate"))
        body.append(tile("hero", k, label, fmt, up))
    for sec in ("gdp", "inflation", "labour", "trade", "public", "markets"):
        cont = {"gdp": "tg", "inflation": "tinf", "labour": "tl", "trade": "tt", "public": "tp", "markets": "tm"}[sec]
        body.append(f'  const {cont}=document.getElementById("tiles-{sec}");')
        for cat in SECTION_ORDER:
            k = key_of(cat)
            if not k or k not in served or sec not in CATALOG[cat][6]:
                continue
            _, _, _, fmt, up, _, _, label = CATALOG[cat]
            if cat == "POLICY":
                label = spec.get("policy_rate_tile", names.get(pk, "Policy rate"))
            body.append(tile(cont, k, label, fmt, up))
    i0 = s.index("  const gdpAnnual = s.gdp_level ? annualGDP(s.gdp_level) : null;")
    i1 = s.index('  renderFxMarkets(document.getElementById("tiles-markets"));', i0)
    s = s[:i0] + "\n".join(body) + "\n" + s[i1:]

    # ---------- INFO_CONTENT verbatim from the citations ----------
    i0 = s.index("/* ---- per-metric info popover content ----")
    i1 = s.index("function infoIconHtml(infoKey){")
    ent = []
    for k, v in SRC.items():
        if k == "fx_usd" or k not in served:
            continue
        fields = ",\n".join(f"    {f}: {js(v[f])}" for f in ("description", "source", "real", "dollar") if f in v)
        ent.append(f"  {k}: {{\n{fields}\n  }}")
    s = s[:i0] + ("/* ---- per-metric info popover content ----\n"
                  f'   Mirrors data-metric-sources.json["{N}"] verbatim (citation_provider.py\n'
                  "   checks the two agree). Regenerate with tools/build_country_page.py. */\n"
                  "const INFO_CONTENT = {\n" + ",\n".join(ent) + "\n};\n") + s[i1:]

    # ---------- leftover template names ----------
    bad = []
    for n, line in enumerate(s.split("\n"), 1):
        if LEFTOVER.search(line) and not any(a in line for a in ALLOWED_LEFTOVER):
            bad.append(f"  line {n}: {line.strip()[:110]}")
    if bad and SLUG != T_SLUG:
        die("template text still names China:\n" + "\n".join(bad[:30]))
    out.write_text(s, encoding="utf-8")
    print(f"wrote {out.name}: {len(served)} served series, "
          f"{sum(1 for l in body if 'chartPanel(' in l)} charts, {sum(1 for l in body if 'statTile(' in l)} tiles")


if __name__ == "__main__":
    main()
