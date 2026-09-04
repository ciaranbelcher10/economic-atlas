"""Fetch upcoming Japan GDP and CPI release dates and write
data-calendar-jp-stats.json (separate from fetch_calendar_jp.py, which
covers BoJ RATE decisions -- this one covers actual data releases from
the Cabinet Office and the Statistics Bureau, different publishers
entirely).

Run:  python3 fetch_calendar_jp_stats.py
No API key needed -- public government pages.

Sources, both confirmed live on 2026-09-03 as real markdown-style tables
published a full year ahead:
  GDP -> https://www.esri.cao.go.jp/en/sna/kouhyou/kouhyou_top.html
         (Cabinet Office, Economic and Social Research Institute)
  CPI -> https://www.stat.go.jp/english/data/cpi/1582.html
         (Statistics Bureau, Ministry of Internal Affairs and Communications)

Both are genuinely excellent sources: full year of dates, published well
in advance, in a clean HTML table with predictable row structure. Of
everything found across two overnight sessions researching this,
Japan's CPI schedule is one of the cleanest -- exact dates for all 12
months of 2026 in one small table.

NOT YET RUN LIVE -- esri.cao.go.jp and stat.go.jp aren't in this
sandbox's network allowlist. The parsing logic below is written against
the real table structures fetched directly (see docstrings on each
function), not guessed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

GDP_URL = "https://www.esri.cao.go.jp/en/sna/kouhyou/kouhyou_top.html"
CPI_URL = "https://www.stat.go.jp/english/data/cpi/1582.html"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

# e.g. "Tuesday, September 8, 2026" or "Monday, November 16, 2026" -- the
# GDP table's date column always spells out full weekday + month + day +
# year, confirmed against the real fetched table.
GDP_DATE_RE = re.compile(
    rf"[A-Za-z]+,\s+({MONTH_RE})\s+(\d{{1,2}}),\s+(\d{{4}})", re.I
)


def fetch_gdp_events(today) -> list[dict]:
    try:
        r = requests.get(GDP_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"WARNING: GDP fetch failed: {e}", file=sys.stderr)
        return []

    text = re.sub(r"<[^>]+>", " ", r.text)
    # Only take the "Quarterly Estimates of GDP" table, not the other
    # tables further down the same page (net capital stocks, household
    # income, etc.) -- slice to the section between that heading and the
    # next one.
    start = text.find("Quarterly Estimates of GDP")
    end = text.find("Annual Report on National Accounts", start)
    section = text[start:end] if start != -1 and end != -1 else text

    events = []
    for m in GDP_DATE_RE.finditer(section):
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today:
            continue
        events.append({
            "date": d.isoformat(),
            "country": "Japan",
            "concept": "gdp",
            "name": "Quarterly GDP estimate",
            "source": "esri.cao.go.jp/en/sna/kouhyou/kouhyou_top.html",
            "time": "8:50am JST",
        })
    return events


def fetch_cpi_events(today) -> list[dict]:
    """The CPI table has two side-by-side series (Japan national, Tokyo
    preliminary) in real <table><tr><td> cells. Flattening tags to plain
    text (the approach used elsewhere in this script, and in every other
    fetch_calendar_*.py script tonight) loses the cell boundaries between
    the two series and makes the row structure genuinely ambiguous to
    recover with a regex -- confirmed by testing: a regex expecting a
    literal '|' separator matched zero rows against realistically
    flattened text, since HTML tables don't render with pipe characters
    once tags are stripped. Rather than ship a regex that looks
    plausible but was shown not to work, this uses real table parsing
    (BeautifulSoup) to walk actual <tr>/<td> boundaries, which is the
    correct tool for this specific structure."""
    try:
        r = requests.get(CPI_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"WARNING: CPI fetch failed: {e}", file=sys.stderr)
        return []

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("WARNING: BeautifulSoup4 not installed (pip install beautifulsoup4) "
              "-- required for this parser, since the two-series table can't be "
              "reliably read from flattened text (see docstring).", file=sys.stderr)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.find("table")
    if not table:
        print("WARNING: no <table> found on the CPI schedule page -- page "
              "structure may have changed.", file=sys.stderr)
        return []

    events = []
    year = today.year
    for row in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        # Expected column order confirmed from the real fetched table:
        # [Japan survey month, Japan release date, Tokyo survey month,
        #  Tokyo release date, remarks]. Japan's release-date cell (index
        # 1) is what we want; it's a bare "Month Day" or, on year-crossing
        # rows, "Month Day, Year".
        if len(cells) < 2:
            continue
        release_cell = cells[1]
        m = re.match(rf"({MONTH_RE})\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?", release_cell, re.I)
        if not m:
            continue
        month_name, day = m.group(1).lower(), int(m.group(2))
        cell_year = int(m.group(3)) if m.group(3) else year
        if month_name not in MONTH_NAMES:
            continue
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(cell_year, month, day).date()
        except ValueError:
            continue
        # Bare "Month Day" cells (no explicit year) are simply within
        # this table's current year -- if that resolves to the past,
        # it's a row that's already happened, not a hint to roll forward
        # a year. (Caught by testing: an earlier version of this rolled
        # every past bare-year date forward, which wrongly pushed
        # already-happened rows like "August 21" into next year instead
        # of just skipping them.) Only skip past dates; never roll them.
        if d < today:
            continue
        events.append({
            "date": d.isoformat(),
            "country": "Japan",
            "concept": "cpi",
            "name": "Consumer Price Index",
            "source": "stat.go.jp/english/data/cpi/1582.html",
            "time": "8:30am JST",
        })
    return events


def main():
    today = datetime.now(timezone.utc).date()
    gdp_events = fetch_gdp_events(today)
    cpi_events = fetch_cpi_events(today)

    if not gdp_events:
        print("WARNING: parsed zero GDP events -- verify GDP_DATE_RE against "
              "a fresh fetch.", file=sys.stderr)
    if not cpi_events:
        print("WARNING: parsed zero CPI events -- the CPI table parser is "
              "a simplified stand-in (see fetch_cpi_events docstring), "
              "needs real HTML table parsing (e.g. via BeautifulSoup) "
              "against the live page before this is trustworthy, not "
              "just the flattened text used for research tonight.",
              file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Japan",
        "events": gdp_events + cpi_events,
    }
    with open("data-calendar-jp-stats.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(gdp_events)} GDP + {len(cpi_events)} CPI Japan events.")


if __name__ == "__main__":
    main()
