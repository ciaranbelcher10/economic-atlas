"""Fetch Denmark's official release dates and write data-calendar-dk.json (v1.9.45).

One official source: Statistics Denmark's scheduled releases (dst.dk/en/Statistik/planlagte),
a table of rows: date (dd-mm-yyyy, written with non-breaking hyphens), time, type (News
or Table), title, subject and period. Only "News" rows are read, as each Table row
repeats a release already announced as News. Served: cpi (Consumer price index), ppi
(Producer and import price index), jobs (Unemployment, Labour force survey), gdp (GDP
and national accounts) and trade (International or external trade in goods).

Not served: Danmarks Nationalbank rate changes, which follow the ECB's decisions (the
euro area rate decisions are already on the calendar).

Built from the live rows seen in the probe of 1 Nov 2026; the first real Actions run is
the real test. If the page changes shape the parser fails loudly and the old file is kept.
"""
from __future__ import annotations

import html
import re
import sys
from datetime import date

from calendar_common import clean_name, run_single

OUT = "data-calendar-dk.json"
URL = "https://www.dst.dk/en/Statistik/planlagte"
SRC = "dst.dk scheduled releases (official Statistics Denmark release calendar)"
CELL = r"<td[^>]*>(.*?)</td>\s*"
ROW_RE = re.compile(r"<tr[^>]*>\s*" + CELL * 6, re.S | re.I)
DATE_RE = re.compile(r"^(\d{2})\D(\d{2})\D(\d{4})$")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
# (pattern on the title, concept); first match wins
RULES = [
    (re.compile(r"^consumer price index|^harmonised index of consumer prices", re.I), "cpi"),
    (re.compile(r"^producer (and import )?price ind", re.I), "ppi"),
    (re.compile(r"^(registered |gross )?unemployment\b|^labour force survey", re.I), "jobs"),
    (re.compile(r"\bgdp\b|national accounts", re.I), "gdp"),
    (re.compile(r"^(international|external) trade in goods", re.I), "trade"),
]


def text(cell: str) -> str:
    return clean_name(html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\u2011", "-"))


def parse(page: str) -> tuple[list[dict], list[str]]:
    events, problems, rows, news = [], [], 0, []
    for m in ROW_RE.finditer(page):
        cells = [text(c) for c in m.groups()]
        dm = DATE_RE.match(cells[0])
        if not dm:
            continue
        rows += 1
        if cells[2].lower() != "news":
            continue
        news.append(f"{cells[0]} {cells[3]}")
        try:
            d = date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
        except ValueError:
            problems.append(f"not a date: {cells[0]!r}")
            continue
        tm = TIME_RE.match(cells[1])
        tlabel = f"{int(tm.group(1))}:{tm.group(2)}am Danish time" if tm and int(tm.group(1)) < 12 else None
        for rx, concept in RULES:
            if rx.search(cells[3]):
                name = cells[3] + (f" ({cells[5]})" if cells[5] else "")
                events.append({"date": d.isoformat(), "country": "Denmark", "concept": concept,
                               "name": name, "source": SRC, "time": tlabel})
                break
    if rows == 0:
        problems.append("no dated release rows found (bot wall or a changed page?)")
    elif rows < 20:
        problems.append(f"only {rows} release rows; the schedule normally lists dozens")
    elif not any(e["concept"] in ("cpi", "trade", "gdp") for e in events):
        # v1.9.46: name what was seen, so the Actions log shows how the titles are worded
        problems.append(f"no CPI, trade or GDP release found among the rows ({rows} rows, {len(news)} News); "
                        f"News titles seen: {'; '.join(news[:25]) or 'none'}")
    return events, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    events, problems = parse(r.text)
    if problems:
        raise ValueError("; ".join(problems))
    return events


def main() -> int:
    return run_single(OUT, "Denmark", fetch_events, "Denmark")


if __name__ == "__main__":
    sys.exit(main())
