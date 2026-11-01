"""Fetch Australia's official release dates and write data-calendar-au.json.

Source: the ABS release calendar's monthly pages
(https://www.abs.gov.au/release-calendar/future-releases-calendar/YYYYMM). They are
server-rendered HTML tables, one row of day numbers per week followed by a row of
the releases on those days, each written as "<Title> <Period> - <time>". The ABS
publishes about six months ahead; this reads the current month and the next five.
All ABS times are Canberra time.

Served (title as the ABS writes it):
  cpi    Consumer Price Index, Australia (monthly)
  jobs   Labour Force, Australia (monthly; the "Detailed" release is not served)
  gdp    Australian National Accounts: National Income, Expenditure and Product (quarterly)
  trade  International Trade in Goods (monthly)
  ppi    Producer Price Indexes, Australia (quarterly)
"Updated information" re-releases are skipped.

Not served: RBA cash rate decisions. rba.gov.au returns a "JavaScript is blocked"
page to scripts, so the dates stay off the calendar rather than being hand-entered.

Integrity: every page must be an ABS release-calendar page for the month asked for;
every event's date must fall inside that month; the first three months must all
load; at least one CPI and one Labour Force release must be found. Otherwise, or on
any fetch error, the existing file is left untouched and the run returns 1, with a
short sample of what was read so the Actions log shows why. Built v1.9.41,
replacing the empty placeholder.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone

import requests

URL = "https://www.abs.gov.au/release-calendar/future-releases-calendar/{ym}"
OUT = "data-calendar-au.json"
SRC = "abs.gov.au release calendar (official monthly calendar pages)"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en"}
MONTHS_AHEAD = 6
MUST_LOAD = 3
# titles are matched exactly and must be followed by a period, so "Labour Force,
# Australia, Detailed" never counts as "Labour Force, Australia"
TITLES = [
    ("Consumer Price Index, Australia", "cpi", "Consumer Price Index"),
    ("Labour Force, Australia", "jobs", "Labour Force"),
    ("Australian National Accounts: National Income, Expenditure and Product", "gdp", "National Accounts (GDP)"),
    ("International Trade in Goods", "trade", "International Trade in Goods"),
    ("Producer Price Indexes, Australia", "ppi", "Producer Price Indexes"),
]
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
PERIOD = rf"(?:(?:{'|'.join(MONTHS[1:])})(?: Quarter)? \d{{4}}|\d{{4}}-\d{{2}} financial year)"
TIME = r"(\d{1,2}:\d{2}\s*[ap]m)"


def month_list(today: date, n: int) -> list[tuple[int, int]]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def cell_text(cell_html: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", cell_html)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()


def rows_of(markup: str) -> list[list[str]]:
    """The calendar table's rows, each a list of cell texts in column order."""
    m = re.search(r"(?is)<table\b.*?</table>", markup)
    if not m:
        return []
    rows = []
    for tr in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", m.group(0)):
        cells = re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", tr)
        rows.append([cell_text(c) for c in cells])
    return rows


def releases_in(text: str) -> list[tuple[str, str, str, str]]:
    """(concept, name, period, time) for each served release written in a cell."""
    found = []
    for title, concept, name in TITLES:
        for m in re.finditer(re.escape(title) + r"\s+(" + PERIOD + r")\s*-\s*" + TIME, text):
            if text[:m.start()].rstrip().endswith("Updated information"):
                continue
            found.append((concept, name, m.group(1), m.group(2).replace(" ", "")))
    return found


class DayTracker:
    """Which day numbers on a month page belong to that month (the grid shows
    the tail of the previous month and the head of the next)."""
    def __init__(self):
        self.started = False
        self.ended = False

    def see(self, d: int):
        if d == 1 and self.started:
            self.ended = True
        if d == 1 and not self.started:
            self.started = True
        return d if self.started and not self.ended else None


def parse_month(markup: str, y: int, m: int) -> tuple[list[dict], list[str]]:
    """Events dated inside month (y, m), and problems if the page is not what it should be."""
    want = f"{MONTHS[m]} {y}"
    if "release-calendar" not in markup or want not in markup:
        return [], [f"{y}-{m:02d}: not an ABS release-calendar page for {want}"]
    rows = rows_of(markup)
    if not rows:
        return [], [f"{y}-{m:02d}: no calendar table on the page"]
    events, problems, col_day, track = [], [], [], DayTracker()
    for cells in rows:
        if cells and all(re.fullmatch(r"\d{1,2}", c) for c in cells):
            col_day = [track.see(int(c)) for c in cells]
            continue
        for i, c in enumerate(cells):
            day = col_day[i] if i < len(col_day) else None
            lead = re.match(r"^(\d{1,2})\s+\S", c)
            if lead:
                # day number and releases in one cell (in case the ABS changes layout)
                day = track.see(int(lead.group(1)))
            elif re.fullmatch(r"\d{1,2}", c):
                track.see(int(c))
                continue
            rel = releases_in(c)
            if not rel or day is None:
                continue    # nothing served, or a neighbouring month's day (its own page has it)
            try:
                ds = date(y, m, day).isoformat()
            except ValueError:
                problems.append(f"{y}-{m:02d}: impossible day {day}")
                continue
            for concept, name, period, t in rel:
                events.append({"date": ds, "country": "Australia", "concept": concept,
                               "name": f"{name} ({period})", "source": SRC,
                               "time": f"{t} Canberra time"})
    return events, problems


def sample(markup: str) -> str:
    busy = [c for r in rows_of(markup) for c in r if len(c) > 20][:2]
    return " || ".join(x[:200] for x in busy) or re.sub(r"\s+", " ", markup[:300])


def main() -> int:
    today = datetime.now(timezone.utc).date()
    s = requests.Session()
    s.headers.update(UA)
    events, problems, loaded = [], [], 0
    for i, (y, m) in enumerate(month_list(today, MONTHS_AHEAD)):
        try:
            r = s.get(URL.format(ym=f"{y}{m:02d}"), timeout=40)
            r.raise_for_status()
        except requests.RequestException as e:
            if i < MUST_LOAD:
                problems.append(f"{y}-{m:02d}: {type(e).__name__}: {e}")
            continue
        page = r.content.decode("utf-8", "replace")
        ev, pr = parse_month(page, y, m)
        if pr and i < MUST_LOAD:
            problems.extend(pr)
            print(f"  sample {y}-{m:02d}: {sample(page)}", file=sys.stderr)
        loaded += 1
        events.extend(ev)
    if not any(e["concept"] == "cpi" for e in events):
        problems.append("no Consumer Price Index release found")
    if not any(e["concept"] == "jobs" for e in events):
        problems.append("no Labour Force release found")
    if problems:
        for p in problems:
            print(f"ERROR {p}", file=sys.stderr)
        print(f"Not writing ({loaded} pages read, {len(events)} events parsed); existing file kept.",
              file=sys.stderr)
        return 1
    t0 = today.isoformat()
    events = sorted({(e["date"], e["concept"]): e for e in events if e["date"] >= t0}.values(),
                    key=lambda e: (e["date"], e["concept"]))
    if not events:
        print("ERROR: zero upcoming Australia releases; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Australia",
                   "events": events}, f, indent=2)
    kinds = {}
    for e in events:
        kinds[e["concept"]] = kinds.get(e["concept"], 0) + 1
    print(f"Wrote {len(events)} Australia calendar events "
          f"({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
