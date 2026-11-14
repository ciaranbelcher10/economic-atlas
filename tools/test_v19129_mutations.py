#!/usr/bin/env python3
"""v1.9.129: mutation runs for tools/test_v19129.js. Each mutation breaks one fix; the test must fail.
Every file is restored byte for byte afterwards (checked by SHA-256).
Run from the repo root:  NODE_PATH=/tmp/node_modules python3 tools/test_v19129_mutations.py
"""
import hashlib, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUTATIONS = [
    ("map stays enlarged when scrolled off screen", "mobile.js",
     "if(!en.isIntersecting) shrinkMap(wrap);", ""),
    ("map stays enlarged after a tap elsewhere", "mobile.js",
     "if(!wrap.contains(e.target)) shrinkMap(wrap);", ""),
    ("page jumps when the map shrinks above the reader", "mobile.js",
     "if(d > 0 && window.scrollBy) window.scrollBy(0, -d);", ""),
    ("first tap no longer swallowed", "mobile.js",
     "          e.preventDefault();\n          e.stopPropagation();\n          wrap.classList.add(\"mm-expanded\");",
     "          wrap.classList.add(\"mm-expanded\");"),
    ("Collapse button comes back", "mobile.js",
     "wrap.classList.add(\"mm-expanded\");\n        }\n      }, true);",
     "wrap.classList.add(\"mm-expanded\"); var hh = wrap.querySelector(\".minihint\"); if(hh) hh.textContent = \"Collapse\";\n        }\n      }, true);"),
    ("pill shown while enlarged", "mobile.css",
     "  .mini-mapwrap.mm-expanded .minihint, .mapwrap.mm-collapsible.mm-expanded .minihint{ display:none; }\n", ""),
    ("map hint shown on desktop", "style.css",
     ".ea-maphint{display:none;}", ".ea-maphint{display:block;}"),
    ("Slovenia Per capita label loses the glow colour", "slovenia.html",
     ".infoPopoverToggleNote.capita strong{color:#E06A5A;}", ".infoPopoverToggleNote.capita strong{color:var(--ink);}"),
    ("generator keeps the old mobile.js", "generate_indicator_pages.py",
     "../mobile.js?v=45", "../mobile.js?v=44"),
    ("Italy keeps the old style.css", "italy.html",
     "style.css?v=63", "style.css?v=62"),
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
            r = subprocess.run(["node", "tools/test_v19129.js"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=900)
        finally:
            open(f, "wb").write(before)
        restored = sha(f) == h
        dead = r.returncode == 1
        killed += dead and restored
        print(f"  {'killed' if dead else 'SURVIVED'}  {name}" + ("" if restored else "  (RESTORE FAILED)"))
        if not restored:
            sys.exit(1)
    print(f"test_v19129_mutations: {killed}/{len(MUTATIONS)} killed, all files restored")
    sys.exit(0 if killed == len(MUTATIONS) else 1)


if __name__ == "__main__":
    main()
