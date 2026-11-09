#!/usr/bin/env python3
"""v1.9.110 checks: every hand-maintained page with a Supabase client calls touch_last_seen
exactly once, only for a signed-in session, without awaiting it, inside the load-time
getSession block; the generator carries the same call."""
import glob, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
CALL = 'sb.rpc("touch_last_seen")'
BLOCK = re.compile(r'  sb\.auth\.getSession\(\)\.then\(function\(res\)\{\n'
                   r'    updateAuthUI\(res\.data\.session\);\n'
                   r'    // v1\.9\.110[^\n]*\n'
                   r'    if\(res\.data\.session\)\{ sb\.rpc\("touch_last_seen"\)\.then\(function\(\)\{\}, function\(\)\{\}\); \}\n'
                   r'  \}\);\n')
fails = []; checks = 0
def check(ok, msg):
    global checks; checks += 1
    if not ok: fails.append(msg)

pages = [f for f in sorted(glob.glob(os.path.join(ROOT, "*.html")))
         if os.path.basename(f) not in GENERATED and "supabase.createClient" in open(f, encoding="utf-8").read()]
check(len(pages) >= 70, f"expected 70+ pages with a Supabase client, found {len(pages)}")
for f in pages:
    s = open(f, encoding="utf-8").read(); n = os.path.basename(f)
    check(s.count(CALL) == 1, f"{n}: touch_last_seen call count {s.count(CALL)} (want 1)")
    check(len(BLOCK.findall(s)) == 1, f"{n}: call not in the guarded load-time getSession block")
    check("await " + CALL not in s, f"{n}: call must not be awaited")
g = open(os.path.join(ROOT, "generate_indicator_pages.py"), encoding="utf-8").read()
check(g.count(CALL) == 1 and len(BLOCK.findall(g)) == 1, "generator: guarded touch_last_seen call missing")

print(f"test_v19110: {checks} checks, {len(fails)} failed")
for m in fails[:20]: print("  FAIL", m)
sys.exit(1 if fails else 0)
