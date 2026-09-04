"""Fetch upcoming RBA cash rate decision dates and write
data-calendar-au.json.

Run:  python3 fetch_calendar_au.py
No API key needed -- public RBA page.

Source: https://www.rba.gov.au/monetary-policy/int-rate-decisions/ -- the
RBA's own official decisions page. The RBA holds 8 Board meetings a year,
each over two days, with the decision explained in a media release at
2:30pm AEST on the second day.

This is a lighter-weight source than the US/UK/EZ/JP ones: the RBA page
structure for FUTURE (not yet decided) meeting dates wasn't confirmed in
as much depth as the others tonight, so this script's date-extraction
regex is a reasonable first pass, not verified against the live page's
exact HTML the way the ECB and BoJ ones were. Flagged here rather than
overstated -- check the parsed output against the real page by eye on
the first run before trusting it unattended.

NOT YET RUN LIVE -- rba.gov.au isn't in this sandbox's network allowlist.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.rba.gov.au/monetary-policy/int-rate-decisions/"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

# e.g. "29 September 2026" or "29 September 2026" appearing on the page
# as a heading for that meeting's outcome/media release.
DATE_RE = re.compile(
    rf"(\d{{1,2}})\s+({MONTH_RE})\s+(\d{{4}})", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching RBA page: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    seen = set()
    for m in DATE_RE.finditer(text):
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append(d.isoformat())

    events = sorted(events)[:8]  # cap at the next 8, roughly a year's worth of meetings
    out_events = [{
        "date": d,
        "country": "Australia",
        "concept": "rate_decision",
        "name": "RBA cash rate decision",
        "source": "rba.gov.au/monetary-policy/int-rate-decisions",
        "time": "2:30pm AEST",
    } for d in events]

    if not out_events:
        print("WARNING: parsed zero upcoming RBA dates -- check the page structure "
              "by hand, this parser is a first pass, not verified against the "
              "live page.", file=sys.stderr)
        print("DEBUG: first 1500 chars of the fetched page text:\n" +
              text[:1500], file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Australia",
        "events": out_events,
    }
    with open("data-calendar-au.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(out_events)} Australia calendar events. "
          f"Verify by eye against rba.gov.au before trusting unattended.")


if __name__ == "__main__":
    main()
