#!/usr/bin/env python3
"""v1.9.126: phone switches on one line each; World Bank cross-check knows the Cyprus difference.

 1. mobile.css: switch labels never wrap on phones (nowrap), inflation and USD$ share a row, a 360px
    rule shrinks them for the smallest phones; the dashboard (i) follows Per capita (mobile.js).
 2. check_wb_gdp_per_capita, offline with a fake World Bank built from the real data files:
    Cyprus at +4.6% is "known" (not flagged); Cyprus at +10% IS flagged (outside its band);
    Ireland at -5.7% is flagged; Switzerland compared in US$; exit code 1 only when something is flagged.
Run: python3 tools/test_v19126.py   (layout itself was checked in Chromium at 320/340/360/375/412/430px)
"""
import contextlib, io, json, os, re, sys, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
checks, fails = 0, []
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)

css = open(os.path.join(ROOT, "mobile.css"), encoding="utf-8").read()
js = open(os.path.join(ROOT, "mobile.js"), encoding="utf-8").read()
check(re.search(r"\.metric-toggles \.mtoggle\{ flex:1 1 calc\(50% - 4px\) !important; white-space:nowrap !important;", css), "phone switches: two per row, labels on one line")
check(re.search(r"body\.dash-m \.metric-toggles \.mtoggle\{[^}]*white-space:nowrap", css), "dashboard switches: labels on one line")
check(re.search(r"body\.dash-m \.metric-toggles #perCapitaBtn\{ flex:1 1 0; \}", css), "dashboard Per capita shares its row with (i)")
m = re.search(r"@media \(max-width:360px\)\{(.*?)\n\}", css, re.S)
check(m and "font-size:12px" in m.group(1) and css.rstrip().endswith("}") and m.end() >= len(css.rstrip()) - 1, "smallest-phone rule is its own block at the end")
depth = 0
for ch in css:
    depth += (ch == "{") - (ch == "}")
    if depth < 0: break
check(depth == 0, "mobile.css braces balanced")
check('document.getElementById("perCapitaBtn") || document.getElementById("dollariseBtn")' in js, "(i) placed after Per capita")

import check_wb_gdp_per_capita as wbc   # noqa: E402
def run(factors):
    """factors: {name: ours/theirs - 1}; everyone else matches exactly."""
    data = {}
    for name, f, iso2 in wbc.countries():
        p = os.path.join(ROOT, f)
        if name in wbc.SKIP or not os.path.exists(p): continue
        s = json.load(open(p, encoding="utf-8")).get("series", {}).get("gdp_per_capita")
        if s and s.get("points"):
            data[iso2] = {str(y): v / (1 + factors.get(name, 0)) for y, v in s["points"] if v}
    asked = []
    class R:
        def __init__(self, url): self.url = url
        def raise_for_status(self): pass
        def json(self):
            ind = re.search(r"indicator/([A-Z.]+)", self.url).group(1)
            isos = re.search(r"country/([A-Z;]+)/", self.url).group(1).split(";")
            asked.append((ind, set(isos)))
            return [{}, [{"country": {"id": i}, "date": y, "value": v} for i in isos for y, v in data.get(i, {}).items()]]
    sys.modules["requests"] = types.SimpleNamespace(get=lambda url, timeout=None: R(url))
    out, code = io.StringIO(), 0
    sys.argv = ["x"]
    with contextlib.redirect_stdout(out):
        try: wbc.main()
        except SystemExit as e: code = e.code or 0
    return out.getvalue(), code, asked

o, code, asked = run({"Cyprus": 0.046})
check(re.search(r"known\s+Cyprus", o) and "known difference" in o, "Cyprus +4.6% reported as a known difference")
check(re.search(r"\n0 economies|; 0 outside", o) and code == 0, "nothing flagged, exit 0: " + o.strip().splitlines()[-6])
check(any(i == wbc.USD and "CH" in s for i, s in asked) and not any(i == wbc.USD and "AU" in s for i, s in asked), "Switzerland asked in US$, Australia not")
check(len(asked) == 2, "two batched requests (local and US$), not one per economy")
o, code, _ = run({"Cyprus": 0.10})
check(re.search(r"OUT\s+Cyprus", o) and "OUTSIDE its known band" in o and code == 1, "Cyprus +10% flagged (outside its band)")
o, code, _ = run({"Ireland": -0.057})
check(re.search(r"OUT\s+Ireland", o) and "; 1 outside" in o and code == 1, "Ireland -5.7% flagged")
o, code, _ = run({"Cyprus": -0.244})
check(re.search(r"OUT\s+Cyprus", o), "the old -24% would be flagged again")

print(f"test_v19126: {checks} checks, {len(fails)} failed")
for f in fails: print("  FAIL", f)
sys.exit(1 if fails else 0)
