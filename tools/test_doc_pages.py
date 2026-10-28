#!/usr/bin/env python3
"""The reference pages fit the site (v1.9.16): /methodology and /methodology-by-economy.

  1. doc.css uses only the site's own design tokens: every var(--x) is defined in style.css for BOTH the light
     (:root) and dark ([data-theme="dark"]) themes, and the file carries no colours of its own (the only rgba
     allowed is a box-shadow);
  2. methodology.html is built from the site's components: its head links indicator.css and doc.css, it has one
     h1, no inline style attributes in its content, no charting library, a contents list whose links all resolve,
     eight sections, thirty accordions each with a unique id, and every local link in it resolves;
  3. doc.js is dependency free and makes no network requests;
  4. the pages behave: tools/test_doc_pages.js loads both with their real doc.js in jsdom (filter, regions, empty
     state, anchors, accordions). It needs node and jsdom 24 (NODE_PATH), as the other jsdom gates do.

The by-economy page's own structure is checked by tools/generated_pages_gate.py, which generates it.
Run from the repo root:  python3 tools/test_doc_pages.py
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
        print("FAIL", msg)


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. tokens
css_raw, style = read("doc.css"), read("style.css")
css = re.sub(r"/\*.*?\*/", "", css_raw, flags=re.S)      # comments may name tokens; only declarations count
root_block = re.search(r":root\s*\{(.*?)\}", style, re.S).group(1)
dark_block = re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}', style, re.S).group(1)
light = set(re.findall(r"(--[a-z0-9-]+)\s*:", root_block))
dark = set(re.findall(r"(--[a-z0-9-]+)\s*:", dark_block))
used = set(re.findall(r"var\((--[a-z0-9-]+)", css))
check(used, "doc.css uses no design tokens at all")
check(used <= light, f"doc.css uses tokens missing from the light theme: {sorted(used - light)}")
check(used <= dark, f"doc.css uses tokens missing from the dark theme: {sorted(used - dark)}")
for prop, val in re.findall(r"([a-z-]+)\s*:\s*([^;{}]+);", css):
    if re.search(r"#[0-9a-fA-F]{3,8}\b|\brgb\(|\bhsla?\(", val):
        check(False, f"doc.css carries its own colour in '{prop}: {val.strip()}'")
    if "rgba(" in val and prop != "box-shadow":
        check(False, f"doc.css uses rgba() in '{prop}': only a box-shadow may")
check("@media (max-width:640px)" in css, "doc.css has no mobile layout")
check("prefers-reduced-motion" in css, "doc.css ignores reduced motion")
check(":focus-visible" in css, "doc.css styles no focus state")
for sel in (".doc-searchbox", ".doc-search", ".doc-search-clear", ".doc-search-icon", ".doc-actions", ".doc-chip", ".doc-count"):
    check(re.search(r"(?m)^" + re.escape(sel) + r"\s*\{", css), f"doc.css has no rule of its own for {sel}")
loose = re.findall(r"\.doc-sec a(?!:not\(\.btn\))[^{,]*", css)
check(not loose, f"doc.css restyles the site's own buttons inside sections: {loose[:2]}")
check(re.search(r"\.doc-sec a:not\(\.btn\)\s*\{", css), "doc.css has no link style for running text inside sections")

# ---------------------------------------------------------------- 2. methodology.html
h = read("methodology.html")
head = h.split("</head>")[0]
for asset in ("style.css", "mobile.css", "indicator.css", "doc.css"):
    check(re.search(r'<link[^>]*stylesheet[^>]*href="%s(\?[^"]*)?"' % re.escape(asset), head), f"methodology.html does not link {asset}")
check(re.search(r'<script[^>]*src="doc\.js(\?[^"]*)?"', h), "methodology.html does not load doc.js")
check("chart.umd" not in h and "indicator-kit" not in h, "methodology.html must not load the charting library or the indicator kit")
a, b = h.find("<main"), h.find("</main>")
main = h[a:b]
check(a > 0 and b > a, "methodology.html has no <main>")
check(len(re.findall(r"<h1[ >]", main)) == 1, "methodology.html needs exactly one h1 in its content")
check(not re.search(r"\sstyle=", main), "methodology.html still has inline style attributes in its content")
check('class="roadmap"' not in main and 'header class="page"' not in main, "methodology.html still uses the old roadmap/page containers in its content")
secs = re.findall(r'<section class="panel ind-panel doc-sec" id="([^"]+)">', main)
check(len(secs) == 8 and len(set(secs)) == 8, f"expected 8 distinct sections, found {secs}")
toc = re.search(r'<nav class="panel ind-panel doc-toc".*?</nav>', main, re.S)
toc_ids = re.findall(r'href="#([^"]+)"', toc.group(0)) if toc else []
check(toc_ids == secs, f"the contents list must link the 8 sections in order: {toc_ids}")
det = re.findall(r'<details class="doc-detail" id="([^"]+)"><summary>(.*?)</summary>', main, re.S)
check(len(det) == 30 and len({i for i, _ in det}) == 30 and all(i.startswith("limit-") and s.strip() for i, s in det),
      f"expected 30 accordions with unique limit- ids and a summary, found {len(det)}")
check(re.search(r'<footer class="ind-wrap doc-foot">', h), "methodology.html footer is not aligned with the content column")
check(re.search(r'<a class="btn" href="methodology-by-economy">', main), "methodology.html must offer the by-economy page as a button")
check(re.search(r'<a class="btn ghost" href="contact">', main), "methodology.html must offer contact as a button")
prose = re.sub(r'<nav class="panel ind-panel doc-toc".*?</nav>', "", main, flags=re.S)
stray = re.findall(r'<(p|li)\b[^>]*>(?:(?!</\1>).)*?<a\s(?![^>]*class="btn)[^>]*>(.*?)</a>', prose, re.S)
check(not stray, f"methodology.html has hyperlinks inside running text (use a button): {[x[1][:40] for x in stray][:3]}")
for key in ("Known limitations", "Dollarise", "Make it real", "Seasonal adjustment", "Where the data comes from"):
    check(key in main, f"methodology.html lost its '{key}' content")
for ref in re.findall(r'(?:href|src)="([^"#][^"]*)"', main + h[b:b + 600]):
    if re.match(r"(https?:|mailto:|tel:|data:|javascript:|//)", ref):
        continue
    p = ref.split("#")[0].split("?")[0]
    cands = [ROOT / p, ROOT / (p + ".html")]
    check(any(c.is_file() for c in cands), f"methodology.html: link '{ref}' does not resolve")

# ---------------------------------------------------------------- 3. doc.js
js = read("doc.js")
check("use strict" in js, "doc.js is not in strict mode")
check(not re.search(r"https?://|fetch\(|XMLHttpRequest|\bimport\b|require\(", js), "doc.js must be dependency free and make no network requests")
check("localStorage" not in js and "document.cookie" not in js, "doc.js must not store anything")

# ---------------------------------------------------------------- 4. behaviour in jsdom
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
env.setdefault("NODE_PATH", "/tmp/node_modules")
r = subprocess.run(["node", str(ROOT / "tools" / "test_doc_pages.js")], capture_output=True, text=True, env=env, timeout=240)
tail = [ln for ln in r.stdout.splitlines() if ln.strip()]
check(r.returncode == 0 and tail and "0 failures" in tail[-1],
      f"jsdom behaviour test failed (rc {r.returncode}): {' | '.join(tail[-4:])[:400]} {r.stderr[-200:]}")

print("test_doc_pages:", "FAILED" if fails else "ok", f"({len(fails)} failures)",
      "| " + tail[-1] if tail else "")
sys.exit(1 if fails else 0)
