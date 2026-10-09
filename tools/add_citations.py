#!/usr/bin/env python3
"""Merge a country's citation block into data-metric-sources.json (v1.7.33).

    python3 tools/add_citations.py tools/country_specs/hu.citations.json

The file holds {"<Name>": {metric: {description, source, ...}}}. Run this
BEFORE tools/add_country.py, which checks the citations exist. Refuses to
overwrite a country that is already there (edit data-metric-sources.json by
hand for changes). Keeps the file's format: indent 2, UTF-8, trailing newline.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
p = ROOT / "data-metric-sources.json"
if len(sys.argv) != 2:
    sys.exit("usage: add_citations.py tools/country_specs/<code>.citations.json")
new = json.load(open(sys.argv[1], encoding="utf-8"))
d = json.load(open(p, encoding="utf-8"))
for name, block in new.items():
    if name in d:
        sys.exit(f"add_citations: {name} already in data-metric-sources.json; nothing changed")
    for k, v in block.items():
        bad = [f for f, t in v.items() if "\u2014" in t or "--" in t]
        if bad or "source" not in v:
            sys.exit(f"add_citations: {name}.{k} has no source or uses an em dash / double hyphen")
    d[name] = block
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"added {', '.join(new)} ({sum(len(b) for b in new.values())} citations)")
