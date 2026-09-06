"""Fetch upcoming Bank of Canada rate decision dates and write
data-calendar-ca.json.

Run:  python3 fetch_calendar_ca.py
No API key needed -- no live fetch at all, see below.

CHANGED FROM A LIVE SCRAPE TO A HARDCODED SCHEDULE, deliberately. A
real workflow run confirmed the guessed schedule-announcement URL
(bankofcanada.ca/2025/08/bank-canada-publishes-2026-schedule-...)
genuinely resolves and contains the right press release (its title was
visible in the debug output), but the date-extraction regex still
found zero matches -- the real dates evidently sit further into the
article body than what a simple flat-text search reliably picks up
alongside all the surrounding WordPress boilerplate. Rather than keep
tuning a regex against a page whose exact structure isn't confirmed,
the full 2026 schedule is hardcoded here, cross-confirmed across SIX
independent sources (Equals Money, Sphera Credit, myperch.io,
CanadaOutlook, nesto.ca, RBC) all reporting the identical eight dates,
plus the Bank of Canada's own individual per-announcement pages (e.g.
bankofcanada.ca/2026/09/interest-rate-announcement-september-2-2026/)
directly confirming the pattern.

All eight announcements land at 09:45 ET; four (January, April, July,
October) are accompanied by the quarterly Monetary Policy Report and a
press conference -- noted but not treated as a separate event here.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

# Cross-confirmed across six independent sources plus individual BoC
# announcement pages (see module docstring).
BOC_MEETINGS_2026 = [
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 10),
    date(2026, 7, 15),
    date(2026, 9, 2),
    date(2026, 10, 28),
    date(2026, 12, 9),
]


def main():
    today = datetime.now(timezone.utc).date()
    events = []
    for meeting_day in BOC_MEETINGS_2026:
        if meeting_day < today:
            continue
        events.append({
            "date": meeting_day.isoformat(),
            "country": "Canada",
            "concept": "rate_decision",
            "name": "Bank of Canada interest rate announcement",
            "source": "bankofcanada.ca (2026 schedule, hardcoded -- cross-confirmed via 6 independent sources, see script docstring)",
            "time": "9:45am ET",
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "events": events,
    }
    with open("data-calendar-ca.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Canada calendar events (hardcoded schedule).")


if __name__ == "__main__":
    main()
