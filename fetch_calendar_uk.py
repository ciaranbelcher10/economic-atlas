"""Fetch upcoming UK release dates and write data-calendar-uk.json.

Run:  python3 fetch_calendar_uk.py
No API key needed -- this is ONS's own public release-calendar iCal feed.

REWRITTEN from a slug-guessing regex scraper to parsing ONS's official
iCal feed at https://www.ons.gov.uk/calendar/releasecalendar, after the
first real workflow run wrote 0 UK events and root-causing showed TWO
separate bugs in the old approach:

1. Wrong slug prefixes, confirmed by fetching real ONS search results:
   the CPI bulletin's real slug is "consumerpriceinflationuk{month}{year}"
   (the old script was missing the "uk"), and the labour market
   bulletin's real slug is "uklabourmarket{month}{year}" (the old
   script's "labourmarketoverviewuk" prefix doesn't exist at all --
   every slug tried for it 404'd, which is exactly what the log showed).
2. Even where the slug WAS right (GDP, public finances, trade), the
   live page returned HTTP 200 but the "Release date:" regex still
   didn't match against the raw HTML, despite the same text being
   plainly visible when the page is rendered/extracted as text. Never
   got to the bottom of the exact markup cause (no raw-HTML access from
   this environment), and it doesn't matter now -- the iCal feed sidesteps
   the whole problem, since it returns each release's exact name and
   DTSTART as clean structured fields, no page-scraping or slug
   conventions to guess at all.

The feed (confirmed live, fetched directly) returns a rolling ~3 month
window of every upcoming ONS release as VEVENT blocks, e.g.:
  SUMMARY:GDP monthly estimate, UK: September 2026
  DTSTART:20261112T070000Z
  UID:/releases/gdpmonthlyestimateukseptember2026
This script fetches that feed once and matches each tracked bulletin by
its exact SUMMARY prefix, filtering out the "time series"/regional/
quarterly companion releases ONS publishes alongside the headline
bulletin under similar names.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

FEED_URL = "https://www.ons.gov.uk/calendar/releasecalendar"

# key: (name, a function that decides whether a given SUMMARY line is
# THIS bulletin's headline release, not a companion "time series" /
# regional / quarterly release published under a similar name).
def _is_gdp_monthly(s: str) -> bool:
    return s.startswith("GDP monthly estimate, UK:") and "time series" not in s.lower()

def _is_cpi(s: str) -> bool:
    return s.startswith("Consumer price inflation, UK:") and "time series" not in s.lower()

def _is_labour_market(s: str) -> bool:
    return s.startswith("UK Labour Market:") and "time series" not in s.lower()

def _is_public_finances(s: str) -> bool:
    return s.startswith("Public sector finances, UK:") and "time series" not in s.lower()

def _is_trade(s: str) -> bool:
    sl = s.lower()
    return sl.startswith("uk trade:") and "time series" not in sl and "quarterly" not in sl and "in services" not in sl

TRACKED_BULLETINS = {
    "gdp_monthly": ("GDP monthly estimate", _is_gdp_monthly),
    "cpi": ("Consumer price inflation", _is_cpi),
    "labour_market": ("UK Labour Market", _is_labour_market),
    "public_finances": ("Public sector finances", _is_public_finances),
    "trade": ("UK trade", _is_trade),
}

VEVENT_RE = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.S)
FIELD_RE = re.compile(r"^([A-Z]+):(.*)$", re.M)


def parse_events(ics_text: str) -> list[dict]:
    events = []
    for block in VEVENT_RE.findall(ics_text):
        fields = dict(FIELD_RE.findall(block))
        summary = fields.get("SUMMARY", "").strip()
        dtstart = fields.get("DTSTART", "").strip()
        uid = fields.get("UID", "").strip()
        if not summary or not dtstart:
            continue
        try:
            dt = datetime.strptime(dtstart, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        events.append({"summary": summary, "dt": dt, "uid": uid})
    return events


def main():
    try:
        r = requests.get(FEED_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
    except requests.RequestException as e:
        print(f"ERROR fetching ONS release calendar feed: {e}", file=sys.stderr)
        out = {"generated": datetime.now(timezone.utc).isoformat(), "country": "UK", "events": []}
        with open("data-calendar-uk.json", "w") as f:
            json.dump(out, f, indent=2)
        print("Wrote 0 UK calendar events.")
        return
    if r.status_code != 200:
        print(f"ERROR: ONS release calendar feed returned HTTP {r.status_code}", file=sys.stderr)
        out = {"generated": datetime.now(timezone.utc).isoformat(), "country": "UK", "events": []}
        with open("data-calendar-uk.json", "w") as f:
            json.dump(out, f, indent=2)
        print("Wrote 0 UK calendar events.")
        return

    all_events = parse_events(r.text)
    now = datetime.now(timezone.utc)
    events = []
    for key, (name, matcher) in TRACKED_BULLETINS.items():
        matches = [e for e in all_events if matcher(e["summary"]) and e["dt"] >= now]
        if not matches:
            print(f"WARNING: no upcoming '{name}' release found in the feed "
                  f"(feed covers roughly the next 3 months -- check back closer "
                  f"to the release, or the SUMMARY naming convention may have "
                  f"changed on ONS's end).", file=sys.stderr)
            continue
        matches.sort(key=lambda e: e["dt"])
        soonest = matches[0]
        events.append({
            "date": soonest["dt"].strftime("%Y-%m-%d"),
            "country": "UK",
            "concept": key,
            "name": name,
            "source": f"ons.gov.uk{soonest['uid']} (official ONS release-calendar feed)",
            # DTSTART is UTC, but ONS displays release times in UK local
            # time (BST/GMT depending on time of year) -- converting
            # correctly needs a real timezone library the other fetch
            # scripts don't currently use, so left as None rather than
            # silently showing a wrong hour (e.g. a genuine 7:00am BST
            # release stored as UTC would display as "6:00am").
            "time": None,
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
