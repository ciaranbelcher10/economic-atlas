#!/usr/bin/env python3
"""Sitemap gate: every served page listed exactly once, nothing else.

Fails on: a duplicate <loc>; a served page missing from sitemap.xml; a listed
URL with no file behind it; a listed page that is noindex or a redirect stub.
Served pages = root *.html (except 404.html and redirect/noindex stubs),
indicators/*.html, rankings/*.html (index.html -> /rankings). Embeds are
noindex and never listed (v1.6.48); robots.txt must not block a listed URL.

    python3 tools/sitemap_gate.py      # exit 0 = clean
"""
import os, re, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://theeconomicatlas.com"

def head(path):
    with open(path, encoding="utf-8") as f:
        return f.read(4000)

def blocked(path):
    h = head(path)
    return 'http-equiv="refresh"' in h or "noindex" in h

def expected():
    want = {}
    for f in os.listdir(ROOT):
        if f.endswith(".html") and f != "404.html":
            p = os.path.join(ROOT, f)
            if not blocked(p):
                want[f"{SITE}/" if f == "index.html" else f"{SITE}/{f[:-5]}"] = p
    for d in ("indicators", "embed", "rankings"):
        dp = os.path.join(ROOT, d)
        for f in os.listdir(dp) if os.path.isdir(dp) else []:
            if f.endswith(".html") and not blocked(os.path.join(dp, f)):
                url = f"{SITE}/{d}" if f == "index.html" else f"{SITE}/{d}/{f[:-5]}"
                want[url] = os.path.join(dp, f)
    return want

def url_to_file(u):
    rel = u[len(SITE):].strip("/")
    for c in ([os.path.join(ROOT, "index.html")] if not rel else
              [os.path.join(ROOT, rel + ".html"), os.path.join(ROOT, rel, "index.html")]):
        if os.path.isfile(c):
            return c
    return None

def main():
    with open(os.path.join(ROOT, "sitemap.xml"), encoding="utf-8") as f:
        locs = re.findall(r"<loc>([^<]+)</loc>", f.read())
    cnt = Counter(locs)
    dups = {u: n for u, n in cnt.items() if n > 1}
    want = expected()
    missing = sorted(set(want) - set(cnt))
    nofile, bad = [], []
    for u in cnt:
        p = url_to_file(u)
        if p is None:
            nofile.append(u)
        elif blocked(p):
            bad.append(u)
    # robots.txt must not block anything the sitemap asks to be indexed (v1.6.48)
    dis = []
    rp = os.path.join(ROOT, "robots.txt")
    if os.path.exists(rp):
        dis = [l.split(":", 1)[1].strip() for l in open(rp, encoding="utf-8")
               if l.lower().startswith("disallow:") and l.split(":", 1)[1].strip()]
    robots_blocked = [u for u in cnt if any(u[len(SITE):].startswith(d) for d in dis)]
    # embeds are widgets for other sites: always noindex, never listed
    ed = os.path.join(ROOT, "embed")
    embed_indexable = [f for f in (os.listdir(ed) if os.path.isdir(ed) else [])
                       if f.endswith(".html") and not blocked(os.path.join(ed, f))]
    bad += [f"robots.txt blocks {u}" for u in robots_blocked] + [f"embed without noindex: {f}" for f in embed_indexable]
    print(f"sitemap: {len(locs)} <loc>, {len(cnt)} unique; served pages {len(want)}")
    print(f"  duplicates {len(dups)} | missing {len(missing)} | no file {len(nofile)} | noindex/redirect listed {len(bad)}")
    for name, xs in (("DUP", [f"{u} x{n}" for u, n in dups.items()]), ("MISSING", missing), ("NOFILE", nofile), ("BLOCKED", bad)):
        for x in xs[:20]:
            print(f"  {name}: {x}")
    sys.exit(1 if (dups or missing or nofile or bad) else 0)

if __name__ == "__main__":
    main()
