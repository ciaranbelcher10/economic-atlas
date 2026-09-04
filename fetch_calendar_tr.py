"""Fetch upcoming CBRT (Turkey) Monetary Policy Committee decision dates
and write data-calendar-tr.json.

Run:  python3 fetch_calendar_tr.py
No API key needed -- public tcmb.gov.tr page.

Source: https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Temel+Faaliyetler/Para+Politikasi/PPK/2026
-- TCMB's own official PPK (Monetary Policy Committee) schedule page for
the year, confirmed to exist tonight (found via search, not yet fetched
directly -- the September 10, 2026, 14:00 date used on this calendar
came from several independent Turkish financial news outlets citing
TCMB's own published calendar consistently, not from a direct fetch of
this page itself). Fetching the primary page directly rather than
relying on secondary reporting is the natural next step before trusting
this script fully.

Real, useful context found tonight: CBRT doesn't hold a meeting every
month (no August 2026 meeting, confirmed across multiple sources) --
so month-by-month assumptions would be wrong; only the actual published
calendar tells you which months have a decision.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = ("https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/"
       "Temel+Faaliyetler/Para+Politikasi/PPK/2026")

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5,
    "haziran": 6, "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9,
    "ekim": 10, "kasım": 11, "kasim": 11, "aralık": 12, "aralik": 12,
}

# e.g. "10 Eylül 2026" -- DD MonthName YYYY, confirmed as the format
# used in every secondary source quoting TCMB's own calendar tonight.
DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(TURKISH_MONTHS.keys()) + r")\s+(\d{4})", re.I
)


def main():
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "economic-atlas/0.1"})
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching TCMB page: {e}", file=sys.stderr)
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", r.text)
    today = datetime.now(timezone.utc).date()

    events = []
    seen = set()
    for m in DATE_RE.finditer(text):
        day, month_name, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = TURKISH_MONTHS.get(month_name)
        if not month:
            continue
        try:
            d = datetime(year, month, day).date()
        except ValueError:
            continue
        if d < today or d.isoformat() in seen:
            continue
        seen.add(d.isoformat())
        events.append({
            "date": d.isoformat(),
            "country": "Turkey",
            "concept": "rate_decision",
            "name": "CBRT Monetary Policy Committee decision",
            "source": "tcmb.gov.tr (official PPK 2026 schedule)",
            "time": "2:00pm TRT",
        })

    events.sort(key=lambda e: e["date"])
    if not events:
        print("WARNING: parsed zero upcoming PPK dates -- this script's "
              "URL/pattern was built from secondary reporting rather than "
              "a confirmed direct fetch of tcmb.gov.tr, so a zero result "
              "here is a real signal to check the URL and page structure "
              "by hand, not just retry.", file=sys.stderr)

    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "Turkey",
        "events": events,
    }
    with open("data-calendar-tr.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} Turkey calendar events.")


if __name__ == "__main__":
    main()
