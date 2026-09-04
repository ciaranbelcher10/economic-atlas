"""Fetch upcoming Bank Indonesia (BI-Rate) decision dates and write
data-calendar-id.json.

Run:  python3 fetch_calendar_id.py
No API key needed -- public bi.go.id page.

Source: https://www.bi.go.id/en/publikasi/kalender/default.aspx --
confirmed live tonight, and genuinely one of the best tables found
across three research sessions: a clean "BOARD OF GOVERNOR MEETING 2026"
table with all 12 months, each a two-day Tuesday-Wednesday meeting, e.g.
"Tuesday-Wednesday, 22-23 September 2026". The decision itself is
announced on the second day (the convention used consistently across
every two-day central bank meeting on this calendar).

Two footnote markers worth preserving if this table is read again by a
human, though not needed for the decision date itself: "*" marks a
meeting with Quarterly Coverage (i.e. also covers the quarterly
Monetary Policy Report) and "**" marks Quarterly + Annual Coverage.
Neither changes which day the decision falls on.

BI does not publish an exact announcement time in advance for the
BI-Rate decision itself (confirmed: the table only gives dates, not
times, and BI's own press releases about past decisions don't cite a
fixed daily announcement time the way the Fed's 2:00pm ET or the BoE's
noon are fixed) -- left blank rather than guessed.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.bi.go.id/en/publikasi/kalender/default.aspx"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

# e.g. "22-23 September 2026" or "Tuesday-Wednesday, 22-23 September
# 2026" -- confirmed against the real fetched table. The second day
# number is the decision day.
MEETING_RE = re.compile(
    rf"(\d{{1,2}})\s*-\s*(\d{{1,2}})\s+({MONTH_RE})\s+(\d{{4}})", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Bank Indonesia calendar: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    # Restrict to the "BOARD OF GOVERNOR MEETING" table specifically --
    # the same page also lists an Advance Release Calendar and Open
    # Market Operation auction schedule further down, which have their
    # own date-range-like text that isn't a rate decision.
    start = text.upper().find("BOARD OF GOVERNOR MEETING")
    end = text.upper().find("HOLIDAYS AND COLLECTIVE LEAVES", start)
    section = text[start:end] if start != -1 and end != -1 else text

    events = []
    seen = set()
    for m in MEETING_RE.finditer(section):
        day2, month_name, year = m.group(2), m.group(3).lower(), int(m.group(4))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, int(day2)).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append({
            "date": d.isoformat(),
            "country": "Indonesia",
            "concept": "rate_decision",
            "name": "Bank Indonesia BI-Rate decision",
            "source": "bi.go.id/en/publikasi/kalender (official Board of Governors Meeting schedule)",
            "time": None,
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming meetings -- check the page "
              "structure by hand.", file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Indonesia",
        "events": events,
    }
    with open("data-calendar-id.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Indonesia calendar events.")


if __name__ == "__main__":
    main()
