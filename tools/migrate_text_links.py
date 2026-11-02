#!/usr/bin/env python3
"""v1.9.67: move every link out of running text on the hand-written pages.

Each <a> inside a paragraph or footer is replaced by its own words, and the
destination becomes a button in a row straight after that paragraph (inside
the footer, for footers). Generated regions (KEY-FIGURES block), scripts,
styles and navigation are left alone. The script is idempotent: a page with
no links left in running text is not changed, so it is safe to run on top of
whatever the data bot has committed since.

Run from the repo root:  python3 tools/migrate_text_links.py [--check]
--check reports what would change and writes nothing.
"""
import os, re, sys, glob, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {"tools", "node_modules", "og", ".github", "docs", "indicators", "embed", "rankings"}
GENERATED = {"methodology-by-economy.html", "gdp-by-country.html", "inflation-by-country.html",
             "unemployment-by-country.html", "data-status.html"}
BTN_CLASSES = {"btn", "rk-btn", "rk-cty", "glow-cta", "rkx-card", "w-badge", "lockedbtn", "item",
               "ea-btn", "ea-cty", "doc-anchor"}
PROTECT = re.compile(r"<!-- KEY-FIGURES:START.*?<!-- KEY-FIGURES:END -->|<script\b.*?</script>|<style\b.*?</style>"
                     r"|<nav\b.*?</nav>|<head\b.*?</head>|<template\b.*?</template>", re.S | re.I)
A_RE = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
COOKIE_LINK = re.compile(r'\s*<a href="contact">Questions\? Get in touch</a>\.')
CONTACT_SENT = re.compile(r'Ideas or corrections:\s*<a href="(?:\.\./)?contact">get in touch</a>\.')

def classes(attrs):
    m = re.search(r'class="([^"]*)"', attrs)
    return set(m.group(1).split()) if m else set()

