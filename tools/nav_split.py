"""Lay out the European columns of the site nav (v1.7.37; replaces the v1.7.20 split).

Europe outgrew one column, then two. The nav now shows four European
columns by sub-region, each alphabetical, and Eurozone sits under Overview:

    Western Europe | Southern Europe | Northern Europe | Central & Eastern Europe

Only the nav changes. Data regions (spec "region", REGION_OF, REGION_GROUPS)
keep "Europe" and "Scandinavia", so Compare, Rankings and the calendar group
countries exactly as before.

Every European country page, present or planned, is listed in NAV_GROUPS.
A European country missing from it stops the run, so a new country can't
silently land in the wrong column.

The same markup appears in every page and in generate_indicator_pages.py
(with a "../" prefix), so this works on raw text and is idempotent.
tools/add_country.py calls split() after inserting a link.

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
NAV_GROUPS = [
    ("Western Europe", ["austria", "belgium", "france", "germany", "ireland", "luxembourg",
                        "netherlands", "switzerland", "uk"]),
    ("Southern Europe", ["cyprus", "greece", "italy", "malta", "portugal", "spain", "turkey"]),
    ("Northern Europe", ["denmark", "estonia", "finland", "latvia", "lithuania", "norway", "sweden"]),
    ("Central & Eastern Europe", ["bulgaria", "croatia", "czechia", "hungary", "poland", "romania",
                                  "slovakia", "slovenia"]),
]
MAX_PER_COLUMN = 11
EUROPE_REGIONS = ("Europe", "Scandinavia")          # data regions whose links live in these columns
LEGACY_HEADS = {"Europe", "Scandinavia"} | {g for g, _ in NAV_GROUPS}
SLUG_GROUP = {s: g for g, ss in NAV_GROUPS for s in ss}
LINK = r' <a href="(?:\.\./)?([a-z]+)"[^>]*>([^<]+)</a>\n'
PANEL = '<div class="dropdown-panel" id="macroPanel">\n'
OVERVIEW = re.compile(r' <div class="doverview">\n((?:' + LINK + r')+) </div>\n')
COLUMN = re.compile(r' <div class="dcol(?: dcont)?">\n(?: <p class="dhead">([^<]+)</p>\n)?((?:' + LINK + r')*) </div>\n')


def head_html(group):
    return f' <p class="dhead">{html.escape(group, quote=False)}</p>\n'


def group_of(slug):
    if slug not in SLUG_GROUP:
        raise SystemExit(f"nav: {slug} is European but not in tools/nav_split.py NAV_GROUPS; add it to a sub-region")
    return SLUG_GROUP[slug]


def _links(block):
    return [(m.group(0), m.group(1), m.group(2)) for m in re.finditer(LINK, block)]


def layout(text):
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
    europe, other_cols = [], []
    for head, body in cols:
        if head is None or head in LEGACY_HEADS:      # continuation columns only ever followed Europe
            europe += _links(body)
        else:
            other_cols.append((head, body))
    eurozone = [l for l in over if l[1] == "eurozone"] + [l for l in europe if l[1] == "eurozone"]
    over = [l for l in over if l[1] != "eurozone"]
    europe = [l for l in europe if l[1] != "eurozone"]
    out = " <div class=\"doverview\">\n" + "".join(l[0] for l in over + eurozone[:1]) + " </div>\n"
    for g, _ in NAV_GROUPS:
        members = sorted([l for l in europe if group_of(l[1]) == g], key=lambda l: l[2].lower())
        if not members:
            continue
        if len(members) > MAX_PER_COLUMN:
            raise SystemExit(f"nav: {g} has {len(members)} links, more than {MAX_PER_COLUMN}")
        out += ' <div class="dcol">\n' + head_html(g) + "".join(l[0] for l in members) + " </div>\n"
    for head, body in other_cols:
        out += f' <div class="dcol">\n <p class="dhead">{html.escape(head, quote=False)}</p>\n{body} </div>\n'
    return text[:o.start()] + out + text[pos:]


# add_country.py API (kept from v1.7.20)
def merge(text, region="Europe"):
    return text


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
