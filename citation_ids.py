#!/usr/bin/env python3
"""
Workstream 6: compare the series identifier in each citation against the
identifier the fetch script actually uses, per metric per country.

The existing sitewide check matches PROVIDER NAMES only, so a citation
naming the wrong FRED series id from the right provider passes straight
through it. That is not hypothetical: the Eurozone exports citation named
teiet110 (the imports dataset) while the fetch used teiet010.

Reports, per (country, metric):
  MATCH      cited id == id the script uses
  MISMATCH   cited id != id the script uses
  UNCITED    script uses an id, citation names none
  NO-ID      script has no single id to compare (derived, multi-source)
"""
import re, json, os, sys
from collections import Counter

import os as _os
REPO = _os.environ.get("ATLAS_REPO") or _os.path.dirname(
    _os.path.dirname(_os.path.abspath(__file__)))


def country_to_script():
    src = open(os.path.join(REPO, "compare.html"), encoding="utf-8").read()
    blk = src[src.index("var FILES = {"):]
    blk = blk[:blk.index("}")]
    out = {}
    for m in re.finditer(r'(?:"([^"]+)"|([A-Za-z]+))\s*:\s*"(data[a-z\-]*\.json)"', blk):
        name = (m.group(1) or m.group(2)).strip()
        f = m.group(3)
        out[name] = "fetch_data.py" if f == "data.json" else "fetch_" + f[5:-5] + ".py"
    return out


# Identifiers we expect to see: FRED-style uppercase, Eurostat lowercase
# dataset ids, World Bank dotted indicators, IMF indicator codes.
ID_RE = re.compile(r"\b(?:[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+){2,}|[A-Z][A-Z0-9]{5,}|(?:tei|gov|une|nama|prc|ei|sts|ext)[a-z]*_?[a-z0-9_]*\d[a-z0-9_]*)\b")
STOPWORDS = {
    "GDP", "CPI", "HICP", "OECD", "IMF", "BIS", "ONS", "FRED", "EDP", "COICOP",
    "USD", "EUR", "NSA", "PPP", "YoY", "QoQ", "ILO", "WEO", "IFS", "EU", "ECB",
    "UNITED", "NOTE", "DATA", "ANNUAL", "MONTHLY", "QUARTERLY", "TOTAL",
}


def ids_in(text):
    return {t for t in ID_RE.findall(text or "") if t.upper() not in STOPWORDS}


def script_ids_for(script, metric):
    """Every identifier the script associates with this metric."""
    path = os.path.join(REPO, script)
    if not os.path.exists(path):
        return set()
    s = open(path, encoding="utf-8").read()
    ids = set()
    m = re.search(r'"%s":\s*\("([A-Z0-9._]+)"' % re.escape(metric), s)
    if m:
        ids.add(m.group(1))
    for pat in (r'\("%s",\s*lambda:\s*fetch_worldbank\("([A-Z0-9.]+)"\)',
                r'\("%s",\s*lambda:\s*[a-z_]*fred[a-z_]*\("([A-Z0-9._]+)"'):
        m = re.search(pat % re.escape(metric), s)
        if m:
            ids.add(m.group(1))
    # metric assigned a label carrying an id, e.g. out["series"]["cpi"] = {... "label": "... (Eurostat, CP0000PLM086NEST)"}
    for m in re.finditer(r'\["series"\]\["%s"\]\s*=\s*\{(.{0,400}?)\}' % re.escape(metric), s, re.S):
        ids |= ids_in(m.group(1))
    if metric in ("debt_gdp", "deficit"):
        ds = re.findall(r"(gov_10[a-z0-9_]+)", s)
        if ds:
            ids.add(next((x for x in ds if "ggdebt" in x), ds[0]) if metric == "debt_gdp"
                    else next((x for x in ds if "ggnfa" in x), ds[0]))
    return ids


if __name__ == "__main__":
    c2s = country_to_script()
    sources = json.load(open(os.path.join(REPO, "data-metric-sources.json"), encoding="utf-8"))
    rows, counts = [], Counter()
    for country, metrics in sources.items():
        if not isinstance(metrics, dict):
            continue
        script = c2s.get(country)
        if not script:
            counts["NO-SCRIPT"] += 1
            continue
        for metric, info in metrics.items():
            if not isinstance(info, dict):
                continue
            cited = ids_in(info.get("source", ""))
            used = script_ids_for(script, metric)
            if not used:
                counts["NO-ID"] += 1
                continue
            if not cited:
                counts["UNCITED"] += 1
                rows.append(("UNCITED", country, metric, "", ",".join(sorted(used))))
                continue
            if cited & used:
                counts["MATCH"] += 1
            else:
                counts["MISMATCH"] += 1
                rows.append(("MISMATCH", country, metric,
                             ",".join(sorted(cited)), ",".join(sorted(used))))
    for k in ("MATCH", "MISMATCH", "UNCITED", "NO-ID", "NO-SCRIPT"):
        print(f"  {k:10} {counts[k]}")
    print()
    for r in sorted(rows):
        print(f"{r[0]:9} {r[1]:14}{r[2]:20} cited={r[3][:44]:46} used={r[4][:44]}")
