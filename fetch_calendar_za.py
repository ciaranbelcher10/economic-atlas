"""Fetch the next South African Reserve Bank MPC decision and write data-calendar-za.json (v1.9.45).

One official source: the SARB home page (resbank.co.za/en/home), whose "Upcoming Events"
panel names the next Monetary Policy Committee statement, e.g. "Statement of the
Monetary Policy Committee on 19 November 2026". Served: rate_decision, that one date.

The panel only ever shows the next meeting, so between a meeting and the next
announcement there is no upcoming date: the run then reports it and keeps the old file,
and past decisions stay on the calendar through calendar_history.py. The SARB calendar
page is script-built and Stats SA blocks scripts (probes of 1 Nov 2026), so CPI and GDP
are not served. No announcement time is printed, so none is given.
"""
from __future__ import annotations

import re
import sys
from datetime import date

from calendar_common import page_lines, run_single

OUT = "data-calendar-za.json"
URL = "https://www.resbank.co.za/en/home"
SRC = "resbank.co.za upcoming events (official South African Reserve Bank home page)"
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
EVENT_RE = re.compile(r"Statement of the Monetary Policy Committee on (\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})", re.I)


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems = [], []
    lines = page_lines(page)
    if not any("Upcoming Events" in l for l in lines):
        problems.append("no 'Upcoming Events' panel found (bot wall or a changed page?)")
        return events, problems
    for line in lines:
        for m in EVENT_RE.finditer(line):
            try:
                d = date(int(m.group(3)), MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
            except ValueError:
                problems.append(f"not a date: {m.group(0)!r}")
                continue
            events.append({"date": d.isoformat(), "country": "South Africa", "concept": "rate_decision",
                           "name": "SARB Monetary Policy Committee rate decision", "source": SRC, "time": None})
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "South Africa", fetch_events, "South Africa")


if __name__ == "__main__":
    sys.exit(main())
