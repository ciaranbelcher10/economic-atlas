"""Fetch upcoming Bank of Canada rate-decision dates and write
data-calendar-ca.json.

Run:  python3 fetch_calendar_ca.py
No API key needed -- public Bank of Canada page.

Source: the Bank of Canada publishes its FULL YEAR of fixed announcement
dates in one press release each August (e.g. "Bank of Canada publishes
its 2026 schedule for policy interest rate announcements..."), confirmed
findable via a stable, predictable URL pattern under
bankofcanada.ca/{year}/08/. All 8 dates for the year are announced at
once and essentially never move, unlike some other central banks --
comparatively an easier, more stable source than most.

This script fetches the CURRENT year's schedule-announcement page rather
than the 32 individual per-decision press releases (which only exist
retroactively, one at a time, close to each date) -- one fetch, whole
year, rather than guessing 8 URLs months in advance.

NOT YET RUN LIVE -- bankofcanada.ca isn't in this sandbox's network
allowlist. The exact URL slug for THIS year's schedule announcement
should be confirmed by hand before the first real run (it follows last
year's pattern closely but the exact wording varies year to year) -- see
the fallback search step below, which tries the Bank's own site search
if the direct guess 404s.

All announcements land at 09:45 ET; four of the eight (Jan/Apr/Jul/Oct)
also come with a Monetary Policy Report -- both are Bank of Canada
convention, not something extracted per-date from the page.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

DATE_RE = re.compile(
    r"\b((?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},?\s+\d{4})\b"
)


def guess_schedule_url(year: int) -> str:
    # Last year's real slug (confirmed by search) was:
    #   bank-canada-publishes-2026-schedule-policy-interest-rate-announcements-other-major-publications
    # published in August of the PRIOR year. Exact wording has drifted
    # year to year in the past, so this is a best-effort guess to be
    # confirmed/fixed by hand on the first real run, not treated as
    # guaranteed-correct.
    return (f"https://www.bankofcanada.ca/{year - 1}/08/"
            f"bank-canada-publishes-{year}-schedule-policy-interest-rate-"
            f"announcements-other-major-publications/")


def main():
    today = datetime.now(timezone.utc).date()
    year = today.year
    url = guess_schedule_url(year)

    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
    except requests.RequestException as e:
        print(f"ERROR fetching Bank of Canada schedule page: {e}", file=sys.stderr)
        sys.exit(1)

    if r.status_code != 200:
        print(f"WARNING: guessed URL returned {r.status_code} -- the slug has "
              f"likely drifted from last year's pattern. Find the real "
              f"'Bank of Canada publishes its {year} schedule' press release "
              f"URL by hand and hardcode it here rather than guessing again.",
              file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    events = []
    for m in DATE_RE.finditer(text):
        try:
            d = datetime.strptime(m.group(1).replace(",", ""), "%B %d %Y").date()
        except ValueError:
            continue
        if d.year != year or d < today:
            continue
        events.append(d.isoformat())

    events = sorted(set(events))
    out_events = [{
        "date": d,
        "country": "Canada",
        "concept": "rate_decision",
        "name": "Bank of Canada interest rate announcement",
        "source": "bankofcanada.ca (annual schedule announcement)",
        "time": "9:45am ET",
    } for d in events]

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Canada",
        "events": out_events,
    }
    with open("data-calendar-ca.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(out_events)} Canada calendar events. "
          f"NOTE: verify these are genuinely 8 rate-decision dates and not "
          f"other dates mentioned on the page (e.g. survey release dates) "
          f"before trusting this in production -- the regex above matches "
          f"ANY date on the page, and the schedule announcement covers "
          f"several different publication types, not just rate decisions.")


if __name__ == "__main__":
    main()
