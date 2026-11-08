#!/usr/bin/env python3
"""v1.9.104: page edits made at deploy time (the data bot rewrites country pages). Idempotent.
  - Account initial: any letter or digit in any script shows (capitalised when that stays one
    character); anything else (symbol, emoji, stray accent mark, no email) shows "?".
Run from the repo root:  python3 tools/migrate_v19104.py   (exits 1 if an old pattern remains)"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
OLD = '      var ini = (em.charAt(0) || "?").toUpperCase().replace(/[^A-Z0-9]/, "?");\n'
NEW = ('      var c0 = Array.from(em)[0] || "", up = c0.toUpperCase(), ln;\n'
       '      try { var bs = String.fromCharCode(92); ln = new RegExp("^[" + bs + "p{L}" + bs + "p{N}]$", "u"); } catch(e){ ln = /^[A-Za-z0-9]$/; }\n'
       '      var ini = ln.test(c0) ? (up.length === 1 ? up : c0) : "?";\n')

def fix(path):
    s = open(path, encoding="utf-8").read()
    n = s.count(OLD)
    if n:
        open(path, "w", encoding="utf-8").write(s.replace(OLD, NEW))
    return n, OLD in open(path, encoding="utf-8").read()

def main():
    pages = 0; left = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        if os.path.basename(f) in GENERATED: continue
        n, bad = fix(f)
        pages += 1 if n else 0
        if bad: left.append(os.path.basename(f))
    gn, gbad = fix(os.path.join(ROOT, "generate_indicator_pages.py"))
    if gbad: left.append("generate_indicator_pages.py")
    print(f"migrate_v19104: {pages} page(s) changed; generator {gn} edit(s)")
    if left:
        print("migrate_v19104: FAIL old pattern remains in: " + ", ".join(left)); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
