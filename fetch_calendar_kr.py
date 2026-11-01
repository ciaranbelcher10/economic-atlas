"""Fetch South Korea's Bank of Korea release dates and write data-calendar-kr.json (v1.9.45).

One official source: the Bank of Korea's statistical calendar
(bok.or.kr/eng/stats/statsPublictSchdul/listCldr.do?menuNo=400359), a table of rows with
the release date (yyyy-mm-dd), the time (h:mm, Korea time) and the title, covering the
year. The Bank of Korea compiles Korea's national accounts and producer prices, so
served: gdp (Gross Domestic Product titles) and ppi (Producer Price Indices). Balance
of payments, money, credit and trade price indexes are left out.

Not served: Statistics Korea's CPI and jobs releases (its English schedule page returns
404) and Bank of Korea rate decisions, which are not on this calendar and have no
readable official schedule page (probes of 1 Nov 2026).

Built from the live rows seen in that probe; the first real Actions run is the real
test. If the page changes shape the parser fails loudly and the old file is kept.
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date

from calendar_common import clean_name, run_single

OUT = "data-calendar-kr.json"
URL = "https://www.bok.or.kr/eng/stats/statsPublictSchdul/listCldr.do?menuNo=400359"
SRC = "bok.or.kr statistical calendar (official Bank of Korea release calendar)"
ROW_RE = re.compile(r"<td>\s*(\d{4})-(\d{2})-(\d{2})\s*</td>\s*<td>\s*(\d{1,2}):(\d{2})\s*</td>\s*"
                    r"<td[^>]*class=[\"']title[\"'][^>]*>(.*?)</td>", re.S | re.I)
RULES = [
    (re.compile(r"gross domestic product|\bgdp\b", re.I), "gdp"),
    (re.compile(r"^producer price ind", re.I), "ppi"),
]


def time_label(h: int, m: int) -> str:
    if h == 12:
        return f"12:{m:02d}pm Korea time"
    return f"{h}:{m:02d}am Korea time" if h < 12 else f"{h - 12}:{m:02d}pm Korea time"


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, rows = [], [], 0
    for m in ROW_RE.finditer(page):
        rows += 1
        title = clean_name(html.unescape(re.sub(r"<[^>]+>", " ", m.group(6))))
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            problems.append(f"not a date: {m.group(0)[:60]!r}")
            continue
        for rx, concept in RULES:
            if rx.search(title):
                events.append({"date": d.isoformat(), "country": "South Korea", "concept": concept,
                               "name": title, "source": SRC,
                               "time": time_label(int(m.group(4)), int(m.group(5)))})
                break
    if rows == 0:
        problems.append("no 'date | time | title' rows found (bot wall or a changed page?)")
    elif rows < 20:
        problems.append(f"only {rows} rows; the calendar normally lists the whole year")
    elif not events:
        problems.append("no GDP or producer price release found among the rows")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "South Korea", fetch_events, "South Korea")


if __name__ == "__main__":
    sys.exit(main())
