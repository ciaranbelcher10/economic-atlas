#!/usr/bin/env python3
"""v1.9.113 checks (after tools/migrate_v19113.py): new toggle labels everywhere they are shown,
code identifiers and saved-setting keys untouched, popover notes relabelled at display time,
Markets status dots and expandable rows valid ARIA."""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
OLD = re.compile(r"(?<![A-Za-z_\-#.])(Dollarise|Make it real)(?![A-Za-z_\-])")
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)
def read(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()

files = [os.path.basename(f) for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))) if os.path.basename(f) not in GENERATED]
files += ["mobile.js", "generate_indicator_pages.py", "methodology_by_economy.py"]
with_toggles = 0
for n in files:
    s = read(n); m = OLD.search(s)
    check(m is None, f"{n}: old label '{m.group(0) if m else ''}' still present")
    check("USD${" not in s, f"{n}: label sits against a template expression")
    if 'class="mtoggle-switch"' in s and n.endswith(".html"):
        with_toggles += 1
        check("</span>Adjust for inflation" in s or "</span>Convert to USD$" in s, f"{n}: toggle buttons not relabelled")
check(with_toggles >= 60, f"expected 60+ pages with toggles, found {with_toggles}")
cm = read("chartmaker.html")
check('id="dollariseToggle" aria-label="Convert to USD$:' in cm and 'id="makeRealToggle" aria-label="Adjust for inflation:' in cm,
      "chartmaker: button names relabelled, ids unchanged")
check('(which === "real" ? "Adjust for inflation" : "Convert to USD$") + ": "' in cm, "chartmaker: screen-reader announcement")
dash = read("dashboard.html")
check('id="dollariseBtn"' in dash and "DOLLARISE_KEY" in dash, "dashboard: ids and saved-setting key unchanged")
check("escapeHtmlDash(eaRelabel(info.dollar))" in dash and "escapeHtmlDash(eaRelabel(info.real))" in dash, "dashboard popover notes relabelled")
check("/Dollari[s]e/g" in dash and "/Make it rea[l]/g" in dash and 'return "Convert to USD$";' in dash,
      "dashboard relabel helper (function replacement, so $ stays literal)")
gen = read("generate_indicator_pages.py")
check("</span>Adjust for inflation</button>" in gen and "</span>Convert to USD$</button>" in gen, "generator toggle labels")
mk = read("markets.html")
check("'\" role=\"img\" title=\"' + t + '\" aria-label=\"' + t + '\"></span>'" in mk, "markets: status dots have role=img")
check('tr.setAttribute("aria-expanded"' not in mk and 't.setAttribute("aria-expanded"' not in mk, "markets: no aria-expanded on table rows")
check('b.className = "mk-rowbtn"' in mk and 'b.setAttribute("aria-expanded", "false")' in mk and "function mkRowState(" in mk,
      "markets: rows carry a real button with the expanded state")
check(mk.count("mkRowState(") >= 4, "markets: every open/close path updates the button")
check(".mk-rowbtn:focus-visible{" in mk, "markets: row button visible when focused by keyboard")

print(f"test_v19113: {checks} checks, {len(fails)} failed")
for f in fails[:20]: print("  FAIL", f)
sys.exit(1 if fails else 0)
