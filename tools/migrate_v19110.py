#!/usr/bin/env python3
"""v1.9.110 last-seen tracking: on page load, a signed-in user calls the Supabase
function touch_last_seen(), which stamps profiles.last_seen_at (server writes at most hourly).

Page edit made at deploy time, like migrate_v19103.py, because the data bot rewrites pages.
Edits every hand-maintained page that creates a Supabase client, plus generate_indicator_pages.py
(the bot-generated pages pick it up on their next regeneration; they are never committed by hand).
Idempotent: a page already done is left alone.

Run from the repo root:  python3 tools/migrate_v19110.py
Exits 1 if a page with a Supabase client is left without the call."""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
MARKER = 'sb.rpc("touch_last_seen")'
OLD = ("  sb.auth.getSession().then(function(res){\n"
       "    updateAuthUI(res.data.session);\n"
       "  });\n")
NEW = ("  sb.auth.getSession().then(function(res){\n"
       "    updateAuthUI(res.data.session);\n"
       "    // v1.9.110: record when a signed-in user last used the site (the server writes at most hourly).\n"
       "    if(res.data.session){ " + MARKER + ".then(function(){}, function(){}); }\n"
       "  });\n")

def apply(path):
    s = open(path, encoding="utf-8").read()
    if MARKER in s or OLD not in s:
        return 0, s
    new = s.replace(OLD, NEW, 1)
    open(path, "w", encoding="utf-8").write(new)
    return 1, new

def main():
    changed = 0; missing = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        name = os.path.basename(f)
        if name in GENERATED: continue
        n, s = apply(f); changed += n
        if "supabase.createClient" in s and MARKER not in s: missing.append(name)
    g = os.path.join(ROOT, "generate_indicator_pages.py")
    gn, gs = apply(g)
    if MARKER not in gs: missing.append("generate_indicator_pages.py")
    print(f"migrate_v19110: {changed} page(s) changed; generator {gn} edit(s)")
    if missing:
        print("migrate_v19110: FAIL no touch_last_seen call in: " + ", ".join(missing)); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
