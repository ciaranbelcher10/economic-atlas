"""Fetch upcoming UK release dates and write data-calendar-uk.json.

Run:  python3 fetch_calendar_uk.py
No API key needed -- these are public ONS bulletin pages.

ONS's old release-calendar data endpoint (/releasecalendar/data) was
retired in 2024 in favour of a search API (api.beta.ons.gov.uk/v1/search)
that, as of this writing, doesn't cleanly expose a "future release date"
field per item without more investigation than fit in one overnight
session -- flagged as a follow-up, not solved here.

What DOES work, confirmed directly (fetched live, not guessed): every ONS
bulletin has a predictable URL of the form
  https://www.ons.gov.uk/releases/{slug}{month}{year}
and the NEXT release's page already exists and is publicly fetchable
MONTHS before publication, showing "Release date: DD Month YYYY H:MMam"
and "Important information: This release is not yet published" --
e.g. https://www.ons.gov.uk/releases/gdpmonthlyestimateukseptember2026
returned a real "Release date: 12 November 2026 7:00am" when fetched on
2026-09-03, for a bulletin that won't itself be published until then.

This script generates the next N months of slugs for each tracked
bulletin and fetches each one, parsing the "Release date:" line. A slug
that 404s just means that future bulletin's page hasn't been created yet
-- not an error, so those are skipped rather than failing the run.

NOT YET RUN LIVE -- ons.gov.uk isn't in this sandbox's network
allowlist. Written and reasoned through against two real fetches of
actual ONS pages (see the URLs above), not guessed. Treat the first real
GitHub Actions run log as the genuine test.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

MONTH_NAMES = ["january", "february", "march", "april", "may", "june",
               "july", "august", "september", "october", "november", "december"]

# key: (slug prefix, human name, source note). The slug is
# {prefix}{month}{year}, e.g. "gdpmonthlyestimateuk" + "september2026".
TRACKED_BULLETINS = {
    "gdp_monthly": ("gdpmonthlyestimateuk", "GDP monthly estimate"),
    "cpi": ("consumerpriceinflation", "Consumer price inflation"),
    "labour_market": ("labourmarketoverviewuk", "Labour market overview"),
}

RELEASE_DATE_RE = re.compile(
    r"Release date:\s*(\d{1,2} [A-Za-z]+ \d{4})\s*([\d:]+(?:am|pm))?", re.I)


def month_year_slugs() -> list[str]:
    """Real bug found by testing this script against live pages after
    the first workflow run: ONS's slug-month convention is NOT
    consistent across bulletins. The GDP monthly estimate slug uses
    the DATA's reference month (confirmed live: the bulletin due out
    11 September 2026 lives at .../gdpmonthlyestimateukjuly2026, a
    2-month lag), while the CPI bulletin slug uses the RELEASE month
    itself (confirmed live: the release due 16 September 2026, covering
    August data, lives at .../consumerpriceinflationukseptember2026,
    zero lag). The original version of this function only ever guessed
    forward from the current month, so it could find CPI's slug but
    could never find GDP's, since july2026 is chronologically behind
    today -- which is exactly why the first real run returned zero UK
    events. Rather than hardcode a per-bulletin offset (fragile, and
    the labour market bulletin's own convention hasn't been separately
    confirmed), this tries a wide window covering both known
    conventions with margin either side."""
    now = datetime.now(timezone.utc)
    out = []
    y, m = now.year, now.month - 3
    while y < now.year or (y == now.year and m <= now.month + 3):
        yy, mm = y, m
        while mm < 1:
            mm += 12; yy -= 1
        while mm > 12:
            mm -= 12; yy += 1
        out.append(f"{MONTH_NAMES[mm - 1]}{yy}")
        m += 1
    return out


def fetch_bulletin_date(slug_prefix: str) -> tuple[str, str] | None:
    """Try each upcoming month's slug for this bulletin; return the first
    one that resolves with a real, not-yet-published release date."""
    for my in month_year_slugs():
        url = f"https://www.ons.gov.uk/releases/{slug_prefix}{my}"
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        m = RELEASE_DATE_RE.search(r.text)
        if not m:
            continue
        date_str, time_str = m.group(1), m.group(2)
        try:
            parsed = datetime.strptime(date_str, "%d %B %Y")
        except ValueError:
            continue
        # Only want dates that are actually still in the future -- a
        # slug can resolve to an ALREADY-published bulletin (this
        # month's, already out) rather than the next upcoming one.
        if parsed.date() < datetime.now(timezone.utc).date():
            continue
        return parsed.strftime("%Y-%m-%d"), (time_str or "")
    return None


def main():
    events = []
    for key, (slug_prefix, name) in TRACKED_BULLETINS.items():
        result = fetch_bulletin_date(slug_prefix)
        if result is None:
            print(f"WARNING: no upcoming date found for {key} ({slug_prefix}) "
                  f"in the next few months -- check the slug pattern by hand.",
                  file=sys.stderr)
            continue
        release_date, release_time = result
        events.append({
            "date": release_date,
            "country": "UK",
            "concept": key,
            "name": name,
            "source": f"ons.gov.uk/releases/{slug_prefix}...",
            "time": release_time or None,
        })

    events.sort(key=lambda e: e["date"])
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "UK",
        "events": events,
    }
    with open("data-calendar-uk.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} UK calendar events.")


if __name__ == "__main__":
    main()
