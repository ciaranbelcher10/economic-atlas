#!/usr/bin/env python3
"""v2.0.15 migration: schema.org structured data for the 8 main pages that had none, built from each
page's own <title>, meta description and canonical link. Idempotent (skips a page that already has it).
Run from the repo root: python3 tools/migrate_v215.py"""
import html, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://theeconomicatlas.com"
ORG = {"@type": "Organization", "name": "The Economic Atlas", "url": SITE}
APP = {"@type": "WebApplication", "applicationCategory": "BusinessApplication", "operatingSystem": "Any",
       "browserRequirements": "Requires JavaScript", "isAccessibleForFree": True,
       "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP"}}
PAGES = {"about.html": {"@type": "AboutPage"}, "contact.html": {"@type": "ContactPage"},
         "calendar.html": {"@type": "WebPage"}, "markets.html": {"@type": "WebPage"},
         "privacy.html": {"@type": "WebPage"}, "terms.html": {"@type": "WebPage"},
         "chartmaker.html": APP, "dashboard.html": APP}
changed = 0
for fn, base in PAGES.items():
    p = os.path.join(ROOT, fn); t = open(p, encoding="utf-8").read()
    if "application/ld+json" in t:
        continue
    title = html.unescape(re.search(r"<title>(.*?)</title>", t, re.S).group(1).strip())
    d = re.search(r'<meta name="description" content="([^"]*)"', t)
    c = re.search(r'<link rel="canonical" href="([^"]*)"', t)
    obj = {"@context": "https://schema.org", **base,
           "name": re.sub(r"\s*[|·]\s*The Economic Atlas$", "", title),
           "url": c.group(1) if c else SITE + "/" + fn[:-5],
           "publisher" if base["@type"].endswith("Page") else "provider": ORG,
           "isPartOf": {"@type": "WebSite", "name": "The Economic Atlas", "url": SITE}}
    if d: obj["description"] = html.unescape(d.group(1))
    block = '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False) + "</script>\n"
    i = t.find("</head>"); assert i != -1, fn
    open(p, "w", encoding="utf-8").write(t[:i] + block + t[i:]); changed += 1
print(f"migrate_v215: {changed} files changed")
