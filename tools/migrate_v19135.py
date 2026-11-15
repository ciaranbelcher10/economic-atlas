#!/usr/bin/env python3
"""v1.9.135 text review, site-wide patterns (claude/v1.9.135-text-review.md, section A).

The site's text names, defines and explains the figures. It does not argue for the site, describe
its roadmap, or say what it does not do. This removes the notes that fail that test on every page:

A1  Miscellaneous section note ("useful context that sits outside the headline figures")
A2/3 "On the roadmap: ..." section notes
A4  Markets section note ("market prices, not government statistics ... never a news aggregator")
A5  footer "Productivity ... is currently only tracked for the UK and US, not yet for X."
A6  footer "Series codes are shown ...; figures are the latest published observations and are subject
    to revision." -> "Figures are the latest published and may be revised."; "Ideas or corrections are
    welcome." removed (the Get in touch link stays)
A7  "..., so the latest year is a year ahead of the IMF's." comparison dropped
og:image:alt no longer says "no commentary"

Idempotent: run twice, expect "N changed" then "0 changed".
"""
import glob, os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
GENERATED_ROOT = {"methodology-by-economy.html", "data-status.html"}

SECNOTE_DROP = re.compile(
    r'[ \t]*<p class="secnote">(?:'
    r'Foreign direct investment, business confidence and population: useful context that sits outside the headline figures\.'
    r'|On the roadmap:[^<]*'
    r'|Government bond yields and exchange rates are market prices, not government statistics,[^<]*'
    r')</p>\n?')


def fix(s):
    s = SECNOTE_DROP.sub("", s)
    # Australia: stale (unemployment has been OECD monthly since v1.9.131)
    s = re.sub(r'[ \t]*<p class="secnote">Unemployment here is quarterly, not monthly: the ABS itself publishes a monthly\s*figure, but the FRED mirror wired in here is only quarterly\. On the roadmap: a monthly source,\s*plus employment and participation rates\.</p>\n?', "", s)
    # key-figures box (generated; generate_indicator_pages.py writes the same text from v1.9.135)
    s = s.replace("<p>Each figure is the latest published by the source named. Each name opens that indicator\u2019s page with its full history.</p>", "<p>Select a name for its full history.</p>")
    # Section notes: say what the figure is; no "we", no defending choices, no narrating the chart
    s = re.sub(r"The chart above shows the combined trade balance \(exports minus imports\)\. Exports and imports as individual time series aren't yet wired to a verified live source for ([^,<]+), a known gap, not shown here rather than estimated\.",
               r"Exports and imports are not available separately for \1, so only the trade balance is shown.", s)
    s = re.sub(r"We have not yet found a free official source for (.+?)'s 10-year government bond yield, so only the exchange rate is shown here\.",
               r"No 10-year government bond yield is available for \1.", s)
    s = s.replace(", actual years only, so estimates and projections never appear as data.", ", actual years only.")
    s = s.replace(" If the latest observation is too old to show as current, the CPI tile is left out rather than shown.", "")
    s = re.sub(r" [A-Z][A-Za-z ]+ (?:usually |almost always )?imports (?:far |much )?more goods than it exports(?: every month| in most months)?\.", "", s)
    s = s.replace("Goods trade is Eurostat's monthly total with the rest of the world, in euros.", "Goods only, in euros.")
    s = s.replace("Goods trade only. Services aren't covered by this data source and aren't shown here, so relationships that lean heavily on services may be understated.", "Goods only; services are not included.")
    s = s.replace("Services aren't covered by this data source and aren't shown here, so relationships that lean heavily on services may be understated.", "Services are not included.")
    s = s.replace('"Calculated: complete calendar years of GDP divided by that year\'s population (World Bank)"', '"Calculated: GDP \u00f7 population (World Bank), calendar years"')
    s = s.replace('"Calculated: complete calendar years of GDP divided by that year\'s population (Eurostat, government-controlled area, the same area as GDP)"', '"Calculated: GDP \u00f7 population (Eurostat, government-controlled area), calendar years"')
    s = s.replace(" This is the deposit facility rate specifically, one of the ECB's three main policy rates.", "")
    s = s.replace("GDP is Eurostat's quarterly national accounts, seasonally and calendar adjusted. Figures before", "Seasonally and calendar adjusted. Figures before")
    # roadmap sentences inside longer notes, and the mini-map key
    s = re.sub(r'\s*On the roadmap: employment and participation rates, and wage growth\.', "", s)
    s = s.replace(': "On the roadmap";', ': "Not covered";')
    s = s.replace('</span>On the roadmap</span>', '</span>Not covered</span>')
    s = re.sub(r'\s*Productivity \(GDP per hour worked\) is currently only tracked for the UK and US, not yet for [^.<]+\.', "", s)
    s = re.sub(r'Series codes are shown with each metric;\s*figures are the latest published observations and are subject to revision\.',
               "Figures are the latest published and may be revised.", s)
    s = re.sub(r'\s*Ideas or corrections are welcome\.', "", s)
    s = s.replace(", so the latest year is a year ahead of the IMF's.", ".")
    s = s.replace(", so the latest year is a year ahead of the IMF’s.", ".")
    s = s.replace('content="The Economic Atlas, official economic data, updated automatically, no commentary."',
                  'content="The Economic Atlas, official economic data for 62 economies."')
    return s


def main():
    changed = checked = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "*.html"))):
        if os.path.basename(f) in GENERATED_ROOT:
            continue
        s0 = open(f, encoding="utf-8").read()
        s = fix(s0)
        checked += 1
        if s != s0:
            open(f, "w", encoding="utf-8").write(s)
            changed += 1
    print(f"{checked} page(s) checked, {changed} changed")


if __name__ == "__main__":
    main()
