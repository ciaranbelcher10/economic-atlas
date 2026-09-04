"""Fetch upcoming Bank Al-Maghrib board meeting dates and write
data-calendar-ma.json.

Run:  python3 fetch_calendar_ma.py
No API key needed -- no live fetch at all, see below.

CHANGED FROM A LIVE SCRAPE TO A HARDCODED SCHEDULE, deliberately, after
a real workflow run returned "403 Client Error: Forbidden" even after
switching to a realistic browser User-Agent (which fixed the same
problem for Poland's NBP). That means bkam.ma is blocking on more than
just the User-Agent string -- likely a proper WAF/bot-challenge -- and
no amount of header-tweaking from a plain requests.get() is going to
get past that. The real fix would be a headless browser, same as the
RBA case, not attempted here.

Bank Al-Maghrib's board meets quarterly. Three of the four 2026 dates
are confirmed directly from BAM's own press release titles (found via
search, since the site itself can't be fetched directly):
  17 March 2026, 23 June 2026, 22 September 2026
The fourth (Q4) date is NOT YET PUBLISHED as of this writing -- BAM
typically announces each quarter's exact date only shortly before it
happens, unlike the RBA or Fed's full-year-ahead announcements. Rather
than guess a December date from the roughly-quarterly pattern, it's
left out entirely below. This script will need a manual update once
that date is announced (expected sometime in Q4 2026, likely
mid-to-late December based on 2025's pattern) -- flagged here so that
gap doesn't get silently forgotten.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

# Confirmed directly from Bank Al-Maghrib's own press release titles
# (see module docstring). No time is published in advance by BAM for
# any of these -- confirmed absence, not a parsing gap.
BAM_MEETINGS_2026 = [
    date(2026, 3, 17),
    date(2026, 6, 23),
    date(2026, 9, 22),
    # Q4 2026 date not yet published -- see module docstring.
]


def main():
    today = datetime.now(timezone.utc).date()
    events = []
    for meeting_day in BAM_MEETINGS_2026:
        if meeting_day < today:
            continue
        events.append({
            "date": meeting_day.isoformat(),
            "country": "Morocco",
            "concept": "rate_decision",
            "name": "Bank Al-Maghrib board meeting",
            "source": "bkam.ma (individual board meeting press releases, hardcoded -- site blocks automated fetches)",
            "time": None,
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Morocco",
        "events": events,
    }
    with open("data-calendar-ma.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Morocco calendar events (hardcoded schedule, "
          f"Q4 2026 date not yet published, see docstring).")


if __name__ == "__main__":
    main()
