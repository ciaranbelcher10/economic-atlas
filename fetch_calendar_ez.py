"""Fetch upcoming ECB Governing Council rate-decision dates and write
data-calendar-ez.json.

Run:  python3 fetch_calendar_ez.py
No API key needed -- public ECB page.

Source: https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html
-- the ECB's own official Governing Council calendar, published up to a
year ahead. Confirmed live (fetched directly on 2026-09-03): the page
lists entries as DD/MM/YYYY followed by a description line, e.g.

  09/09/2026
  Governing Council of the ECB: monetary policy meeting hosted by the
  Deutsche Bundesbank (Day 1)
  10/09/2026
  Governing Council of the ECB: monetary policy meeting hosted by the
  Deutsche Bundesbank (Day 2), followed by press conference

Only the "(Day 2) ... press conference" entries are real rate-decision
days (Day 1 is a closed-door meeting with no announcement); this script
keeps only those. The decision itself is always announced at 14:15 CET
with the press conference at 14:45 CET -- fixed ECB convention, not
something the page states per-entry, so it's hardcoded here rather than
parsed.

NOT YET RUN LIVE -- ecb.europa.eu isn't in this sandbox's network
allowlist. The parsing regex below is written against the real page
structure fetched directly (see above), not guessed, but hasn't been
executed end-to-end. Treat the first real GitHub Actions run log as the
genuine test.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"

# Matches a DD/MM/YYYY date line followed (possibly a couple of lines
# later once HTML tags are stripped) by a "(Day 2) ... press conference"
# description -- i.e. an actual decision day, not the closed-door Day 1.
ENTRY_RE = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s*"
    r"Governing Council of the ECB:\s*monetary policy meeting[^\n]*"
    r"\(Day 2\)[^\n]*press conference",
    re.I,
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching ECB calendar: {e}", file=sys.stderr)
        sys.exit(1)

    # Strip HTML tags down to plain text so the regex above can match
    # across what were separate table cells/rows.
    text = re.sub(r"<[^>]+>", "\n", r.text)
    text = re.sub(r"\n{2,}", "\n", text)

    today = datetime.now(timezone.utc).date()
    events = []
    for m in ENTRY_RE.finditer(text):
        try:
            d = datetime.strptime(m.group(1), "%d/%m/%Y").date()
        except ValueError:
            continue
        if d < today:
            continue
        events.append({
            "date": d.isoformat(),
            "country": "Eurozone",
            "concept": "rate_decision",
            "name": "ECB Governing Council rate decision",
            "source": "ecb.europa.eu/press/calendars/mgcgc",
            "time": "2:15pm CET (press conference 2:45pm CET)",
        })

    if not events:
        print("WARNING: parsed zero events -- the page's HTML structure may "
              "have changed since this was written; check the regex against "
              "a fresh fetch before assuming the source itself is broken.",
              file=sys.stderr)

    events.sort(key=lambda e: e["date"])
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Eurozone",
        "events": events,
    }
    with open("data-calendar-ez.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Eurozone calendar events.")


if __name__ == "__main__":
    main()
