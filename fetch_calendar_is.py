"""Fetch Iceland's official release dates and write data-calendar-is.json (v1.8.14).

One official source: Statistics Iceland's advance release calendar
(statice.is/publications/news-archive/advance-release-calendar/), a table of
"d.m.yyyy | title" rows covering the coming months. Served: cpi (Consumer price
index), jobs (monthly Labour market), trade (Trade in goods, including preliminary
figures), ppi (Producer price index) and gdp (national accounts / GDP titles).
The harmonised index, wage index, VAT turnover, tourism and the like are left out.

Not served: Central Bank of Iceland rate decisions. The bank's pages
(cb.is/monetary-policy/...) were script-only shells in the probe of 18 Oct 2026, so
no official decision schedule could be read; it is left out rather than guessed.

Built from the rows seen in that probe; the first real Actions run is the real
test. If the page changes shape the parser fails loudly and the old file is kept.
"""
from __future__ import annotations

import re
import sys
from datetime import date

from calendar_common import clean_name, page_lines, run_single

OUT = "data-calendar-is.json"
URL = "https://statice.is/publications/news-archive/advance-release-calendar/"
SRC = "statice.is advance release calendar (official Statistics Iceland release calendar)"
ROW_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4}) \| (.+?)(?: \|)*$")

# (title pattern, concept, name template; None keeps the title)
RULES = [
    (re.compile(r"^Consumer price index in (.+)$", re.I), "cpi", "Consumer price index ({p})"),
    (re.compile(r"^Producer price index in (.+)$", re.I), "ppi", "Producer price index ({p})"),
    (re.compile(r"^Labour market in ([A-Za-z]+ \d{4})$", re.I), "jobs", "Labour market ({p})"),
    (re.compile(r"^Trade in goods in (.+?) - Preliminary figures$", re.I), "trade", "Trade in goods, preliminary figures ({p})"),
    (re.compile(r"^Trade in goods in ([A-Za-z]+ \d{4})$", re.I), "trade", "Trade in goods ({p})"),
    (re.compile(r"^(?:Gross domestic product|GDP|Quarterly national accounts|National accounts)\b.*$", re.I), "gdp", None),
]


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, rows = [], [], 0
    for line in page_lines(page):
        m = ROW_RE.match(line)
        if not m:
            continue
        rows += 1
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            problems.append(f"not a date: {line[:60]!r}")
            continue
        title = m.group(4).strip()
        for rx, concept, tmpl in RULES:
            mm = rx.match(title)
            if mm:
                name = tmpl.format(p=mm.group(1)) if tmpl else title
                events.append({"date": d.isoformat(), "country": "Iceland", "concept": concept,
                               "name": clean_name(name), "source": SRC, "time": None})
                break
    if rows == 0:
        problems.append("no 'd.m.yyyy | title' rows found (bot wall or a changed page?)")
    elif rows < 10:
        problems.append(f"only {rows} dated rows; the calendar normally lists dozens")
    elif not any(e["concept"] == "cpi" for e in events):
        problems.append("no Consumer price index release found among the rows")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "Iceland", fetch_events, "Iceland")


if __name__ == "__main__":
    sys.exit(main())
