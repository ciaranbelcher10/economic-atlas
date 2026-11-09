#!/usr/bin/env python3
"""v1.9.111 Lighthouse fixes: page edits made at deploy time, like migrate_v19110.py, because the
data bot rewrites pages. Idempotent: a page already done is left alone.

  1. Google Fonts stylesheet loads without blocking first paint (preload + print/onload swap,
     noscript fallback). Hand pages and generate_indicator_pages.py.
  2. One main landmark: role="main" on the wrapper that holds each page's header.page, plus
     named wrappers on Compare, Dashboard and Markets. Pages that already have one are skipped.
  3. Country pages: the headline tile box carries its row count (--hero-rows) so phones reserve
     its height before the tiles render.
  4. Country pages: clickable stat tiles take their accessible name from their visible text.
  5. Home: both intro texts ship in the page (CSS picks one per width); the map zoom hint is
     shown at full opacity (contrast).

Run from the repo root:  python3 tools/migrate_v19111.py
Exits 1 if any page is left without an expected change."""
import glob, math, os, sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
FONT_URL = "https://fonts.googleapis.com/css2?family=Nunito+Sans:wght@400;600;700&display=swap"
FONT_OLD = '<link href="' + FONT_URL + '" rel="stylesheet">'
FONT_NEW = ('<link rel="preload" as="style" href="' + FONT_URL + '">\n'
            '<link href="' + FONT_URL + '" rel="stylesheet" media="print" onload="this.media=\'all\'">\n'
            '<noscript>' + FONT_OLD + '</noscript>')
HERO_OLD = '<div class="hero" id="hero" aria-label="Headline figures"></div>'
TILE_OLD = 'div.setAttribute("aria-label",title+", view chart");'
TILE_NEW = '/* v1.9.111: name comes from the tile\'s visible text */'
SUB_FULL = ("GDP, inflation, jobs, trade and interest rates for 62 economies, updated automatically "
            "from official sources. No commentary, no forecasts.")
SUB_OLD = '<p class="subline">' + SUB_FULL + '</p>'
SUB_NEW = ('<p class="subline"><span class="sl-full">' + SUB_FULL +
           '</span><span class="sl-short">Official data for 62 economies.</span></p>')
ZOOM_OLD = "background:var(--panel); padding:2px 8px; border-radius:6px; opacity:.75;}"
ZOOM_NEW = "background:var(--panel); padding:2px 8px; border-radius:6px;}"
MAIN_FILE = {  # pages without a header.page: their content wrapper
    "compare.html": '<div class="wrap" style="padding:30px 24px 60px;">',
    "dashboard.html": '<div class="wrap">\n<div class="dash-layout" id="dashLayout">',
    "markets.html": '<div class="wrap">\n<header class="mk-hero">',
}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
        "source", "track", "wbr"}


def has_main(s):
    return "<main" in s or 'role="main"' in s


class HeaderParent(HTMLParser):
    """Offset of the start tag of the element that directly contains the first header.page."""
    def __init__(self):
        super().__init__(convert_charrefs=False); self.stack = []; self.found = None
    def handle_starttag(self, tag, attrs):
        if tag in VOID: return
        cls = (dict(attrs).get("class") or "").split()
        if self.found is None and tag == "header" and "page" in cls and self.stack:
            self.found = self.stack[-1]
        self.stack.append((tag, self.getpos(), self.get_starttag_text()))
    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag: del self.stack[i:]; break


def add_main(s, name):
    if has_main(s): return s
    if name in MAIN_FILE:
        a = MAIN_FILE[name]
        if s.count(a) < 1: return s
        return s.replace(a, a.replace('<div class="wrap"', '<div class="wrap" role="main"', 1), 1)
    p = HeaderParent(); p.feed(s); p.close()
    if not p.found or p.found[0] != "div": return s
    (line, col), tag = p.found[1], p.found[2]
    off = sum(len(l) for l in s.splitlines(True)[:line - 1]) + col
    if s[off:off + len(tag)] != tag: return s
    return s[:off] + tag[:-1] + ' role="main">' + s[off + len(tag):]


def migrate_page(name, s):
    s = s.replace(FONT_OLD, FONT_NEW, 1) if FONT_NEW not in s else s
    s = add_main(s, name)
    if HERO_OLD in s:
        rows = math.ceil(s.count("statTile(hero,") / 2)
        s = s.replace(HERO_OLD, HERO_OLD[:-7] + ' style="--hero-rows:%d"></div>' % rows, 1)
    s = s.replace(TILE_OLD, TILE_NEW)
    if name == "index.html":
        s = s.replace(SUB_OLD, SUB_NEW, 1).replace(ZOOM_OLD, ZOOM_NEW, 1)
    return s


def problems(name, s):
    out = []
    if FONT_OLD in s.replace("<noscript>" + FONT_OLD, ""): out.append("blocking font link")
    if FONT_URL in s and FONT_NEW not in s: out.append("font not migrated")
    if not has_main(s): out.append("no main landmark")
    if s.count('role="main"') + s.count("<main") > 1: out.append("more than one main")
    if 'id="hero"' in s and "--hero-rows:" not in s: out.append("hero rows missing")
    if TILE_OLD in s: out.append("tile aria-label left")
    if name == "index.html" and (SUB_NEW not in s or ZOOM_OLD in s): out.append("home intro/zoom")
    return out


def main():
    changed = 0; bad = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        name = os.path.basename(f)
        if name in GENERATED: continue
        s = open(f, encoding="utf-8").read()
        if FONT_URL not in s and not has_main(s) and 'id="hero"' not in s: continue  # not a site page
        new = migrate_page(name, s)
        if new != s: open(f, "w", encoding="utf-8").write(new); changed += 1
        for m in problems(name, new): bad.append(name + ": " + m)
    g = os.path.join(ROOT, "generate_indicator_pages.py")
    gs = open(g, encoding="utf-8").read(); gn = 0
    if FONT_NEW not in gs and FONT_OLD in gs:
        gs = gs.replace(FONT_OLD, FONT_NEW, 1); open(g, "w", encoding="utf-8").write(gs); gn = 1
    if FONT_NEW not in gs: bad.append("generate_indicator_pages.py: font not migrated")
    print(f"migrate_v19111: {changed} page(s) changed; generator {gn} edit(s)")
    if bad:
        print("migrate_v19111: FAIL\n  " + "\n  ".join(bad)); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
