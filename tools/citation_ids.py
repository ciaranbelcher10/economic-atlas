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


def _find_repo(start):
    d = start
    while True:
        if (_os.path.exists(_os.path.join(d, "compare.html"))
                and _os.path.exists(_os.path.join(d, "data-metric-sources.json"))):
            return d
        parent = _os.path.dirname(d)
        if parent == d:
            raise SystemExit(
                "could not locate the economic-atlas clone from "
                + start + "; set ATLAS_REPO to the clone root")
        d = parent


REPO = _os.environ.get("ATLAS_REPO") or _find_repo(
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


# Some scripts serve more than one country from separate tables in one file.
# Resolving by a whole-file regex then returns the wrong country's ids: every
# UK metric resolved against US_FRED, so UK cpi "used" CPIAUCSL. That is worse
# than no answer, because it invites inserting a US code into a UK citation,
# which is exactly how GDPC1 ended up in the UK gdp_real citation. Each entry
# maps a country to the table that actually holds its ids.
MULTI_COUNTRY = {
    "fetch_data.py": {"UK": "UK_SERIES", "US": "US_FRED"},
}


def _table_block(src, name):
    """Source text of a top-level `NAME = {...}` table."""
    m = re.search(r"^%s\s*=\s*\{" % re.escape(name), src, re.M)
    if not m:
        return ""
    i = src.index("{", m.start())
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return ""


# ONS identifies a series by the four-character code in its page URI
# (/timeseries/ybha/pn2) and repeats it in the label. Neither is uppercase in
# the URI, so ID_RE cannot see it.
ONS_URI_RE = re.compile(r"/timeseries/([a-z0-9]{4})/")


# Table entries are `"metric": ("ID", freq, label, unit)` or, for the ONS
# table, `"metric": ([uri, ...], label, unit)`. The leading quoted token is the
# identifier, and taking it positionally catches short codes (GDP, GDPC1) that
# ID_RE's six-character minimum cannot see.
FIRST_ID_RE = re.compile(r'"[a-z_0-9]+":\s*\(\s*"([A-Za-z0-9._]+)"')


def _ids_from_entry(entry):
    ids = set(m.group(1).upper() for m in ONS_URI_RE.finditer(entry))
    ids |= set(m.group(1).upper() for m in FIRST_ID_RE.finditer(entry))
    ids |= ids_in(entry)
    return ids


def scoped_ids_for(script, metric, country):
    """Ids for this metric from this country's own table, for shared scripts."""
    table = MULTI_COUNTRY.get(script, {}).get(country)
    if not table:
        return None
    path = os.path.join(REPO, script)
    if not os.path.exists(path):
        return set()
    blk = _table_block(open(path, encoding="utf-8").read(), table)
    m = re.search(r'"%s":\s*\((.{0,400}?)\),\n' % re.escape(metric), blk, re.S)
    return _ids_from_entry(m.group(1)) if m else set()


def foreign_ids_for(script, country):
    """Ids belonging to the OTHER countries shared with this script."""
    tables = MULTI_COUNTRY.get(script, {})
    if not tables or country not in tables:
        return set()
    src = open(os.path.join(REPO, script), encoding="utf-8").read()
    mine = _ids_from_entry(_table_block(src, tables[country]))
    theirs = set()
    for other, tbl in tables.items():
        if other != country:
            theirs |= _ids_from_entry(_table_block(src, tbl))
    return theirs - mine


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
    # EU members' cpi goes through inflation_sources.fetch_hicp with the
    # literal FRED id passed in by the country script.
    if metric == "cpi":
        m = re.search(r'fetch_hicp\(\s*fetch_fred,\s*"(CP0000[A-Z0-9]+M086NEST)"', s)
        if m:
            ids.add(m.group(1))
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
            citation = info.get("source", "")
            cited = ids_in(citation)
            scoped = scoped_ids_for(script, metric, country)
            used = scoped if scoped is not None else script_ids_for(script, metric)
            # An id from a country that shares this script is always wrong here,
            # whether or not the right id is present too.
            # ID_RE needs six characters, so short codes (GDP, GDPC1) are
            # invisible to it. The foreign table is a closed, known list, so
            # match it literally instead. Drop anything that reads as ordinary
            # prose ("% of GDP") or the check fires on every citation.
            foreign = {f for f in foreign_ids_for(script, country)
                       if len(f) >= 4 and f.upper() not in STOPWORDS}
            stray = {f for f in foreign
                     if re.search(r"\b" + re.escape(f) + r"\b", citation)}
            if stray:
                counts["CROSS-TABLE"] += 1
                rows.append(("CROSS-TABLE", country, metric,
                             ",".join(sorted(stray)), ",".join(sorted(used))))
                continue
            if not used:
                counts["NO-ID"] += 1
                continue
            # ID_RE needs six characters, so short FRED codes (GDP, GDPC1,
            # PCEPI) are invisible to it and a correct citation reads as
            # UNCITED. Widening the regex instead would match "GDP" and "CPI"
            # in ordinary prose across every citation on the site, so accept
            # the narrow case: the used id written immediately after the word
            # "series", which is the house citation shape.
            if not cited and any(
                    re.search(r"\bseries " + re.escape(u) + r"\b", citation)
                    for u in used):
                counts["MATCH"] += 1
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
    for k in ("MATCH", "MISMATCH", "CROSS-TABLE", "UNCITED", "NO-ID", "NO-SCRIPT"):
        print(f"  {k:12} {counts[k]}")
    total = sum(counts.values())
    compared = counts["MATCH"] + counts["MISMATCH"] + counts["CROSS-TABLE"]
    print(f"\n  compared     {compared} of {total} citations "
          f"({100 * compared // total if total else 0}%); the rest name no "
          f"resolvable id and are NOT evidence of a correct citation")
    print()
    for r in sorted(rows):
        print(f"{r[0]:9} {r[1]:14}{r[2]:20} cited={r[3][:44]:46} used={r[4][:44]}")
