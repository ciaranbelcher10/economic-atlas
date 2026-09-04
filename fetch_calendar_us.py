"""Fetch upcoming US release dates and write data-calendar-us.json.

Run:  FRED_API_KEY=yourkey python3 fetch_calendar_us.py

Source: FRED's own Releases API (fred/releases + fred/release/dates), the
same api.stlouisfed.org host and FRED_API_KEY secret already used by
fetch_us.py -- no new credential needed. This is a real, documented,
stable API (https://fred.stlouisfed.org/docs/api/fred/releases_dates.html),
not a scrape of the release-calendar webpage.

Approach: FRED release IDs (rid=) are internal integers that are NOT
guessable and can change their meaning between releases, so this script
looks each one up BY NAME via fred/releases (matching against
TRACKED_RELEASE_NAMES below) rather than hardcoding rid numbers that
could silently point at the wrong release after a FRED-side change.
Once the right release IDs are found, fred/release/dates?include_release_
dates_with_no_data=true is what actually returns FUTURE scheduled dates
-- without that flag the endpoint only returns dates data was already
published for.

NOT YET RUN LIVE -- this sandbox's network allowlist doesn't include
api.stlouisfed.org, so this has been written and reasoned through against
FRED's real, documented API shape (confirmed via web search/fetch of
FRED's own docs and release-calendar page), but not executed end-to-end.
Treat the first real GitHub Actions run log as the genuine test, per the
site's existing convention for every other fetch script.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

FRED_BASE = "https://api.stlouisfed.org/fred"

# Human names as they appear in FRED's own release list (confirmed by
# fetching https://fred.stlouisfed.org/releases/calendar directly) --
# looked up by substring match against fred/releases, not by a
# hardcoded rid, so a FRED-side renumbering can't silently break this.
TRACKED_RELEASE_NAMES = {
    "cpi": "Consumer Price Index",
    "jobs": "Employment Situation",
    "fomc": "FOMC Press Release",
    "gdp": "Gross Domestic Product",
    "ppi": "Producer Price Index",
    "pce": "Personal Income and Outlays",
}


def find_release_ids(key: str) -> dict[str, int]:
    """Map our short keys -> FRED's own numeric release id, by name match."""
    r = requests.get(f"{FRED_BASE}/releases", params={
        "api_key": key, "file_type": "json", "limit": 1000,
    }, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    releases = r.json().get("releases", [])
    found = {}
    for short_key, wanted_name in TRACKED_RELEASE_NAMES.items():
        for rel in releases:
            if rel.get("name", "").strip().lower() == wanted_name.lower():
                found[short_key] = rel["id"]
                break
    missing = set(TRACKED_RELEASE_NAMES) - set(found)
    if missing:
        print(f"WARNING: could not find FRED release id for: {sorted(missing)} "
              f"-- name may have changed on FRED's side, check manually.",
              file=sys.stderr)
    return found


def fetch_upcoming_dates(release_id: int, key: str, horizon_days: int = 120) -> list[str]:
    """Real future dates for one release, via fred/release/dates.
    include_release_dates_with_no_data=true is required to get dates that
    haven't happened yet -- without it FRED only returns already-published
    dates, which is useless for a forward-looking calendar."""
    today = date.today()
    r = requests.get(f"{FRED_BASE}/release/dates", params={
        "release_id": release_id,
        "api_key": key,
        "file_type": "json",
        "include_release_dates_with_no_data": "true",
        "realtime_start": today.isoformat(),
        "realtime_end": (today + timedelta(days=horizon_days)).isoformat(),
        "sort_order": "asc",
    }, timeout=60, headers={"User-Agent": "economic-atlas/0.1"})
    r.raise_for_status()
    return [d["date"] for d in r.json().get("release_dates", [])
            if d.get("date", "") >= today.isoformat()]


def main():
    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("FRED_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    release_ids = find_release_ids(key)
    events = []
    for short_key, rid in release_ids.items():
        try:
            dates = fetch_upcoming_dates(rid, key)
        except requests.RequestException as e:
            print(f"WARNING: fetch failed for {short_key} (rid={rid}): {e}", file=sys.stderr)
            continue
        for d in dates:
            events.append({
                "date": d,
                "country": "US",
                "concept": short_key,
                "name": TRACKED_RELEASE_NAMES[short_key],
                "source": "fred.stlouisfed.org (FRED Releases API)",
                # FRED's release/dates endpoint does not return a
                # time-of-day -- that lives on each publisher's own site
                # (e.g. BLS always publishes CPI/jobs at 8:30am ET, the
                # Fed always publishes FOMC decisions at 2:00pm ET) and
                # would need a small per-release lookup table alongside
                # this, not a FRED API field. Left blank rather than
                # guessed.
                "time": None,
            })

    events.sort(key=lambda e: e["date"])
    out = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "country": "US",
        "events": events,
    }
    with open("data-calendar-us.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(events)} US calendar events.")


if __name__ == "__main__":
    main()
