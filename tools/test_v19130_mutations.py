#!/usr/bin/env python3
"""v1.9.130: mutation runs for tools/test_v19130.js. Each mutation breaks one part of the smooth map card;
the test must fail. Every file is restored byte for byte afterwards (checked by SHA-256). About 5 minutes.
Run from the repo root:  NODE_PATH=/tmp/node_modules python3 tools/test_v19130_mutations.py
"""
import hashlib, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUTATIONS = [
    ("enlarging snaps (no animation)", "mobile.js",
     "animateMap(wrap, function(){ wrap.classList.add(\"mm-expanded\"); });", "wrap.classList.add(\"mm-expanded\");"),
    ("shrinking on a tap elsewhere snaps", "mobile.js",
     "if(visible){ animateMap(wrap, off); return; }", ""),
    ("animation starts from the full height", "mobile.js",
     "    wrap.style.maxHeight = h0 + \"px\";\n", ""),
    ("inline height never handed back", "mobile.js",
     "    wrap.style.maxHeight = \"\"; wrap.style.transition = \"\";\n  }", "  }"),
    ("no fallback when transitionend never comes", "mobile.js",
     "wrap._mmTimer = setTimeout(done, 450);", ""),
    ("off-screen shrink animated", "mobile.js",
     "if(!en.isIntersecting) shrinkMap(wrap, false);", "if(!en.isIntersecting) shrinkMap(wrap, true);"),
    ("reduced motion ignored", "mobile.js",
     "if(mapStill() || !(h0 > 0)", "if(!(h0 > 0)"),
    ("old max-height transition back on the country card", "mobile.css",
     "    transition:none;   /* v1.9.130: mobile.js animates the real height */", "    transition:max-height .25s ease;"),
    ("legend no longer fades", "mobile.css",
     "{ animation:eaMapFade .25s ease .2s both; }", "{ }"),
    ("Spain keeps the old mobile.js", "spain.html",
     "mobile.js?v=46", "mobile.js?v=45"),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    env = dict(os.environ)
    killed = 0
    for name, rel, old, new in MUTATIONS:
        f = os.path.join(ROOT, rel)
        before, h = open(f, "rb").read(), sha(f)
        s = before.decode("utf-8")
        if s.count(old) != 1:
            print(f"  ANCHOR  {name}: found {s.count(old)} times"); sys.exit(1)
        try:
            open(f, "w", encoding="utf-8").write(s.replace(old, new))
            r = subprocess.run(["node", "tools/test_v19130.js"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        finally:
            open(f, "wb").write(before)
        restored = sha(f) == h
        dead = r.returncode == 1
        killed += dead and restored
        print(f"  {'killed' if dead else 'SURVIVED'}  {name}" + ("" if restored else "  (RESTORE FAILED)"))
        if not restored:
            sys.exit(1)
    print(f"test_v19130_mutations: {killed}/{len(MUTATIONS)} killed, all files restored")
    sys.exit(0 if killed == len(MUTATIONS) else 1)


if __name__ == "__main__":
    main()
