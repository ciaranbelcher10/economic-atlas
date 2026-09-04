"""Fetch upcoming Bank Al-Maghrib board meeting dates and write
data-calendar-ma.json.

Run:  python3 fetch_calendar_ma.py
No API key needed -- public bkam.ma page.

Source: bkam.ma's own press-releases listing includes board meeting
announcements with real dates months ahead, confirmed live tonight --
e.g. "Bank Al-Maghrib board meeting - September 22, 2026" appearing on
their own homepage. BAM meets quarterly (four board meetings a year),
each announced individually via a press release with the meeting's
title containing the date in plain English, rather than a single
one-page full-year table like several other central banks tonight
(Norges Bank, NBP, Chile). That makes this a slightly different
scraping shape: watch the press-releases feed for meeting announcements
rather than reading one calendar page.

BAM does not publish the exact time of the announcement in advance
(confirmed: none of the individual meeting write-ups found tonight
state a time) -- left blank rather than guessed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.bkam.ma/en"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

# e.g. "Bank Al-Maghrib board meeting - September 22, 2026" -- confirmed
# against the real homepage text fetched tonight.
MEETING_RE = re.compile(
    rf"Bank Al-Maghrib board meeting\s*-\s*({MONTH_RE})\s+(\d{{1,2}}),\s+(\d{{4}})", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Bank Al-Maghrib page: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    seen = set()
    for m in MEETING_RE.finditer(text):
        month_name, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append({
            "date": d.isoformat(),
            "country": "Morocco",
            "concept": "rate_decision",
            "name": "Bank Al-Maghrib board meeting",
            "source": "bkam.ma (board meeting announcement)",
            "time": None,
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming board meetings -- BAM only "
              "seems to announce these one meeting at a time (not a "
              "full-year table), so this may just mean the NEXT meeting "
              "hasn't been announced yet, not that the page is broken. "
              "Check the page by eye before assuming a real failure.",
              file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Morocco",
        "events": events,
    }
    with open("data-calendar-ma.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Morocco calendar events.")


if __name__ == "__main__":
    main()
