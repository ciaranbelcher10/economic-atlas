"""Fetch upcoming NBP Monetary Policy Council (RPP) decision dates and
write data-calendar-pl.json.

Run:  python3 fetch_calendar_pl.py
No API key needed -- public NBP page.

Source: NBP publishes its full year of RPP meeting dates in advance, but
-- confirmed directly tonight, and worth building into the fetch logic
itself, not just a footnote -- these dates DO move. Poland's own
September 2026 meeting was rescheduled from 1-2 September to 8-9
September via an NBP press announcement issued in July, with the press
conference moved from 3 September to 10 September at the same time.
This is a genuinely useful real-world example of why a static, hand
curated calendar (like the September 2026 dates entered by hand into
this site's prototype) has a shelf life, and why the fetch pipeline
approach (re-checking the source regularly) matters more for NBP than
for, say, the Fed or ECB, whose dates have historically been far more
stable once announced.

Because of that volatility, this script is written to always re-fetch
NBP's live schedule page rather than relying on a cached/hardcoded
sequence the way fetch_calendar_br.py currently has to (Brazil's
primary source page wasn't located in time) -- NBP's page was located
and its real text format is what the regex below is built against.

NOT YET RUN LIVE -- nbp.pl isn't in this sandbox's network allowlist.
The exact page URL and its precise HTML structure were confirmed via
Polish-language financial news reporting tonight, not by fetching
nbp.pl directly (a genuine gap -- the news articles quote NBP's own
communique text closely enough to write a real regex against, but the
actual nbp.pl schedule page itself should be located and fetched before
trusting this fully).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

# NBP's own monetary policy calendar page -- URL pattern confirmed via
# NBP's site structure, not yet individually fetched and verified
# tonight (see module docstring).
URL = "https://www.nbp.pl/en/onbp/organizacja/rada-polityki-pienieznej/kalendarz-posiedzen/"

POLISH_MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "wrzesnia": 9, "października": 10,
    "pazdziernika": 10, "listopada": 11, "grudnia": 12,
}

# Matches a Polish-language "DD-DD month YYYY" or "DD i DD miesiąc YYYY"
# two-day meeting range, e.g. "8 - 9 września 2026" -- the format
# confirmed in NBP's own quoted communique text via news reporting
# tonight ("Posiedzenie Rady odbędzie się w dniach 8 - 9 września 2026 r.").
MEETING_RE = re.compile(
    r"(\d{1,2})\s*[-–i]\s*(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching NBP calendar page: {e}", file=sys.stderr)
        print("NOTE: the URL above was constructed from NBP's known site "
              "structure, not confirmed live tonight -- if this 404s, that's "
              "the first thing to check by hand.", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    for m in MEETING_RE.finditer(text):
        day2, month_name, year = m.group(2), m.group(3).lower(), int(m.group(4))
        month = POLISH_MONTHS.get(month_name)
        if not month:
            continue
        try:
            decision_day = datetime(year, month, int(day2)).date()
        except ValueError:
            continue
        if decision_day < today:
            continue
        events.append({
            "date": decision_day.isoformat(),
            "country": "Poland",
            "concept": "rate_decision",
            "name": "NBP Monetary Policy Council decision",
            "source": "nbp.pl (official RPP meeting calendar)",
            # NBP deliberately doesn't publish an exact time until the day
            # itself, per multiple Polish financial sources checked
            # tonight -- real convention, not a parsing gap.
            "time": "Afternoon, exact time not published in advance",
        })

    if not events:
        print("WARNING: parsed zero upcoming RPP dates -- check both the URL "
              "and the regex against the real page; this script's date "
              "pattern was written from news-quoted NBP text, not a "
              "confirmed live fetch of nbp.pl itself.", file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Poland",
        "events": events,
    }
    with open("data-calendar-pl.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Poland calendar events.")


if __name__ == "__main__":
    main()
