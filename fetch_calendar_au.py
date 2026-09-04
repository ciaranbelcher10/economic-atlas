"""Fetch upcoming RBA cash rate decision dates and write
data-calendar-au.json.

Run:  python3 fetch_calendar_au.py
No API key needed -- no live fetch at all, see below.

CHANGED FROM A LIVE SCRAPE TO A HARDCODED SCHEDULE, deliberately, after
confirming via a real workflow run that rba.gov.au's decisions page is
genuinely JavaScript-rendered -- the debug output from that run showed
the raw HTML literally saying "It appears JavaScript is currently
blocked... This website requires JavaScript for some content and
functionality." No regex fix can find data that was never in the HTML
to begin with. Checked for a public RBA data API as an alternative;
found several third-party ones covering historical rate series, but
nothing exposing the future meeting schedule specifically.

The right long-term fix is a headless browser (Playwright) in the
workflow, which is a bigger, separate change not made here. In the
meantime: the RBA publishes its full year of meeting dates in one media
release each year (like Bank of Canada, unlike the more volatile NBP or
CBRT), and that release is easy to find and about as stable as a
real-world schedule gets. Confirmed directly from RBA's own official
2026 media release:
https://www.rba.gov.au/media-releases/2025/mr-25-02.html
("Media Release: 2026 Monetary Policy Board Meeting Dates").

Same trade-off as fetch_calendar_br.py's Copom dates and
fetch_calendar_us.py's FOMC dates: a static list that needs manual
updating once a year, rather than a dynamic fetch that's currently
broken and can't easily be un-broken.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone

# Confirmed directly from RBA's own official 2026 media release
# (see module docstring for URL). Each meeting is two days; the
# decision is announced 2:30pm AEST/AEDT on the second day.
RBA_MEETINGS_2026 = [
    (date(2026, 2, 2), date(2026, 2, 3)),
    (date(2026, 3, 16), date(2026, 3, 17)),
    (date(2026, 5, 4), date(2026, 5, 5)),
    (date(2026, 6, 15), date(2026, 6, 16)),
    (date(2026, 8, 10), date(2026, 8, 11)),
    (date(2026, 9, 28), date(2026, 9, 29)),
    (date(2026, 11, 2), date(2026, 11, 3)),
    (date(2026, 12, 7), date(2026, 12, 8)),
]


def main():
    today = datetime.now(timezone.utc).date()
    events = []
    for _, decision_day in RBA_MEETINGS_2026:
        if decision_day < today:
            continue
        events.append({
            "date": decision_day.isoformat(),
            "country": "Australia",
            "concept": "rate_decision",
            "name": "RBA cash rate decision",
            "source": "rba.gov.au/media-releases/2025/mr-25-02.html (official 2026 schedule)",
            "time": "2:30pm AEST/AEDT",
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Australia",
        "events": events,
    }
    with open("data-calendar-au.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Australia calendar events (hardcoded schedule).")


if __name__ == "__main__":
    main()
