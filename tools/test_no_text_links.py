#!/usr/bin/env python3
"""v1.9.66: no links inside running text anywhere on the site.

Ciaran's rule: every destination is a button, never an underlined link in a
sentence. A link counts as "in running text" when it sits inside a p, li, td,
th, dd, footer, figcaption, blockquote, small or label element and carries no
button class. Navigation (<nav>, menus, dropdowns) is not running text.

Scopes:
  --generated  pages built by generate_indicator_pages.py (must be 0)
  --all        every page in the repo (must be 0 since v1.9.67), plus links built inside page scripts
  --root DIR   scan another checkout (default: the repo this file is in)
  --regen      rebuild the generated pages in a temp folder first (as generated_pages_gate does),
               so the check does not wait for the next data run to regenerate the live pages
Run: python3 tools/test_no_text_links.py --generated
"""
import os, re, sys, glob
from html.parser import HTMLParser

BUTTON_CLASSES = {"btn", "rk-btn", "rk-cty", "glow-cta", "rkx-card", "w-badge",
                  "lockedbtn", "item", "ea-btn", "ea-cty", "doc-anchor"}
TEXT_TAGS = {"p", "li", "td", "th", "dd", "footer", "figcaption", "blockquote", "small", "label"}
SKIP_TAGS = {"nav", "script", "style", "template", "head"}
SKIP_CLASSES = {"dropdown", "dropdown-panel", "menu", "nav-menu", "mnav", "drawer"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

class Scan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.bad = [], []
    def skipping(self):
        return any(t in SKIP_TAGS or (c & SKIP_CLASSES) for t, c in self.stack)
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = set((a.get("class") or "").split())
        if tag == "a" and not self.skipping() and any(t in TEXT_TAGS for t, _ in self.stack):
            if not (cls & BUTTON_CLASSES):
                self.bad.append((self.getpos()[0], a.get("href", "")))
        if tag not in VOID:
            self.stack.append((tag, cls))
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

def files(root, scope):
    gen = (glob.glob(os.path.join(root, "indicators", "*.html")) + glob.glob(os.path.join(root, "embed", "*.html"))
           + glob.glob(os.path.join(root, "rankings", "*.html"))
           + [os.path.join(root, f) for f in ("methodology-by-economy.html",) if os.path.exists(os.path.join(root, f))])
    if scope == "generated":
        return sorted(gen)
    out = []
    for f in glob.glob(os.path.join(root, "**", "*.html"), recursive=True):
        rel = os.path.relpath(f, root)
        if rel.split(os.sep)[0] in ("tools", "node_modules", "og", ".github", "docs"):
            continue
        out.append(f)
    return sorted(out)

def scan(path):
    s = Scan()
    s.feed(open(path, encoding="utf-8", errors="ignore").read())
    return s.bad

JS_LINK = re.compile(r"""<a href=[^>]{0,200}?>(?!<title>|<text\b)""")

def script_links(root):
    """Links the page scripts build as strings. Chart links (<a> wrapping an SVG <title> or <text>) are not text."""
    bad = []
    for f in glob.glob(os.path.join(root, "*.html")):
        s = open(f, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", s, re.S):
            for x in JS_LINK.finditer(m.group(1)):
                bad.append((os.path.basename(f), x.group(0)[:80]))
    return bad

def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    scope = "all" if "--all" in argv else "generated"
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    if "--regen" in argv:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import generated_pages_gate as gpg
        tmp, r, _ = gpg.stage(root, os.path.join(root, "generate_indicator_pages.py"))
        if r.returncode != 0:
            print(r.stderr[-2000:]); print("0 ok, 1 failed"); return 1
        root = tmp
    fl = files(root, scope)
    total, worst = 0, []
    for f in fl:
        b = scan(f)
        if b:
            total += len(b)
            worst.append((len(b), os.path.relpath(f, root), b[0]))
    worst.sort(reverse=True)
    print(f"no-text-links ({scope}): {len(fl)} pages scanned, {total} links in running text")
    for n, f, (line, href) in worst[:15]:
        print(f"  {n:4d}  {f}  (first at line {line}: {href})")
    if scope == "generated":
        ok = len(fl) > 1000 and total == 0
        print(f"{1 if ok else 0} ok, {0 if ok else 1} failed")
        return 0 if ok else 1
    js = script_links(root)
    print(f"  {len(js)} link(s) built as text by page scripts")
    for f, x in js[:10]:
        print(f"    {f}: {x}")
    checks = [len(fl) > 2000, total == 0, not js]
    print(f"{sum(checks)} ok, {len(checks) - sum(checks)} failed")
    return 0 if all(checks) else 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
