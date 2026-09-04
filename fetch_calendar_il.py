"""Fetch upcoming Bank of Israel interest rate announcement dates and
write data-calendar-il.json.

Run:  python3 fetch_calendar_il.py
No API key needed -- public Bank of Israel page.

Source: https://www.boi.org.il/en/economic-roles/monetary-policy/interest-rate-announcement-dates-2026/
-- confirmed live tonight (this page 404'd/bot-checked on a first attempt
earlier in the session, then fetched cleanly on retry -- worth a retry
if this script hits the same wall, rather than assuming the source is
unreachable). It's a genuinely clean official table: eight rows for the
year, each with Press conference / Research Department Staff Forecast /
Maintenance period Start Date / Start Date / Publication Date columns,
all in DD/MM/YYYY format. The rate decision itself is what "Publication
Date" means (announced 16:00 local time on that date); a blank in the
"Press conference" column just means that particular decision isn't
accompanied by one -- confirmed real, not a scraping gap (4 of the 8
2026 dates have no press conference: Feb, May, Sep, Nov).

Confirmed directly tonight: Israel's September 2026 decision already
happened (1 September, before this calendar's "today" of 3 September),
and the next one is 21 October -- correctly outside a September
calendar's window, not a gap in coverage.

There's a second page (interest-rate-announcement-dates-2027-2028) for
future years, linked directly from this one -- worth following once
this year's list runs out, rather than re-guessing a URL pattern.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.boi.org.il/en/economic-roles/monetary-policy/interest-rate-announcement-dates-2026/"

# DD/MM/YYYY -- confirmed against the real fetched table (Israel uses
# day-first dates throughout this page, not US-style month-first).
DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Bank of Israel page: {e}", file=sys.stderr)
        print("NOTE: this page bot-checked a first fetch attempt earlier "
              "tonight and worked cleanly on retry -- worth trying again "
              "before concluding the source is broken.", file=sys.stderr)
        sys.exit(1)

    text = r.text

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("WARNING: BeautifulSoup4 not installed (pip install beautifulsoup4) "
              "-- required, since this table has irregular blank cells that "
              "break a flat regex approach (see below).", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table")
    if not table:
        print("WARNING: no <table> found on the page -- structure may have "
              "changed.", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(timezone.utc).date()
    events = []
    for row in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        # "Publication Date" is always the LAST of the 5 columns,
        # regardless of which earlier cells (press conference, forecast)
        # are blank for that row -- confirmed against the real table:
        # 4 of 8 2026 rows have blank press-conference/forecast cells,
        # but Publication Date is populated in every row. Using column
        # position (not counting all dates found in the row flatly) is
        # what makes this robust to those blanks.
        if len(cells) < 5:
            continue
        m = DATE_RE.match(cells[4])
        if not m:
            continue
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today:
            continue
        events.append({
            "date": d.isoformat(),
            "country": "Israel",
            "concept": "rate_decision",
            "name": "Bank of Israel interest rate announcement",
            "source": "boi.org.il (official 2026 announcement dates table)",
            "time": "4:00pm local time",
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming events -- either the table "
              "structure changed, or (more likely late in the year) this "
              "year's page has run out and interest-rate-announcement-"
              "dates-2027-2028 should be fetched instead.", file=sys.stderr)
        print("DEBUG: first 1500 chars of the fetched page text:\n" +
              text[:1500], file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Israel",
        "events": events,
    }
    with open("data-calendar-il.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Israel calendar events.")


if __name__ == "__main__":
    main()
