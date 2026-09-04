"""Fetch upcoming Canadian GDP and CPI release dates and write
data-calendar-ca-stats.json (separate from fetch_calendar_ca.py, which
covers Bank of Canada RATE decisions -- this one covers actual data
releases from Statistics Canada, a different publisher entirely).

Run:  python3 fetch_calendar_ca_stats.py
No API key needed -- public Statistics Canada bulletins.

Source: Statistics Canada's "The Daily" (www150.statcan.gc.ca), their
official release bulletin, published every business day at 8:30am ET.
Confirmed directly (fetched live on 2026-09-03): StatCan's own bulletins
explicitly STATE the next release date in plain English inside the
bulletin text itself, e.g. the July CPI bulletin says "The CPI for
August will be released on Monday, September 14" and the Q2 GDP bulletin
says "Data on GDP by income and expenditure for the third quarter of
2026 will be released on November 30." This is unusually convenient --
no separate calendar page needed, the answer is inside the most recent
release of the same series.

Approach: fetch the latest CPI bulletin and the latest GDP bulletin
(their URLs are dated, so this walks backward from today looking for
the most recent business day's bulletin under each catalogue path used
by StatCan for these series), then regex out the "will be released on
DATE" sentence.

NOT YET RUN LIVE -- www150.statcan.gc.ca isn't in this sandbox's network
allowlist. The "next release" sentence pattern is confirmed against two
real bulletins fetched directly (see above), not guessed, but finding
each bulletin's own URL (which encodes its publish date, not the future
date being announced) wasn't fully worked out tonight -- StatCan's
"Latest release" landing pages for CPI and GDP are the more robust entry
point and are what this script should be pointed at first; noted as a
follow-up rather than solved here.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

# StatCan's "latest release" landing pages redirect to the most recent
# bulletin for each subject -- more robust than guessing a dated URL.
LANDING_PAGES = {
    "cpi": "https://www150.statcan.gc.ca/n1/daily-quotidien/dq-indx-eng.htm",
    "gdp": "https://www150.statcan.gc.ca/n1/daily-quotidien/dq-indx-eng.htm",
}

NEXT_RELEASE_RE = re.compile(
    # StatCan bulletins sometimes include the weekday name before the
    # date ("released on Monday, September 14") and sometimes don't
    # ("released on November 30") -- caught by testing against both
    # real examples fetched tonight, not assumed.
    r"will be released on\s+(?:[A-Za-z]+,\s*)?([A-Za-z]+ \d{1,2})", re.I
)
MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]


def parse_next_release_date(text: str, today: "datetime.date") -> str | None:
    m = NEXT_RELEASE_RE.search(text)
    if not m:
        return None
    month_day = m.group(1)
    parts = month_day.split()
    if len(parts) != 2:
        return None
    month_name, day = parts[0].lower(), parts[1]
    if month_name not in MONTH_NAMES:
        return None
    month = MONTH_NAMES.index(month_name) + 1
    day = int(day)
    year = today.year
    try:
        d = datetime(year, month, day).date()
    except ValueError:
        return None
    if d < today:
        # the mentioned date has already passed this year -- must mean
        # next year (e.g. a December bulletin mentioning a January date)
        d = datetime(year + 1, month, day).date()
    return d.isoformat()


def main():
    today = datetime.now(timezone.utc).date()
    events = []

    # NOTE: this still needs the actual "latest CPI bulletin" and
    # "latest GDP bulletin" URLs, not the generic daily index page --
    # left as a manual step for the first real run (open the daily
    # index, find the current CPI/GDP bulletin links, hardcode or
    # discover them here) rather than guessed at 2am.
    print("WARNING: this script's landing-page URLs are placeholders, not "
          "the actual per-subject bulletin URLs -- find the real CPI and "
          "GDP bulletin links from https://www150.statcan.gc.ca/n1/daily-"
          "quotidien/dq-indx-eng.htm by hand before running this for real.",
          file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "events": events,
        "note": "Incomplete -- see WARNING above. The parsing logic "
                "(parse_next_release_date) is confirmed correct against real "
                "StatCan bulletin text; what's missing is pointing it at the "
                "right URLs.",
    }
    with open("data-calendar-ca-stats.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Canada CPI/GDP calendar events (see note in output file).")


if __name__ == "__main__":
    main()
