"""Lay out the Country Breakdowns nav (v1.7.38; restores the v1.7.20 Europe split).

Europe keeps one alphabetical list (Eurozone included): the first FIRST links
sit under the heading, the rest flow into headless continuation columns of
CONT links each, so Europe can grow past 21 countries without a new rule.
Scandinavia keeps its own column. Every region column is ordered by how many
countries it holds, largest first; ties keep their order.

Undoes the v1.7.37 sub-region columns if it finds them. Works on raw text in
every page and in generate_indicator_pages.py ("../" prefix); idempotent.

    python3 tools/nav_split.py          # apply to every page and the generator
    python3 tools/nav_split.py --check  # exit 1 if anything would change, including
                                        # generated indicators/ and rankings/ pages
"""
from __future__ import annotations

import glob
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRST, CONT = 10, 11          # links under the Europe heading; links per headless continuation column
SCANDINAVIA = {"denmark", "norway", "sweden"}
SUBREGION_HEADS = {"Western Europe", "Southern Europe", "Northern Europe", "Central & Eastern Europe"}  # v1.7.37 layout, folded back
LINK = r' <a href="(?:\.\./)?([a-z]+)"[^>]*>([^<]+)</a>\n'
PANEL = '<div class="dropdown-panel" id="macroPanel">\n'
OVERVIEW = re.compile(r' <div class="doverview">\n((?:' + LINK + r')+) </div>\n')
COLUMN = re.compile(r' <div class="dcol(?: dcont)?">\n(?: <p class="dhead">([^<]+)</p>\n)?((?:' + LINK + r')*) </div>\n')


def _links(block):
    return [(m.group(0), m.group(1), m.group(2)) for m in re.finditer(LINK, block)]


def layout(text, split_europe=True):
    p = text.find(PANEL)
    if p < 0:
        return text
    o = OVERVIEW.match(text, p + len(PANEL))
    if not o:
        return text
    pos = o.end()
    cols = []
    while True:
        m = COLUMN.match(text, pos)
        if not m:
            break
        cols.append((html.unescape(m.group(1)) if m.group(1) else None, m.group(2)))
        pos = m.end()
    if not cols:
        return text
    over = _links(o.group(1))
    europe, scand, others = [], [], []
    for head, body in cols:
        if head is None or head == "Europe" or head in SUBREGION_HEADS:
            europe += _links(body)
        elif head == "Scandinavia":
            scand += _links(body)
            others.append(("Scandinavia", None))        # keeps its place for tie order
        else:
            others.append((head, _links(body)))
    europe += [l for l in over if l[1] == "eurozone"]          # Eurozone back in the Europe list
    over = [l for l in over if l[1] != "eurozone"]
    scand += [l for l in europe if l[1] in SCANDINAVIA]
    europe = [l for l in europe if l[1] not in SCANDINAVIA]
    by_name = lambda l: l[2].lower()
    if scand and not any(h == "Scandinavia" for h, _ in others):
        others.append(("Scandinavia", None))            # folded out of the v1.7.37 layout: its old place, last
    groups = [("Europe", sorted(europe, key=by_name))] + [
        (h, sorted(scand, key=by_name) if h == "Scandinavia" else l) for h, l in others]
    # Regions with more countries come first (Europe leads); ties keep their current order.
    groups = [g for _, g in sorted(enumerate(groups), key=lambda ig: (-len(ig[1][1]), ig[0]))]
    out = " <div class=\"doverview\">\n" + "".join(l[0] for l in over) + " </div>\n"
    for head, links in groups:
        h = f' <p class="dhead">{html.escape(head, quote=False)}</p>\n'
        if head == "Europe" and split_europe:
            out += ' <div class="dcol">\n' + h + "".join(l[0] for l in links[:FIRST]) + " </div>\n"
            rest = links[FIRST:]
            while rest:
                out += ' <div class="dcol dcont">\n' + "".join(l[0] for l in rest[:CONT]) + " </div>\n"
                rest = rest[CONT:]
        else:
            out += ' <div class="dcol">\n' + h + "".join(l[0] for l in links) + " </div>\n"
    return text[:o.start()] + out + text[pos:]


# add_country.py API: merge() puts Europe in one column for the insert, split() lays it out again.
def merge(text, region="Europe"):
    return layout(text, split_europe=False)


def split(text, region="Europe"):
    return layout(text)


def files():
    out = [Path(p).name for p in sorted(glob.glob(str(ROOT / "*.html"))) if Path(p).name != "404.html"]
    return out + ["generate_indicator_pages.py"]


def generated():
    """Pipeline output (never committed): checked, never written."""
    return [str(Path(p).relative_to(ROOT)) for d in ("indicators", "rankings")
            for p in sorted(glob.glob(str(ROOT / d / "*.html")))]


def main():
    check = "--check" in sys.argv
    changed = []
    if check:
        stale = [rel for rel in generated()
                 if layout((ROOT / rel).read_text(encoding="utf-8")) != (ROOT / rel).read_text(encoding="utf-8")]
        if stale:
            print(f"nav layout: {len(stale)} generated page(s) not laid out yet (regenerate: python3 generate_indicator_pages.py), e.g. {stale[0]}")
            changed += stale
    for rel in files():
        p = ROOT / rel
        t = p.read_text(encoding="utf-8")
        new = layout(t)
        if new != t:
            changed.append(rel)
            if not check:
                p.write_text(new, encoding="utf-8")
    print(f"nav layout: {len(changed)} file(s) {'would change' if check else 'changed'}")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
