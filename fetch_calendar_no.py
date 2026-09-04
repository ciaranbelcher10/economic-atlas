"""Fetch upcoming Norges Bank policy rate decision dates and write
data-calendar-no.json.

Run:  python3 fetch_calendar_no.py
No API key needed -- public Norges Bank page.

Source: https://www.norges-bank.no/en/news-events/calendar/?selectedFacets%5BType%5D=145879
-- Norges Bank's own calendar, filtered to policy rate decisions only via
the selectedFacets query param. This is genuinely the cleanest structured
source found across two research sessions on this: each decision gets
its own predictable URL
(.../calendar/policy-rate-decisions/YY-MM-DD/), the list page itself
already gives clean "24 Sep 2026, Thursday 10:00" entries, and it lists
11+ months ahead (confirmed live: results ran from September 2026 all
the way to November 2027).

Because the list page already has everything needed in one fetch, this
script does NOT need to visit each individual decision's own page --
that would be needed only if per-meeting detail (agenda, prior
statement, etc.) were wanted, which isn't the case for a calendar.

NOT YET RUN LIVE -- norges-bank.no isn't in this sandbox's network
allowlist. The date/heading pattern below is written against the real
page fetched directly (see above).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.norges-bank.no/en/news-events/calendar/?selectedFacets%5BType%5D=145879"

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# e.g. "24 Sep 2026" followed later by "Thursday 10:00" -- confirmed
# against the real fetched page, which lists each entry as
# "<Day> <Mon> <Year>\n<Weekday> <HH:MM>".
DATE_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\D{0,20}?(\d{1,2}):(\d{2})", re.S
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Norges Bank calendar: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    seen = set()
    for m in DATE_RE.finditer(text):
        day, month_abbr, year, hh, mm = m.groups()
        month = MONTH_ABBR.get(month_abbr.lower())
        if not month:
            continue
        try:
            d = datetime(int(year), month, int(day)).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append({
            "date": d.isoformat(),
            "country": "Norway",
            "concept": "rate_decision",
            "name": "Norges Bank policy rate decision",
            "source": "norges-bank.no/en/news-events/calendar",
            "time": f"{hh}:{mm} CET/CEST",
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming Norges Bank dates -- check the "
              "page structure by hand.", file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Norway",
        "events": events,
    }
    with open("data-calendar-no.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Norway calendar events.")


if __name__ == "__main__":
    main()
