"""Fetch Bank of Thailand MPC decision dates and write data-calendar-th.json (v1.9.44).

One official source: the Bank of Thailand's Monetary Policy Committee meeting page
(bot.or.th/en/our-roles/monetary-policy/mpc-meeting.html), which holds a schedule table
per year. Each row starts with the meeting date (e.g. "Wed. 23 Dec. 2026"), then the
press release, minutes and report dates. Served: rate_decision, the first date in each
row. Thai CPI and GDP come from other offices whose calendars could not be read
(probe of 1 Nov 2026), so they are left out.

No announcement time is printed on the schedule, so none is given. Built from the live
rows seen in that probe; the first real Actions run is the real test. If the page
changes shape the parser fails loudly and the old file is kept.
"""
from __future__ import annotations

import re
import sys
from datetime import date

from calendar_common import page_lines, run_single

OUT = "data-calendar-th.json"
URL = "https://www.bot.or.th/en/our-roles/monetary-policy/mpc-meeting.html"
SRC = "bot.or.th MPC meeting schedule (official Bank of Thailand schedule)"
MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun",
                                       "jul", "aug", "sep", "oct", "nov", "dec"])}
# a schedule row: optional empty first cell, then the meeting date
ROW_RE = re.compile(r"^(?:\|\s*)?(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\.?\s+(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})\b")


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, rows = [], [], 0
    for line in page_lines(page):
        m = ROW_RE.match(line)
        if not m:
            continue
        rows += 1
        mon = MON.get(m.group(2).lower())
        try:
            d = date(int(m.group(3)), mon, int(m.group(1))) if mon else None
        except ValueError:
            d = None
        if not d:
            problems.append(f"not a date: {line[:60]!r}")
            continue
        events.append({"date": d.isoformat(), "country": "Thailand", "concept": "rate_decision",
                       "name": "Bank of Thailand MPC rate decision", "source": SRC, "time": None})
    if rows == 0:
        problems.append("no schedule rows starting with a meeting date (bot wall or a changed page?)")
    elif rows < 6:
        problems.append(f"only {rows} schedule rows; the page normally lists two years of meetings")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "Thailand", fetch_events, "Thailand")


if __name__ == "__main__":
    sys.exit(main())
