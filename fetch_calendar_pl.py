"""Fetch upcoming NBP Monetary Policy Council (RPP) decision dates and
write data-calendar-pl.json.

Run:  python3 fetch_calendar_pl.py
No API key needed -- public NBP page.

Source: NBP publishes its full year of RPP meeting dates in advance,
but these dates genuinely move -- Poland's own September 2026 meeting
was rescheduled from 1-2 September to 8-9 September via an NBP
announcement, and secondary sources disagree with each other about
which date is actually correct even now (some still say 1-2 September,
published well after the reschedule reportedly happened). That
disagreement is itself evidence this needs a live fetch rather than a
hardcoded list -- unlike RBA/Morocco/Turkey/Canada/Israel, which all
got hardcoded after confirming their schedules are genuinely stable
once published, Poland's isn't, so it stays a live scrape.

URL FIXED: the previous version targeted
https://www.nbp.pl/en/onbp/organizacja/rada-polityki-pienieznej/kalendarz-posiedzen/
which appears to be a stale path from an old site structure. Found the
actual current URL via search, cited as the source by multiple Polish
financial sites: nbp.pl/polityka-pieniezna/rada-polityki-pienieznej/
harmonogram-rpp/

REGEX ALSO LOOSENED: the previous version required a 4-digit year
directly after the month name on the same match ("8 - 9 września
2026"), which assumes the year repeats on every row. Real tables from
other central banks (RBA, BoJ) instead put the year once as a heading
above a list of day-month rows -- if NBP's page follows that same
common pattern, requiring an inline year would explain matching
nothing even against the right page. Now matches "DD - DD MonthName"
without requiring a trailing year, and applies the current year
externally instead (same fix that worked for RBA/Chile).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

# Real current URL, found via search (see module docstring) -- not the
# stale one this script originally guessed.
URL = "https://nbp.pl/polityka-pieniezna/rada-polityki-pienieznej/harmonogram-rpp/"

POLISH_MONTHS = {
    "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4, "maja": 5, "czerwca": 6,
    "lipca": 7, "sierpnia": 8, "września": 9, "wrzesnia": 9, "października": 10,
    "pazdziernika": 10, "listopada": 11, "grudnia": 12,
}

# "DD - DD MonthName" -- year no longer required inline (see module
# docstring), applied externally instead.
MEETING_RE = re.compile(
    r"(\d{1,2})\s*[-–i]\s*(\d{1,2})\s+([a-ząćęłńóśźż]+)", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching NBP calendar page: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()
    current_year = today.year

    events = []
    seen = set()
    for m in MEETING_RE.finditer(text):
        day2, month_name = m.group(2), m.group(3).lower()
        month = POLISH_MONTHS.get(month_name)
        if not month:
            continue
        # Only take the FIRST future match (current year if it's still
        # ahead, otherwise next year) -- a real bug caught by testing:
        # trying both year guesses without stopping meant a date like
        # "8-9 września" matched as both a valid 2026 date AND a valid
        # 2027 date (both technically in the future relative to today),
        # producing duplicate entries a year apart for the same table
        # row instead of just the next real occurrence.
        for year_guess in (current_year, current_year + 1):
            try:
                decision_day = datetime(year_guess, month, int(day2)).date()
            except ValueError:
                continue
            if decision_day < today:
                continue
            key = decision_day.isoformat()
            if key in seen:
                break
            seen.add(key)
            events.append({
                "date": decision_day.isoformat(),
                "country": "Poland",
                "concept": "rate_decision",
                "name": "NBP Monetary Policy Council decision",
                "source": "nbp.pl/polityka-pieniezna/rada-polityki-pienieznej/harmonogram-rpp (real current URL)",
                # NBP deliberately doesn't publish an exact time until the day
                # itself, per multiple Polish financial sources checked --
                # real convention, not a parsing gap.
                "time": "Afternoon, exact time not published in advance",
            })
            break

    if not events:
        print("WARNING: parsed zero upcoming RPP dates even against the "
              "corrected URL -- check the regex against the real page by "
              "hand next.", file=sys.stderr)
        print("DEBUG: first 1500 chars of the fetched page text:\n" +
              text[:1500], file=sys.stderr)

    events.sort(key=lambda e: e["date"])
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
