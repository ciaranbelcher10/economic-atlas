#!/usr/bin/env python3
"""v1.9.128: mutation runs for tools/test_v19128.js. Each mutation breaks one fix; the test must fail.
Every file is restored byte for byte afterwards (checked by SHA-256).
Run from the repo root:  NODE_PATH=/tmp/node_modules python3 tools/test_v19128_mutations.py
"""
import hashlib, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUTATIONS = [
    ("indicator page axis callback bypasses EA_axisTick", "indicator-kit.js",
     "return EA_axisTick(f, v, i, t); }}}", "return f(v); }}}"),
    ("relabel stops renaming Make it real", "percapita.js",
     '.replace(/Make it real/g, "Adjust for inflation")', ""),
    ("infoNote never says On now", "percapita.js",
     'if(opts.on) s = "On now: the figures shown are per person. " + s;', ""),
    ("infoNote ignores Taiwan", "percapita.js",
     "    if(opts.noPopulation) return", "    if(false) return"),
    ("Slovenia (i) loses its Per capita paragraph", "slovenia.html",
     "  if(window.EA_PC && EA_PC.infoNote){\n    const p = document.createElement(\"p\");", "  if(false){\n    const p = document.createElement(\"p\");"),
    ("Slovenia map hint reworded", "slovenia.html",
     '<p class="home-mapcap ea-maphint">All 62 economies.', '<p class="home-mapcap ea-maphint">All economies.'),
    ("phone homepage map not collapsible", "mobile.js",
     '[document.getElementById("miniMapWrap"), document.querySelector(".mapwrap")]', '[document.getElementById("miniMapWrap")]'),
    ("Dashboard (i) loses its Per capita paragraph", "dashboard.html",
     "  if(info && window.EA_PC && EA_PC.infoNote){", "  if(false){"),
    ("EA_axisTick adds no decimals", "percapita.js",
     "for(var extra = 1; extra <= 6 && !uniq(out); extra++){", "for(var extra = 1; extra <= 0 && !uniq(out); extra++){"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    env = dict(os.environ, EA_SAMPLE=os.environ.get("EA_SAMPLE", "60"))
    killed = 0
    for name, rel, old, new in MUTATIONS:
        f = os.path.join(ROOT, rel)
        before, h = open(f, "rb").read(), sha(f)
        s = before.decode("utf-8")
        if s.count(old) != 1:
            print(f"  ANCHOR  {name}: found {s.count(old)} times"); sys.exit(1)
        try:
            open(f, "w", encoding="utf-8").write(s.replace(old, new))
            r = subprocess.run(["node", "tools/test_v19128.js"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        finally:
            open(f, "wb").write(before)
        restored = sha(f) == h
        dead = r.returncode == 1
        killed += dead and restored
        print(f"  {'killed' if dead else 'SURVIVED'}  {name}" + ("" if restored else "  (RESTORE FAILED)"))
        if not restored:
            sys.exit(1)
    print(f"test_v19128_mutations: {killed}/{len(MUTATIONS)} killed, all files restored")
    sys.exit(0 if killed == len(MUTATIONS) else 1)


if __name__ == "__main__":
    main()
