"""Fetch upcoming Riksbank policy rate decision dates and write
data-calendar-se.json.

Run:  python3 fetch_calendar_se.py
No API key needed -- public Riksbank page.

Source: https://www.riksbank.se/en-gb/press-and-published/calendar/ --
the Riksbank's own official calendar, which (confirmed by direct fetch on
2026-09-03) lists monetary policy decision entries with real future
dates, e.g. "The decision on the level of the policy rate will apply
from 30 September 2026." Each decision is published together with the
Monetary Policy Report at 9:30am, with a press conference following.

Like the RBA script, this one is a reasonable first pass rather than a
fully page-structure-verified parser (the calendar page mixes several
different event types -- Business Survey releases, press conferences,
etc. -- alongside the actual rate decisions, so the filter phrase below
matters more than for the single-purpose ECB/BoJ pages).

NOT YET RUN LIVE -- riksbank.se isn't in this sandbox's network
allowlist.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.riksbank.se/en-gb/press-and-published/calendar/"

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]
MONTH_RE = "|".join(MONTH_NAMES)

# Only match dates that appear near "policy rate" / "monetary policy
# decision" language, not every date on the page (the calendar also
# lists surveys, publications, etc. that aren't rate decisions).
DECISION_CONTEXT_RE = re.compile(
    rf"(?:decision on (?:the level of )?the policy rate|monetary policy decision)"
    rf"[^.]{{0,80}}?(\d{{1,2}})\s+({MONTH_RE})\s+(\d{{4}})",
    re.I,
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Riksbank calendar: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    seen = set()
    for m in DECISION_CONTEXT_RE.finditer(text):
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = MONTH_NAMES.index(month_name) + 1
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append(d.isoformat())

    events = sorted(events)
    out_events = [{
        "date": d,
        "country": "Sweden",
        "concept": "rate_decision",
        "name": "Riksbank policy rate decision",
        "source": "riksbank.se/en-gb/press-and-published/calendar",
        "time": "9:30am CET, published with the Monetary Policy Report",
    } for d in events]

    if not out_events:
        print("WARNING: parsed zero upcoming Riksbank decisions -- check the "
              "page structure by hand, this parser is a first pass.",
              file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Sweden",
        "events": out_events,
    }
    with open("data-calendar-se.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(out_events)} Sweden calendar events. "
          f"Verify by eye against riksbank.se before trusting unattended.")


if __name__ == "__main__":
    main()
