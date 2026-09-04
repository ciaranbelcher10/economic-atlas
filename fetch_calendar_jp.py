"""Fetch upcoming BoJ policy meeting dates and write data-calendar-jp.json.

Run:  python3 fetch_calendar_jp.py
No API key needed -- public BoJ page.

Source: https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm -- the Bank
of Japan's own official schedule table, published a year or more ahead.
Confirmed live (fetched directly on 2026-09-03): under the "## 2026"
heading there's a real markdown-style table whose first column is the
meeting date in the form "Sept. 17 (Thurs.), 18 (Fri.)" -- a two-day
meeting spanning two dates. Rows for meetings that haven't happened yet
have no link (past meetings link to a PDF statement; future ones are
plain text), which is actually a convenient, incidental way to tell
upcoming meetings apart from historical ones without needing today's
date for comparison.

This script only extracts the MEETING dates (both days), not the Outlook
Report / Summary of Opinions / Minutes follow-up dates in the other
columns -- those are secondary publications, not the actual policy
decision, so out of scope for a "when's the next rate decision" calendar.
The decision itself is announced sometime on day 2, with no fixed time
(BoJ's own convention, unlike the Fed/ECB/BoE) -- flagged as such rather
than guessed.

NOT YET RUN LIVE -- boj.or.jp isn't in this sandbox's network allowlist.
Regex is written against the real table text fetched directly (see
above), not guessed. Treat the first real GitHub Actions run log as the
genuine test.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"

MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# e.g. "Sept. 17 (Thurs.), 18 (Fri.)" -- two dates, same month, first has
# the month name spelled out, second is just a day number.
MEETING_RE = re.compile(
    r"([A-Za-z]{3,4})\.?\s+(\d{1,2})\s*\([A-Za-z]+\.?\)\s*,\s*(\d{1,2})\s*\([A-Za-z]+\.?\)",
)


def parse_year_section(text: str, year: int) -> list[dict]:
    events = []
    for m in MEETING_RE.finditer(text):
        month_str, day1, day2 = m.group(1)[:3].lower(), int(m.group(2)), int(m.group(3))
        month = MONTH_ABBR.get(month_str)
        if not month:
            continue
        try:
            d1 = datetime(year, month, day1).date()
            d2 = datetime(year, month, day2).date()
        except ValueError:
            continue
        events.append({"start": d1.isoformat(), "end": d2.isoformat()})
    return events


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching BoJ schedule: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()
    current_year = today.year

    # Isolate roughly the section for the current year's table, so a
    # stray date-like string elsewhere on the page (there are many links
    # to PDFs with dates in their filenames) doesn't get picked up. Not
    # bulletproof -- worth a manual sanity check against the live page
    # on the first real run.
    year_marker = f"## {current_year}" if f"## {current_year}" in text else str(current_year)
    next_marker = str(current_year + 1)
    start_idx = text.find(year_marker)
    end_idx = text.find(next_marker, start_idx + 1) if start_idx != -1 else -1
    section = text[start_idx:end_idx] if start_idx != -1 and end_idx != -1 else text

    meetings = parse_year_section(section, current_year)
    events = []
    for meeting in meetings:
        if meeting["end"] < today.isoformat():
            continue  # already happened
        events.append({
            "date": meeting["start"],
            "end_date": meeting["end"],
            "country": "Japan",
            "concept": "rate_decision",
            "name": "BoJ Monetary Policy Meeting",
            "source": "boj.or.jp/en/mopo/mpmsche_minu",
            # BoJ deliberately doesn't fix an announcement time (unlike
            # the Fed/ECB/BoE) -- real convention, not a gap in parsing.
            "time": "No fixed time; decision expected on day 2",
        })

    if not events:
        print("WARNING: parsed zero upcoming BoJ meetings -- check the page's "
              "table structure against a fresh fetch before assuming the "
              "source is broken.", file=sys.stderr)
        print("DEBUG: first 1500 chars of the section this script searched:\n" +
              section[:1500], file=sys.stderr)

    events.sort(key=lambda e: e["date"])
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Japan",
        "events": events,
    }
    with open("data-calendar-jp.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Japan calendar events.")


if __name__ == "__main__":
    main()
