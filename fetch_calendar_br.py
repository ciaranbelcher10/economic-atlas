"""Fetch upcoming Copom (Brazil) rate decision dates and write
data-calendar-br.json.

Run:  python3 fetch_calendar_br.py
No API key needed -- public BCB page.

Source: the Central Bank of Brazil (Banco Central do Brasil) publishes
its full year of Copom meeting dates in one official announcement each
year, similar in spirit to how the Bank of Canada does it. The 2026
dates (confirmed via multiple Brazilian financial news outlets tonight,
all citing the same BCB announcement): 27 to 28 January, 17 to 18 March,
28 to 29 April, 16 to 17 June, 4 to 5 August, 15 to 16 September, 3 to 4
November, 8 to 9 December. Each meeting spans two days (Tuesday and
Wednesday); the decision is announced the evening of the second day,
typically between 6:30pm and 7:30pm Brasilia time -- not a fixed minute
the way the Fed/ECB/BoE are, so left as an approximate window rather
than a specific time.

Ideally this script would fetch the BCB's own calendar page directly
rather than relying on the dates as reported by news outlets -- that
page wasn't individually located and fetched tonight (time ran out
after confirming the dates via several independent Brazilian financial
sources, which is reasonable corroboration but not the same as reading
it from bcb.gov.br itself). Flagged as a follow-up: find and fetch BCB's
own Copom calendar page, then extract from there instead of hardcoding.

NOT YET RUN LIVE. The dates below are hardcoded from research rather
than scraped, since the primary source page wasn't pinned down -- this
is a genuine gap, not an oversight, and should be the first thing fixed
before relying on this script.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone

# Hardcoded from the 2026 Copom calendar as reported by BCB and
# corroborated by multiple Brazilian financial outlets (CNN Brasil,
# InfoMoney, C6 Bank) tonight -- NOT scraped from bcb.gov.br directly.
# Each tuple is (meeting start, decision day / meeting end).
COPOM_2026_MEETINGS = [
    (date(2026, 1, 27), date(2026, 1, 28)),
    (date(2026, 3, 17), date(2026, 3, 18)),
    (date(2026, 4, 28), date(2026, 4, 29)),
    (date(2026, 6, 16), date(2026, 6, 17)),
    (date(2026, 8, 4), date(2026, 8, 5)),
    (date(2026, 9, 15), date(2026, 9, 16)),
    (date(2026, 11, 3), date(2026, 11, 4)),
    (date(2026, 12, 8), date(2026, 12, 9)),
]


def main():
    today = datetime.now(timezone.utc).date()
    print("WARNING: dates below are hardcoded from cross-referenced news "
          "reporting, not scraped from bcb.gov.br directly -- find BCB's "
          "own Copom calendar page and point this script at it before "
          "trusting this for more than one year.", file=sys.stderr)

    events = []
    for _, decision_day in COPOM_2026_MEETINGS:
        if decision_day < today:
            continue
        events.append({
            "date": decision_day.isoformat(),
            "country": "Brazil",
            "concept": "rate_decision",
            "name": "Copom Selic rate decision",
            "source": "bcb.gov.br (2026 Copom calendar, corroborated via news reporting, not yet scraped directly)",
            "time": "Evening, Brasilia time, typically 6:30pm to 7:30pm",
        })

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Brazil",
        "events": events,
    }
    with open("data-calendar-br.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Brazil calendar events.")


if __name__ == "__main__":
    main()
