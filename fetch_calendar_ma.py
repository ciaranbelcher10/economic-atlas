"""Fetch upcoming Bank Al-Maghrib board meeting dates and write
data-calendar-ma.json.

Run:  python3 fetch_calendar_ma.py

DELIBERATELY WRITES ZERO EVENTS. Previously hardcoded three of the four
2026 board meeting dates (confirmed genuine at the time: bkam.ma returns
"403 Client Error: Forbidden" even with a realistic browser User-Agent,
a proper WAF/bot-challenge that no header-tweaking from a plain
requests.get() gets past). That hardcoded list has been removed by
explicit policy decision: no calendar data may be hand-typed, even from
an official source, only ever fetched live. Morocco is tracked as a
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
        "country": "Morocco",
        "events": [],
    }
    with open("data-calendar-ma.json", "w") as f:
        json.dump(out, f, indent=2)
    print("Wrote 0 Morocco calendar events (hardcoding removed by policy -- "
          "needs a real live fetch, e.g. a headless browser, not yet built).")


if __name__ == "__main__":
    main()
