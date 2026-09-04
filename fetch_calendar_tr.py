"""Fetch upcoming CBRT (Turkey) Monetary Policy Committee decision dates
and write data-calendar-tr.json.

Run:  python3 fetch_calendar_tr.py
No API key needed -- no live fetch at all, see below.

CHANGED FROM A LIVE SCRAPE TO A HARDCODED SCHEDULE, deliberately. The
real primary page (tcmb.gov.tr/.../PPK/2026) was confirmed to exist and
load in a live workflow run, but the schedule table wasn't found within
what a plain requests.get() sees -- possibly JS-rendered like RBA,
possibly just further down the page than a simple regex reached; not
fully diagnosed. Rather than keep guessing at that page's structure,
the full 2026 schedule is hardcoded here instead, cross-confirmed
across SIX independent Turkish financial news outlets (Haberturk, CNN
Turk Finans, Bloomberg HT, QNB Invest, Sabah, Ahaber) all reporting the
identical eight dates -- about as solid as secondary corroboration
gets, and TCMB itself confirmed no August 2026 meeting was held,
matching the gap in this list.

All eight decisions are announced at 14:00 (2:00pm) Turkey time on the
meeting day itself -- confirmed as TCMB's standing convention across
every source checked.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

# Cross-confirmed across six independent Turkish financial news sources
# (see module docstring) -- no single meeting per month; TCMB skipped
# August 2026 entirely.
CBRT_MEETINGS_2026 = [
    date(2026, 1, 22),
    date(2026, 3, 12),
    date(2026, 4, 22),
    date(2026, 6, 11),
    date(2026, 7, 23),
    date(2026, 9, 10),
    date(2026, 10, 22),
    date(2026, 12, 10),
]


def main():
    today = datetime.now(timezone.utc).date()
    events = []
    for meeting_day in CBRT_MEETINGS_2026:
        if meeting_day < today:
            continue
        events.append({
            "date": meeting_day.isoformat(),
            "country": "Turkey",
            "concept": "rate_decision",
            "name": "CBRT Monetary Policy Committee decision",
            "source": "tcmb.gov.tr (2026 PPK schedule, hardcoded -- cross-confirmed via 6 independent news sources, see script docstring)",
            "time": "2:00pm TRT",
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Turkey",
        "events": events,
    }
    with open("data-calendar-tr.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Turkey calendar events (hardcoded schedule).")


if __name__ == "__main__":
    main()
