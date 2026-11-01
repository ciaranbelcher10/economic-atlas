"""Fetch Bank Indonesia BI-Rate decision dates and write data-calendar-id.json.

One official source: Bank Indonesia's calendar page
(bi.go.id/en/publikasi/kalender/default.aspx), whose "Board of Governors Meeting" table
lists every meeting of the year as a two-day range, e.g.
"Tuesday-Wednesday, 17-18 November 2026". The decision is announced on the second day.
Served: rate_decision. BI publishes no fixed announcement time, so none is given.
Indonesian CPI and GDP come from BPS, which blocks scripts (probe of 1 Nov 2026).

v1.9.44: rewritten on the shared calendar pattern. The old script stripped tags without
decoding the page's entities, so a non-breaking space between "17-18" and "November"
stopped every match, and it then overwrote the file with zero events. It now reads the
page as text lines like every other calendar script, fails loudly on a changed page and
keeps the last good file.
"""
from __future__ import annotations

import re
import sys
from datetime import date

from calendar_common import page_lines, run_single

OUT = "data-calendar-id.json"
URL = "https://www.bi.go.id/en/publikasi/kalender/default.aspx"
SRC = "bi.go.id/en/publikasi/kalender (official Board of Governors Meeting schedule)"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
ROW_RE = re.compile(r"(?:Mon|Tues|Wednes|Thurs|Fri)day\s*-\s*(?:Mon|Tues|Wednes|Thurs|Fri)day,?\s+"
                    r"(\d{1,2})\s*-\s*(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I)


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, rows = [], [], 0
    for line in page_lines(page):
        for m in ROW_RE.finditer(line):
            rows += 1
            try:
                d = date(int(m.group(4)), MONTHS.index(m.group(3).lower()) + 1, int(m.group(2)))
            except ValueError:
                problems.append(f"not a date: {m.group(0)!r}")
                continue
            events.append({"date": d.isoformat(), "country": "Indonesia", "concept": "rate_decision",
                           "name": "Bank Indonesia BI-Rate decision", "source": SRC, "time": None})
    if rows == 0:
        problems.append("no 'Tuesday-Wednesday, dd-dd Month yyyy' meeting rows found (bot wall or a changed page?)")
    elif rows < 6:
        problems.append(f"only {rows} meeting rows; the table normally lists the whole year")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=60)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "Indonesia", fetch_events, "Indonesia")


if __name__ == "__main__":
    sys.exit(main())
