"""Fetch China's official release dates (NBS) and write data-calendar-cn.json.

Source: the National Bureau of Statistics' "Regular Press Release Calendar of
NBS in <year>", an official annual table (rows = releases, columns = months,
cells like "9/Wed"). The index page links each year's table, so next year's is
picked up automatically once NBS publishes it (usually late December).

Served (site concepts):
  - gdp: "National Economic Performance" in Jan, Apr, Jul and Oct only. NBS's
    own note 3 says annual and quarterly performance (GDP) is released in those
    months; the other months carry monthly activity data, which is not GDP.
  - cpi: Monthly Report on Consumer Price Index.
  - ppi: Monthly Report on Industrial Producer Price Index.
Not served: PMI and the monthly activity reports (no matching site concept),
and the PBOC's Loan Prime Rate (published on the 20th of each month, moved for
holidays: a rule, not a published list of dates, so it is not on the calendar).

Integrity: every cell's weekday must match its date ("9/Wed" must be a
Wednesday), or the cell is rejected and the run fails. Built v1.7.30 from the
probe of 8 Oct 2026. On any failure the existing file is left untouched.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests

INDEX = "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/"
OUT = "data-calendar-cn.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CELL_RE = re.compile(r"(\d{1,2})/(Mon|Tue|Wed|Thu|Fri|Sat|Sun)")
A_TAG_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.S | re.I)
YEAR_RE = re.compile(r"Regular Press Release Calendar of NBS in (\d{4})", re.I)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def year_links(index_html: str) -> dict[int, str]:
    """{year: href} from the index page, whatever the attribute order or label prefix."""
    out = {}
    for a in A_TAG_RE.findall(index_html):
        y, h = YEAR_RE.search(a), HREF_RE.search(a)
        if y and h:
            out.setdefault(int(y.group(1)), h.group(1))
    return out
GDP_MONTHS = {1, 4, 7, 10}
GDP_QUARTER = {1: " (Q4 and full year)", 4: " (Q1)", 7: " (Q2)", 10: " (Q3)"}

# (row title starts with, concept, event name, time)
ROWS = [
    ("National Economic Performance", "gdp", "GDP and national economic performance", "10:00am Beijing"),
    ("Monthly Report on Consumer Price Index", "cpi", "Consumer Price Index", "9:30am Beijing"),
    ("Monthly Report on Industrial Producer Price Index", "ppi", "Industrial Producer Price Index", "9:30am Beijing"),
]


def cells(row_html: str) -> list[str]:
    return [html.unescape(re.sub(r"<[^>]+>|\s+", " ", c)).strip()
            for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)]


def parse_year(page: str, year: int, source: str) -> tuple[list[dict], list[str]]:
    """Events from one year's table, and a list of problems (empty if clean)."""
    problems, events = [], []
    rows = [cells(r) for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)]
    header = next((r for r in rows if len(r) >= 14 and r[2].startswith("Jan")), None)
    if header is None:
        return [], ["no month header row (Jan. ... Dec.) found"]
    for prefix, concept, name, time in ROWS:
        row = next((r for r in rows if len(r) >= 14 and r[1].startswith(prefix)), None)
        if row is None:
            problems.append(f"row not found: {prefix}")
            continue
        for month, cell in enumerate(row[2:14], start=1):
            if concept == "gdp" and month not in GDP_MONTHS:
                continue
            for day, wd in CELL_RE.findall(cell):
                try:
                    d = date(year, month, int(day))
                except ValueError:
                    problems.append(f"{prefix} {year}-{month:02d}: invalid day {day}")
                    continue
                if DAYS[d.weekday()] != wd:
                    problems.append(f"{prefix} {d}: table says {wd}, the date is a {DAYS[d.weekday()]}")
                    continue
                label = name + (GDP_QUARTER[month] if concept == "gdp" else "")
                events.append({"date": d.isoformat(), "country": "China", "concept": concept,
                               "name": label, "source": source, "time": time})
    return events, problems


def main() -> int:
    s = requests.Session()
    s.headers.update(UA)
    try:
        idx = s.get(INDEX, timeout=40)
        idx.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching NBS calendar index: {e}", file=sys.stderr)
        return 1
    years = {y: urljoin(idx.url, h) for y, h in year_links(idx.text).items()}
    today = datetime.now(timezone.utc).date()
    wanted = [y for y in (today.year, today.year + 1) if y in years]
    if today.year not in years:
        print(f"ERROR: the NBS index lists no {today.year} calendar (found {sorted(years)})", file=sys.stderr)
        return 1
    events, problems = [], []
    for y in wanted:
        try:
            r = s.get(years[y], timeout=40)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"ERROR fetching NBS {y} calendar: {e}", file=sys.stderr)
            return 1
        ev, pr = parse_year(r.content.decode("utf-8", "replace"), y,
                            f"stats.gov.cn Regular Press Release Calendar of NBS in {y} (official)")
        events += ev
        problems += [f"{y}: {p}" for p in pr]
    if problems:
        for p in problems:
            print(f"ERROR {p}", file=sys.stderr)
        print("Not writing: the table did not parse cleanly; existing file kept.", file=sys.stderr)
        return 1
    events = sorted({(e["date"], e["concept"]): e for e in events if e["date"] >= today.isoformat()}.values(),
                    key=lambda e: (e["date"], e["concept"]))
    if not events:
        print("ERROR: zero upcoming China events parsed; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "China",
                   "events": events}, f, indent=2)
    print(f"Wrote {len(events)} China calendar events ({', '.join(str(y) for y in wanted)} tables).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
