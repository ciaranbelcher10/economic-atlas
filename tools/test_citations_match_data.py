"""v1.9.54: every series' popover citation names the source the data actually came from.

    python3 tools/test_citations_match_data.py   -> "N ok, 0 failed"

For each country (fx_config.COUNTRY_FX) and each series in its data file whose label carries a
source code (a FRED id like IRLTLT01LUM156N or a dataset like irt_lt_mcby_m), the citation in
data-metric-sources.json must name one of those codes. Caught Luxembourg and Slovenia, whose
yields had come from Eurostat since 21 Oct 2026 while every citation still named FRED. Offline.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fx_config  # noqa: E402

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

# source codes: FRED-style ids (6+ capitals/digits) and dataset names with underscores (une_rt_m)
CODE = re.compile(r"\b([A-Z][A-Z0-9]{5,}[A-Z0-9_.]*|[a-z]{2,}(?:_[a-z0-9]+){1,})\b")
def codes(label):
    return [c for c in CODE.findall(label or "") if not c.isdigit()]

def mismatches(sources, data_by_country):
    out, n = [], 0
    for name, series in data_by_country.items():
        for key, s in series.items():
            cite = (sources.get(name, {}).get(key) or {})
            cite = cite.get("source", "") if isinstance(cite, dict) else (cite or "")
            cs = codes(s.get("label"))
            if not cite or not cs:
                continue
            n += 1
            if not any(c in cite for c in cs):
                out.append(f"{name} {key}: data from {cs[-1]}, citation says {cite[:70]!r}")
    return out, n

sources = json.load(open(os.path.join(ROOT, "data-metric-sources.json"), encoding="utf-8"))
data, unmapped = {}, []
for name, spec in fx_config.COUNTRY_FX.items():
    code = spec[1]
    f = os.path.join(ROOT, f"data-{code}.json")
    if not os.path.exists(f):
        unmapped.append(name); continue
    data[name] = json.load(open(f, encoding="utf-8")).get("series", {})
files = {f for f in os.listdir(ROOT) if re.fullmatch(r"data-[a-z]{2}\.json", f)}
check(len(data) == len(files), f"every country data file is covered ({len(data)} of {len(files)}; no data file for {unmapped})")

found, n = mismatches(sources, data)
check(n >= 350, f"enough series carry a source code to make this meaningful ({n})")
check(not found, f"{len(found)} citation(s) name a different source from the data:\n  " + "\n  ".join(found))

# the check itself catches the case it was written for
fake = json.loads(json.dumps(sources)); fake["Luxembourg"]["bond_yield_10y"]["source"] = "FRED series IRLTLT01LUM156N \u00b7 OECD, monthly."
check(any(m.startswith("Luxembourg bond_yield_10y") for m in mismatches(fake, data)[0]), "a FRED citation over Eurostat data is caught")
fake["Luxembourg"]["bond_yield_10y"]["source"] = "Eurostat irt_lt_mcby_m"
check(not any(m.startswith("Luxembourg bond_yield_10y") for m in mismatches(fake, data)[0]), "the matching citation passes")

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
