"""Fetch Hungary's official release dates and write data-calendar-hu.json.

Source (v1.7.35): the Magyar Nemzeti Bank's Monetary Council page
(mnb.hu/en/monetary-policy/the-monetary-council) publishes each year's
scheduled meetings in tables, every policy meeting marked "(P)" and every
non-policy meeting "(NP)". The year comes from the heading above each table
("scheduled meetings in 2027"); the MNB announces the base-rate decision at
2 p.m. Budapest time on the policy-meeting day.
Not served yet: KSH (Hungarian Central Statistical Office) release dates.
Its publication calendar (ksh.hu/katalogus/#/en) is a script-rendered app;
its data source needs a probe, as CZSO's did.

Integrity: every policy date must be a real weekday; each year found must
have 6 to 14 policy meetings; at least one year must be found. On any
failure the previous upcoming events are kept and the file is not rewritten
with less. Built v1.7.35 from fetch_calendar_cz.py.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone

import requests

OUT = "data-calendar-hu.json"
MNB_URL = "https://www.mnb.hu/en/monetary-policy/the-monetary-council"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
MNB_SRC = "mnb.hu Monetary Council meeting schedule (official)"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
YEAR_RE = re.compile(r"scheduled meetings in (\d{4})")
P_RE = re.compile(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") \(P\)")


def page_text(page: str) -> str:
    page = re.sub(r"<!--.*?-->|<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def parse_mnb(page: str) -> tuple[list[dict], list[str]]:
    text = page_text(page)
    heads = list(YEAR_RE.finditer(text))
    events, problems = [], []
    if not heads:
        return [], ["no 'scheduled meetings in YYYY' heading on the page"]
    seen_years = set()
    for i, h in enumerate(heads):
        year = int(h.group(1))
        if year in seen_years:
            continue
        seen_years.add(year)
        seg = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        cut = seg.find("Inflation Report")
        seg = seg[:cut] if cut > 0 else seg[:3000]
        found = []
        for d, mon in P_RE.findall(seg):
            try:
                day = date(year, MONTHS.index(mon) + 1, int(d))
            except ValueError:
                problems.append(f"impossible date {d} {mon} {year}")
                continue
            if day.weekday() > 4:
                problems.append(f"{day} ({day:%A}) is not a weekday")
                continue
            found.append(day)
        if not 6 <= len(found) <= 14:
            problems.append(f"{len(found)} policy meetings found for {year}: not a schedule the MNB keeps")
        for day in found:
            events.append({"date": day.isoformat(), "country": "Hungary", "concept": "rate_decision",
                           "name": "MNB Monetary Council base rate decision", "source": MNB_SRC,
                           "time": "2:00pm Budapest time"})
    return events, problems


def main(today: date | None = None, get=None) -> int:
    get = get or requests.get
    today = today or datetime.now(timezone.utc).date()
    try:
        r = get(MNB_URL, timeout=40, headers=UA)
        r.raise_for_status()
        ev, problems = parse_mnb(r.content.decode("utf-8", "replace"))
        if problems:
            raise ValueError("; ".join(problems))
    except (requests.RequestException, ValueError) as e:
        print(f"ERROR MNB: {e}; existing file kept.", file=sys.stderr)
        return 1
    events = sorted({e["date"]: e for e in ev if e["date"] >= today.isoformat()}.values(), key=lambda e: e["date"])
    if not events:
        print("ERROR: zero upcoming Hungary events; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Hungary",
                   "events": events}, f, indent=2)
    print(f"Wrote {len(events)} Hungary calendar events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