def plain(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()

def label_for(attrs, inner):
    href = (re.search(r'href="([^"]*)"', attrs) or [None, ""])[1]
    t = plain(inner)
    if href.startswith("mailto:"):
        return "Email us"
    if t.lower() in ("get in touch", "questions? get in touch"):
        return "Get in touch"
    t = re.sub(r"^the\s+", "", t, flags=re.I)
    if "," in t and len(t) > 24:
        t = t.split(",")[0]
    return (t[:1].upper() + t[1:]) if t else "Open"

def button(attrs, inner, small):
    attrs = re.sub(r'\s*class="[^"]*"', "", attrs)
    attrs = re.sub(r'\s*style="[^"]*"', "", attrs)
    cls = "ea-btn sm" if small else "ea-btn"
    return f'<a class="{cls}"{attrs}>{html.escape(label_for(attrs, inner), quote=False)}</a>'

def unlink(segment, small):
    """Return (text with links replaced by their words, [buttons]) for links without a button class."""
    btns, seen = [], set()
    def sub(m):
        attrs, inner = m.group(1), m.group(2)
        if classes(attrs) & BTN_CLASSES:
            return m.group(0)
        href = (re.search(r'href="([^"]*)"', attrs) or [None, ""])[1]
        if href not in seen:
            seen.add(href)
            btns.append(button(attrs, inner, small))
        return inner
    return A_RE.sub(sub, segment), btns

def labels_of(btns):
    return [html.unescape(re.sub(r"<[^>]+>", "", b)) for b in btns]

SEP = r"(?:&middot;|\u00b7|,|\band\b|\s)*"

def drop_trailing_labels(text, btns):
    """Remove link words left dangling at the end of a footer ("... licences. Privacy &middot; Terms")."""
    labs = "|".join(re.escape(l) for l in sorted(labels_of(btns), key=len, reverse=True))
    if not labs:
        return text
    return re.sub(r"(?:" + SEP + r"(?:" + labs + r"))+" + SEP + r"\.?\s*$", "", text, flags=re.I)

def only_labels(text, btns):
    labs = "|".join(re.escape(l) for l in sorted(labels_of(btns), key=len, reverse=True))
    rest = re.sub(labs, "", plain(text), flags=re.I) if labs else plain(text)
    return not re.sub(r"[\s\u00b7,.;:]|&middot;|\band\b", "", rest)

def fix_footer(m):
    open_tag, body, close = m.group(1), m.group(2), m.group(3)
    cm = CONTACT_SENT.search(body)
    contact_href = re.search(r'href="([^"]*)"', cm.group(0)).group(1) if cm else None
    body = CONTACT_SENT.sub("Ideas or corrections are welcome.", body)
    body = re.sub(r"(<p\b[^>]*>)(.*?)</p>", lambda pm: fix_p(pm, True), body, flags=re.S)
    new, btns = unlink(body, True)
    if contact_href:
        at = next((i for i, x in enumerate(btns) if re.search(r'href="(?:\.\./)?(privacy|terms)"', x)), len(btns))
        btns.insert(at, f'<a class="ea-btn sm" href="{contact_href}">Get in touch</a>')
    if not btns:
        return m.group(0)
    if '<span id="lastUpdated"' in new:
        head, tail = new.split('<span id="lastUpdated"', 1)
        new = drop_trailing_labels(head.rstrip(), btns) + "\n " + '<span id="lastUpdated"' + tail
    else:
        new = drop_trailing_labels(new.rstrip(), btns)
    row = '\n <div class="lnk-row">' + "".join(btns) + "</div>"
    if '<span id="lastUpdated"' in new:
        new = new.replace('<span id="lastUpdated"', row.lstrip("\n ") + '\n <span id="lastUpdated"', 1)
    else:
        new = new.rstrip() + row + "\n"
    return open_tag + new + close

def fix_p(m, small=False):
    open_tag, body = m.group(1), m.group(2)
    new, btns = unlink(body, small)
    if not btns:
        return m.group(0)
    if only_labels(new, btns):          # a paragraph that was nothing but links becomes just the buttons
        return '<div class="lnk-row">' + "".join(btns) + "</div>"
    # "Spotted something wrong? Get in touch." -> the button says it; drop the echo
    for x in btns:
        lab = re.escape(html.unescape(re.sub(r"<[^>]+>", "", x)))
        new = re.sub(r"([?:])\s*" + lab + r"\.?\s*$", r"\1", new, flags=re.I)
    return f'{open_tag}{new}</p>\n<div class="lnk-row">' + "".join(btns) + "</div>"

# Links built by the UK page's own script for the MPC vote record (inside <script>, so handled as exact strings)
JS_SWAPS = [
    (r'<a href=\"" + mpcMinutesUrl(latest.date) + "\" target=\"_blank\" rel=\"noopener\" style=\"color:var(--blue);\">Read the official Summary &amp; minutes \u2192</a>',
     r'<a class=\"ea-btn sm\" href=\"" + mpcMinutesUrl(latest.date) + "\" target=\"_blank\" rel=\"noopener\">Official summary &amp; minutes</a>'),
    (r'<a href=\"" + mpcMinutesUrl(m.date) + "\" target=\"_blank\" rel=\"noopener\">Minutes \u2192</a>',
     r'<a class=\"ea-btn sm\" href=\"" + mpcMinutesUrl(m.date) + "\" target=\"_blank\" rel=\"noopener\">Minutes</a>'),
]

def transform(src):
    for old, new in JS_SWAPS:
        src = src.replace(old, new)
    parts, last, out = [], 0, []
    for pm in PROTECT.finditer(src):
        parts.append((False, src[last:pm.start()])); parts.append((True, pm.group(0))); last = pm.end()
    parts.append((False, src[last:]))
    for protected, seg in parts:
        if not protected:
            seg = COOKIE_LINK.sub("", seg)
            seg = re.sub(r"(<footer\b[^>]*>)(.*?)(</footer>)", fix_footer, seg, flags=re.S)
            seg = re.sub(r"(<p\b[^>]*>)(.*?)</p>", fix_p, seg, flags=re.S)
        out.append(seg)
    # the button styles ship in style.css v55; bump the cache-buster with them
    return re.sub(r"style\.css\?v=54\b", "style.css?v=55", "".join(out))

def targets():
    for f in sorted(glob.glob(os.path.join(ROOT, "**", "*.html"), recursive=True)):
        rel = os.path.relpath(f, ROOT)
        if rel.split(os.sep)[0] in SKIP_DIRS or rel in GENERATED:
            continue
        yield f, rel

def main(argv):
    check = "--check" in argv
    changed = []
    for f, rel in targets():
        src = open(f, encoding="utf-8").read()
        new = transform(src)
        if new != src:
            changed.append(rel)
            if not check:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(new)
    print(f"migrate_text_links: {len(changed)} page(s) {'would change' if check else 'changed'}")
    for r in changed:
        print("  " + r)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
