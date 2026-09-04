"""Fetch upcoming Central Bank of Chile monetary policy meeting dates and
write data-calendar-cl.json.

Run:  python3 fetch_calendar_cl.py
No API key needed -- public bcentral.cl page.

Source: https://www.bcentral.cl/en/news-and-publications/press/monetary-and-financial-policy-calendar
-- confirmed live tonight, and genuinely one of the cleaner pages found
across three research sessions: an English-language page with a plain
bulleted list under "Monetary Policy Meetings (MPM) 2026", e.g.:

  - January 26 and 27
  - March 24
  - April 27 and 28
  - June 16
  - July 27 and 28
  - September 8
  - October 26 and 27
  - December 15

Some meetings are single-day, others span two days ("26 and 27") --
where a meeting spans two days, the SECOND day is the decision day, by
the same convention used for the Fed/ECB/BoE/BoJ two-day meetings
elsewhere on this calendar. Confirmed the list doesn't include a year in
each bullet (the year lives only in the section heading "...2026"), so
this script takes the page's own stated year rather than assuming
today's year, which matters for scripts still working in January when
last year's list might still be cached somewhere.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.bcentral.cl/en/news-and-publications/press/monetary-and-financial-policy-calendar"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

YEAR_HEADING_RE = re.compile(r"Monetary Policy Meetings \(MPM\)\s+(\d{4})", re.I)
# e.g. "September 8" or "April 27 and 28" -- the second number (if
# present) is the actual decision day.
MEETING_RE = re.compile(
    rf"({MONTH_RE})\s+(\d{{1,2}})(?:\s+and\s+(\d{{1,2}}))?", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Central Bank of Chile calendar: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)

    year_match = YEAR_HEADING_RE.search(text)
    if not year_match:
        print("ERROR: could not find the 'Monetary Policy Meetings (MPM) YYYY' "
              "heading to anchor the year -- page structure may have changed.",
              file=sys.stderr)
        sys.exit(1)
    year = int(year_match.group(1))

    # Only scan the MPM section itself, not the MPM Minutes or Financial
    # Policy sections further down the same page, which have their own
    # month/day mentions that aren't rate-decision dates.
    section_start = year_match.start()
    section_end = text.find("Monetary Policy Reports", section_start)
    section = text[section_start:section_end] if section_end != -1 else text[section_start:section_start + 2000]

    today = datetime.now(timezone.utc).date()
    events = []
    for m in MEETING_RE.finditer(section):
        month_name = m.group(1).lower()
        day = int(m.group(3)) if m.group(3) else int(m.group(2))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today:
            continue
        events.append({
            "date": d.isoformat(),
            "country": "Chile",
            "concept": "rate_decision",
            "name": "Central Bank of Chile monetary policy meeting",
            "source": "bcentral.cl/en/news-and-publications/press/monetary-and-financial-policy-calendar",
            "time": None,
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming meetings -- check the page "
              "structure by hand.", file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Chile",
        "events": events,
    }
    with open("data-calendar-cl.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Chile calendar events.")


if __name__ == "__main__":
    main()
