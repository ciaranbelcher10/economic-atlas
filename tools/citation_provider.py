"""Does each citation name the provider that actually supplied the served series?

    python3 tools/citation_provider.py            # mismatches only, with a summary
    python3 tools/citation_provider.py --all      # every (country, metric) row

`citation_ids.py` compares series identifiers, but 74 citations name no
identifier, and a citation can quote no id and still name the wrong
publisher or the wrong measure (HICP against a national CPI). This tool
reads the provider family from three places and compares them:

  served   the `label` of the series in the country's data file
  compare  compare.html's per-country source table
  chartmkr chartmaker.html's per-country source table
  dashbrd  dashboard.html's per-country source table
  popover  data-metric-sources.json
  page     the country page's own chart, tile and info-panel source strings
           (a source read from the series label at runtime is skipped, since
           it cannot disagree with what is served)

A row is a MISMATCH when two surfaces both name a recognisable family and the
families differ. A surface naming no recognisable family is UNCLASSIFIED and
is counted, not assumed correct.
"""
import json, os, re, sys

REPO = os.environ.get("ATLAS_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A citation's primary provider is the first family it names. Later mentions
# are usually a fallback ("falls back to World Bank") or the underlying
# compiler ("sourced from IMF balance-of-payments data"), not the publisher.
# Ties at the same position go to the earlier entry in this list.
FAMILIES = [
    ("HICP",        r"\bHICP\b|harmoni[sz]ed index of consumer|CP0000[A-Z0-9]+M086NEST"),
    ("IMF",         r"\bIMF\b|Regional Economic Outlook|World Economic Outlook|PPPT\b|A188N\b|GGXWDGGDP|GGXCNLGDP|GDPPT\b"),
    ("World Bank",  r"World Bank|\bNY\.GDP|\bSL\.UEM|\bBX\.KLT|\bBN\.CAB|\bGC\.NLD|\bFP\.CPI"),
    ("INDEC",       r"\bINDEC\b"),
    ("e-Stat",      r"e-Stat|Statistics Bureau of Japan"),
    ("MoSPI",       r"MoSPI|PLFS"),
    ("ONS",         r"\bONS\b"),
    ("BLS",         r"\bBLS\b|CPIAUC|CPILFE|UNRATE|PAYEMS|CIVPART"),
    ("Eurostat",    r"Eurostat|CLVMNAC|CPMNAC|namq_10|une_rt_m|gov_10dd|teiet\d"),
    ("OECD",        r"\bOECD\b|XTNTVA01|XTEXVA01|XTIMVA01|LRHUTTTT|LRUN64TT|MEI\b"),
]
# On inflation rows only, "harmonized" alone names the HICP measure. On
# unemployment it means the ILO-harmonised rate, so it is not applied there.
CPI_HARMONISED = r"\bharmoni[sz]ed\b"

def family(text, key=""):
    if not text:
        return None
    best = None
    pats = list(FAMILIES)
    if key.startswith("cpi"):
        pats = [("HICP", FAMILIES[0][1] + "|" + CPI_HARMONISED)] + FAMILIES[1:]
    for rank, (name, pat) in enumerate(pats):
        m = re.search(pat, text, re.I)
        if m and (best is None or (m.start(), rank) < best[0]):
            best = ((m.start(), rank), name)
    name = best[1] if best else "?"
    # For inflation, Eurostat is the HICP publisher, so the two agree.
    if key.startswith("cpi") and name == "Eurostat":
        name = "HICP"
    return name

def compare_table(src):
    m = src[src.index("var FILES"):src.index("var ALL_COUNTRIES")]
    files = {(a or b): f for a, b, f in re.findall(r'(?:"([^"]+)"|\b([A-Za-z]+))\s*:\s*"(data[^"]*\.json)"', m)}
    table = {}
    for c in files:
        blk = re.search(r'\n  "?' + re.escape(c) + r'"?: \{(.*?)\n  \}', src, re.S)
        if blk:
            table[c] = dict(re.findall(r'\n    ([a-z_0-9]+): "([^"]*)"', blk.group(1)))
    return files, table

def page_sources(html):
    """key -> list of static source strings on a country page."""
    out = {}
    for m in re.finditer(r'chartPanel\("([a-z_0-9]+)"(.{0,900}?)\);', html, re.S):
        tail = re.search(r'pct,\s*"((?:[^"\\]|\\.)*)"\s*$', m.group(2).strip())
        if tail:
            out.setdefault(m.group(1), []).append(tail.group(1))
    for m in re.finditer(r'statTile\([a-z]+,"([a-z_0-9]+)"[^{]*\{[^}]*?source:"((?:[^"\\]|\\.)*)"', html):
        out.setdefault(m.group(1), []).append(m.group(2))
    for m in re.finditer(r'\n  ([a-z_0-9]+): \{\n    description: "(?:[^"\\]|\\.)*",\n    source: "((?:[^"\\]|\\.)*)"', html):
        out.setdefault(m.group(1), []).append(m.group(2))
    return {k: [v.replace("\\u00b7", "\u00b7") for v in vs] for k, vs in out.items()}

def page_file(country):
    return {"UK": "uk.html", "US": "us.html"}.get(country, country.lower().replace(" ", "") + ".html")

def main():
    show_all = "--all" in sys.argv
    src = open(os.path.join(REPO, "compare.html"), encoding="utf-8").read()
    files, table = compare_table(src)
    # chartmaker.html and dashboard.html carry their own copies of the same
    # per-country source strings. They were unchecked until now, which is how
    # a stale CPIAUCSL citation survived a clean run of this tool after the
    # series moved to CPIAUCNS. A copy nobody checks is a copy that drifts.
    shared = {"compare": table}
    for name, fn in (("chartmkr", "chartmaker.html"), ("dashbrd", "dashboard.html")):
        path = os.path.join(REPO, fn)
        if not os.path.exists(path):
            continue
        try:
            shared[name] = compare_table(open(path, encoding="utf-8").read())[1]
        except ValueError:
            print(f"  WARNING  {fn}: no source table found where one was expected")
    pops = json.load(open(os.path.join(REPO, "data-metric-sources.json"), encoding="utf-8"))
    rows, mism, uncls, checked = [], 0, 0, 0
    for c, f in sorted(files.items()):
        served = json.load(open(os.path.join(REPO, f), encoding="utf-8")).get("series", {})
        pf = os.path.join(REPO, page_file(c))
        psrc = page_sources(open(pf, encoding="utf-8").read()) if os.path.exists(pf) else {}
        for k, s in sorted(served.items()):
            if not isinstance(s, dict) or "label" not in s:
                continue
            fam = {"served": family(s.get("label"), k),
                   "popover": family((pops.get(c, {}).get(k) or {}).get("source"), k)}
            for sname, stable in shared.items():
                fam[sname] = family(stable.get(c, {}).get(k), k)
            for i, t in enumerate(psrc.get(k, [])):
                fam[f"page{i + 1}"] = family(t, k)
            known = {n: v for n, v in fam.items() if v and v != "?"}
            if any(v == "?" for v in fam.values()):
                uncls += 1
            if len(known) >= 2:
                checked += 1
            bad = len(set(known.values())) > 1
            mism += bad
            if bad or show_all:
                extra = "  ".join(f"{n}={v}" for n, v in fam.items() if n.startswith("page"))
                surfaces = "  ".join(f"{n}={fam[n]}" for n in ("served", "popover") + tuple(shared))
                rows.append(f"{'MISMATCH' if bad else 'ok      '}  {c:13} {k:22} {surfaces}  {extra}")
    # Each country page's info panel is meant to carry the popover file's
    # text verbatim. Any difference is drift, whoever is right.
    info_rx = re.compile(r'\n  ([a-z_0-9]+): \{\n    description: "(?:[^"\\]|\\.)*",\n    source: "((?:[^"\\]|\\.)*)"')
    equal = drift = 0
    for c, metrics in pops.items():
        pf = os.path.join(REPO, page_file(c))
        if not os.path.exists(pf):
            continue
        for m in info_rx.finditer(open(pf, encoding="utf-8").read()):
            k = m.group(1)
            if k not in metrics:
                continue
            if json.loads('"' + m.group(2) + '"') == metrics[k].get("source"):
                equal += 1
            else:
                drift += 1
                rows.append(f"DRIFT     {c:13} {k:22} page info panel differs from data-metric-sources.json")
    # Every infoKey a page references must have a panel behind it, and every
    # panel should be reachable. A tile pointing at a missing panel renders an
    # empty popover; a panel nothing points at is dead weight that drifts
    # unnoticed. Neither was checked before, which is how the cpih_mom tile
    # shipped pointing at a panel that did not yet exist.
    orphan_ref = orphan_panel = 0
    for c in sorted(files):
        pf = os.path.join(REPO, page_file(c))
        if not os.path.exists(pf):
            continue
        html = open(pf, encoding="utf-8").read()
        referenced = set(re.findall(r'infoKey:\s*"([a-z_0-9]+)"', html))
        referenced |= set(re.findall(r'chartPanel\("([a-z_0-9]+)"', html))
        defined = set(m.group(1) for m in info_rx.finditer(html))
        for k in sorted(referenced - defined):
            # a chart panel key without its own panel falls back to the
            # metric description, so only an explicit infoKey is an error
            if re.search(r'infoKey:\s*"' + re.escape(k) + r'"', html):
                orphan_ref += 1
                rows.append(f"NO PANEL  {c:13} {k:22} infoKey references a panel this page does not define")
        for k in sorted(defined - referenced):
            orphan_panel += 1
            rows.append(f"UNUSED    {c:13} {k:22} info panel defined but nothing references it")

    print("\n".join(rows))
    print(f"\n  compared {checked} (country, metric) rows with two or more classifiable surfaces")
    print(f"  MISMATCH      {mism}")
    print(f"  INFO PANEL    {equal} equal to the popover file, {drift} drifted")
    print(f"  INFO KEYS     {orphan_ref} referencing a missing panel, {orphan_panel} panels referenced by nothing")
    print(f"  UNCLASSIFIED  {uncls}  (a surface naming no known provider family; not evidence of a correct citation)")
    return 1 if (mism or drift or orphan_ref) else 0

if __name__ == "__main__":
    sys.exit(main())
