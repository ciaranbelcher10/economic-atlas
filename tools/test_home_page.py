#!/usr/bin/env python3
"""v1.9.69: the home page is short and sends people to data, without losing the map or its SEO.

Checks that the head (title, description, Open Graph, structured data) and the map script
are byte-for-byte what they were before the redesign, that every quick link resolves to a
real page, and that the visible copy stays short.
Run: python3 tools/test_home_page.py [--baseline <git ref>]   (default baseline: HEAD)
"""
import os, re, sys, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails, oks = [], 0
def check(c, m):
    global oks
    if c: oks += 1
    else: fails.append(m)

h = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
ref = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else None

def head(x): return re.sub(r"\?v=\d+", "", re.sub(r"<style\b.*?</style>", "", x[:x.index("</head>")], flags=re.S))
def map_script(x):
    m = re.search(r'<script>\s*"use strict";\s*/\* ISO 3166-1 numeric ids.*?</script>', x, re.S)
    return m.group(0) if m else ""

if ref:
    old = subprocess.run(["git", "show", f"{ref}:index.html"], cwd=ROOT, capture_output=True, text=True).stdout
    check(old and head(h) == head(old), "head (title, meta, OG, structured data; styles aside) unchanged from " + ref)
    check(map_script(old) and map_script(h) == map_script(old), "map script unchanged from " + ref)

check(re.search(r"<title>The Economic Atlas: Live Economic Data by Country</title>", h), "title kept")
check(re.search(r'<meta name="description" content="[^"]{80,}"', h), "meta description kept")
check(h.count('type="application/ld+json"') >= 2, "structured data kept")
h1 = re.findall(r"<h1\b[^>]*>(.*?)</h1>", h, re.S)
check(len(h1) == 1 and "economic data" in re.sub(r"<[^>]+>", "", h1[0]).lower(), "exactly one h1, and it says economic data")
check(re.search(r"\b62 economies\b", h), "says 62 economies (country_surfaces_gate needs it)")
check('<svg id="map"' in h and map_script(h), "map and its script present")
check('class="hero-h1"' in h and 'class="subline"' in h, "hooks for the search box and Latest ticker kept")

body = h[h.index('<header class="page">'):h.index("<footer")]
for href in re.findall(r'<a class="(?:ea-btn|home-card)"[^>]*href="([^"#:]+)"', body):
    check(os.path.exists(os.path.join(ROOT, href + ".html")) or os.path.exists(os.path.join(ROOT, href, "index.html")),
          f"quick link {href} resolves to a page")
check(len(re.findall(r'class="home-card"', body)) == 6, "six tool cards")
check(len(re.findall(r'<a class="ea-btn" href="(?:uk|us|germany|japan|china|france|india|eurozone)"', body)) == 8, "eight popular economies")
check(len(re.findall(r'href="rankings/', body)) >= 6, "popular rankings linked")
faq = re.findall(r'<details class="faq-item">\s*<summary><h3>(.*?)</h3></summary>\s*<p>(.*?)</p>', body, re.S)
check(len(faq) == 5, "five questions, each with its answer in the page")
visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<details.*?</details>", "", body, flags=re.S)))
words = len(visible.split())
check(words <= 230, f"visible copy outside the FAQ stays short ({words} words, limit 230)")
check("Seven ways to look" not in h and 'class="feature' not in h, "the long feature essays are gone")
print(f"test_home_page: {oks} ok, {len(fails)} failed")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
