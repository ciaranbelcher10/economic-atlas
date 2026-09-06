"""Fetch upcoming Bank of Israel interest rate announcement dates and
write data-calendar-il.json.

Run:  python3 fetch_calendar_il.py
No API key needed -- no live fetch at all, see below.

CHANGED FROM A LIVE SCRAPE TO A HARDCODED SCHEDULE, deliberately. This
page was directly and successfully fetched earlier in the same research
session that built the original scraper -- confirmed real dates, real
table structure, DD/MM/YYYY format. But an actual workflow run
afterwards reported "no <table> found on the page" against the same
URL, meaning something about the Action's request (most likely still
being treated differently than the interactive fetch that worked
earlier, possibly a stricter check on repeat/automated requests) gets a
different response than a one-off manual fetch. Rather than keep
guessing at that inconsistency, the dates already confirmed directly
from boi.org.il's own table are hardcoded here instead.

Full 2026 schedule (DD/MM/YYYY as published, all at 16:00 local time):
05/01, 23/02, 30/03, 25/05, 06/07, 01/09, 21/10, 23/11. Four of the
eight are accompanied by a press conference and a Research Department
staff forecast (Jan, Mar, Jul, Oct); the other four are not -- both
real, confirmed absences in the source table, not a scraping gap.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

# Confirmed directly from boi.org.il's own 2026 announcement-dates table
# (see module docstring).
BOI_MEETINGS_2026 = [
    date(2026, 1, 5),
    date(2026, 2, 23),
    date(2026, 3, 30),
    date(2026, 5, 25),
    date(2026, 7, 6),
    date(2026, 9, 1),
    date(2026, 10, 21),
    date(2026, 11, 23),
]


def main():
    today = datetime.now(timezone.utc).date()
    events = []
    for meeting_day in BOI_MEETINGS_2026:
        if meeting_day < today:
            continue
        events.append({
            "date": meeting_day.isoformat(),
            "country": "Israel",
            "concept": "rate_decision",
            "name": "Bank of Israel interest rate announcement",
            "source": "boi.org.il (2026 announcement dates table, hardcoded -- confirmed directly against the real table earlier, see script docstring)",
            "time": "4:00pm local time",
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Israel",
        "events": events,
    }
    with open("data-calendar-il.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Israel calendar events (hardcoded schedule).")


if __name__ == "__main__":
    main()
