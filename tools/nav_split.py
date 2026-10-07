"""Split a long region column of the site nav into two columns (v1.7.20).

Europe outgrew one column. The first column keeps the heading and the first
FIRST links; a headless continuation column takes up to CONT more (one more
than FIRST, because it has no heading row, so both columns end level).
Links stay alphabetical across both columns.

The same markup appears in every page and in generate_indicator_pages.py
(with a "../" prefix), so this works on raw text and is idempotent:
merge() folds any existing continuation back into the region's list,
split() lays it out again. tools/add_country.py calls both around its nav
insertion, so a new European country lands in the right column.

    python3 tools/nav_split.py          # apply to every page and the generator
    python3 tools/nav_split.py --check  # exit 1 if anything would change, including
                                        # generated indicators/ and rankings/ pages
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLIT = {"Europe": (10, 11)}       # region: (links under the heading, links in the continuation)
LINK = r' <a href="[^"]*"[^>]*>[^<]+</a>\n'
CONT_OPEN = ' <div class="dcol dcont">\n'


def _block(text, region):
    """(start, end, links) of the region's column(s): heading through its links
    plus an immediately following continuation column, if any."""
    head = f' <p class="dhead">{region}</p>\n'
    i = text.find(head)
    if i < 0:
        return None
    j = i + len(head)
    links = []
    while True:
        m = re.match(LINK, text[j:])
        if not m:
            break
        links.append(m.group(0)); j += m.end()
    m = re.match(r' </div>\n' + re.escape(CONT_OPEN) + r'((?:' + LINK + r')+) </div>\n', text[j:])
    if m:
        links += re.findall(LINK, m.group(1))
        j += m.end() - len(" </div>\n")   # keep the closing </div> of the last column outside
    return i, j, links


def _key(link):
    return re.search(r">([^<]+)</a>", link).group(1).lower()


def merge(text, region="Europe"):
    b = _block(text, region)
    if not b:
        return text
    i, j, links = b
    return text[:i] + f' <p class="dhead">{region}</p>\n' + "".join(links) + text[j:]


def split(text, region="Europe"):
    b = _block(text, region)
    if not b or region not in SPLIT:
        return text
    i, j, links = b
    first, cont = SPLIT[region]
    links = sorted(links, key=_key)
    if len(links) > first + cont:
        raise SystemExit(f"{region} has {len(links)} links: more than {first} + {cont}; add a third column rule")
    out = f' <p class="dhead">{region}</p>\n' + "".join(links[:first])
    if len(links) > first:
        out += " </div>\n" + CONT_OPEN + "".join(links[first:])
    return text[:i] + out + text[j:]


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
        stale = []
        for rel in generated():
            t = (ROOT / rel).read_text(encoding="utf-8")
            new = t
            for region in SPLIT:
                new = split(merge(new, region), region)
            if new != t:
                stale.append(rel)
        if stale:
            print(f"nav split: {len(stale)} generated page(s) not split yet (regenerate: python3 generate_indicator_pages.py), e.g. {stale[0]}")
            changed += stale
    for rel in files():
        p = ROOT / rel
        t = p.read_text(encoding="utf-8")
        new = t
        for region in SPLIT:
            new = split(merge(new, region), region)
        if new != t:
            changed.append(rel)
            if not check:
                p.write_text(new, encoding="utf-8")
    print(f"nav split: {len(changed)} file(s) {'would change' if check else 'changed'}")
    return 1 if (check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
