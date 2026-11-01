"""Fetch Swiss National Bank rate decision dates and write data-calendar-ch.json (v1.9.44).

One official source: the SNB's own time schedule
(snb.ch/en/services-events/digital-services/event-schedule), a list of items each with
a date (dd.mm.yyyy), a time (hh:mm) and a title. Served: rate_decision, taken from the
"Monetary policy assessment of ... (press release)" items. The news conference that
follows and every other item (speeches, balance of payments, interim results) are left
out. Swiss CPI and GDP come from the Federal Statistical Office, whose calendar is
script-built and could not be read (probe of 1 Nov 2026).

Built from the live markup seen in that probe; the first real Actions run is the real
test. If the page changes shape the parser fails loudly and the old file is kept.
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date

from calendar_common import clean_name, run_single

OUT = "data-calendar-ch.json"
URL = "https://www.snb.ch/en/services-events/digital-services/event-schedule"
SRC = "snb.ch time schedule (official Swiss National Bank event schedule)"
ITEM_RE = re.compile(
    r'publication-date[^>]*>\s*(\d{2})\.(\d{2})\.(\d{4})\s*<'
    r'(?:(?!publication-date).)*?publication-type[^>]*>\s*(\d{1,2}):(\d{2})\s*<'
    r'(?:(?!publication-date).)*?<h3[^>]*>(.*?)</h3>', re.S)
DECISION_RE = re.compile(r"^Monetary policy assessment of (.+?) \(press release\)$", re.I)


def time_label(h: int, m: int) -> str:
    suffix = "am" if h < 12 else "pm"
    h12 = h if 1 <= h <= 12 else (h - 12 if h > 12 else 12)
    return f"{h12}:{m:02d}{suffix} Swiss time"


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, items = [], [], 0
    for m in ITEM_RE.finditer(page):
        items += 1
        title = clean_name(html.unescape(re.sub(r"<[^>]+>", " ", m.group(6))).replace("\ufeff", ""))
        mm = DECISION_RE.match(title)
        if not mm:
            continue
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            problems.append(f"not a date: {m.group(0)[:60]!r}")
            continue
        events.append({"date": d.isoformat(), "country": "Switzerland", "concept": "rate_decision",
                       "name": "SNB monetary policy assessment (rate decision)", "source": SRC,
                       "time": time_label(int(m.group(4)), int(m.group(5)))})
    if items == 0:
        problems.append("no dated schedule items found (bot wall or a changed page?)")
    elif items < 5:
        problems.append(f"only {items} schedule items; the page normally lists dozens")
    elif not events:
        problems.append("no 'Monetary policy assessment ... (press release)' item found")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "Switzerland", fetch_events, "Switzerland")


if __name__ == "__main__":
    sys.exit(main())
