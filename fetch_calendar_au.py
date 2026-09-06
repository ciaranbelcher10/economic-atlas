"""Fetch upcoming RBA cash rate decision dates and write
data-calendar-au.json.

Run:  python3 fetch_calendar_au.py

DELIBERATELY WRITES ZERO EVENTS. Previously hardcoded RBA's official
2026 meeting schedule (confirmed genuine at the time: rba.gov.au's
decisions page is JavaScript-rendered, confirmed via a real workflow run
whose debug output showed the raw HTML literally saying "It appears
JavaScript is currently blocked" -- no regex fix could ever find data
that was never in the HTML). That hardcoded list has been removed by
explicit policy decision: no calendar data may be hand-typed, even from
an official source, only ever fetched live. Australia is tracked as a
"no data yet, investigating" country until a real live fetch exists --
the real fix is a headless browser (Playwright) in the workflow, not
attempted here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone


def main():
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Australia",
        "events": [],
    }
    with open("data-calendar-au.json", "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote 0 Australia calendar events (hardcoding removed by policy -- "
          "needs a real live fetch, e.g. a headless browser, not yet built).")


if __name__ == "__main__":
    main()
