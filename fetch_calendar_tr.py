"""CBRT (Turkey) Monetary Policy Committee decision dates -> data-calendar-tr.json.

Run:  python3 fetch_calendar_tr.py

v1.9.59: read live from the CBRT's own calendar page, replacing the hand-typed 2026 list.
The page has one table, "MONETARY POLICY COMMITTEE MEETING AND REPORTS CALENDAR", with four
columns: MPC Decision, Summary of the MPC Meeting, Inflation Report, Financial Stability
Report. Only the first column is a rate decision; the other three are publications and are
left out. Blank cells are "&nbsp;", so cells are read by position, never by collecting every
date on the page.

The page does not state a time. Decisions are announced at 14:00 Turkey time on the meeting
day (the CBRT's standing practice, kept from the previous script).

If the page cannot be read, fails a check, or leaves no upcoming date, the existing
data-calendar-tr.json is left as it is (its dates stay on the site) and a
"WARNING CBRT: ..." line is printed. The run never fails the workflow.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone

import requests

from calendar_common import UA

URL = "https://www.tcmb.gov.tr/wps/wcm/connect/EN/TCMB+EN/Main+Menu/Announcements/Calendar"
OUT = "data-calendar-tr.json"
NAME = "CBRT Monetary Policy Committee decision"
SRC = "tcmb.gov.tr Monetary Policy Committee Meeting and Reports Calendar"
TIME = "2:00pm TRT"
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def cell(c: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).replace("\xa0", " ").strip()


def parse(markup: str) -> tuple[list[dict], list[str]]:
    """Decision dates from the first column of the MPC calendar table, and problems."""
    m = re.search(r"MONETARY POLICY COMMITTEE MEETING AND REPORTS CALENDAR[\s\S]*?(<table[\s\S]*?</table>)", markup, re.I)
    if not m:
        return [], ["no 'Monetary Policy Committee Meeting and Reports Calendar' table (bot wall or a changed page?)"]
    t = m.group(1)
    head = re.search(r"<thead[\s\S]*?</thead>", t, re.I)
    cols = [cell(c) for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", head.group(0) if head else "", re.I)]
    if not cols or cols[0] != "Monetary Policy Committee Decision":
        return [], [f"first column is {cols[:1]}, not 'Monetary Policy Committee Decision'"]
    body = re.search(r"<tbody[\s\S]*?</tbody>", t, re.I)
    events, problems, per_year = [], [], {}
    for row in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", body.group(0) if body else "", re.I):
        tds = [cell(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)]
        if not tds or not tds[0]:
            continue
        d = re.fullmatch(r"(" + "|".join(MONTHS[1:]) + r") (\d{1,2}), (\d{4})", tds[0])
        if not d:
            problems.append(f"decision cell not read: {tds[0]!r}")
            continue
        try:
            day = date(int(d.group(3)), MONTHS.index(d.group(1)), int(d.group(2)))
        except ValueError:
            problems.append(f"impossible date {tds[0]!r}")
            continue
        per_year[day.year] = per_year.get(day.year, 0) + 1
        events.append({"date": day.isoformat(), "country": "Turkey", "concept": "rate_decision",
                       "name": NAME, "source": SRC, "time": TIME})
    if not events and not problems:
        problems.append("the table has no decision dates")
    dates = [e["date"] for e in events]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        problems.append("decision dates are out of order or repeated")
    for y, n in per_year.items():
        if n > 12:
            problems.append(f"{y}: {n} decisions; the CBRT holds 8 a year")
    return events, problems


def main() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        r = requests.get(URL, headers=UA, timeout=40)
        r.raise_for_status()
        page = r.content.decode("utf-8", "replace")
        ev, pr = parse(page)
        if pr:
            raise ValueError("; ".join(pr[:3]) + f" | sample: {re.sub(r'\s+', ' ', page[:200])}")
        ev = [e for e in ev if e["date"] >= today]
        if not ev:
            raise ValueError("no upcoming decision date in the table")
    except Exception as e:
        print(f"WARNING CBRT: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Turkey", "events": ev}, f, indent=2)
    print(f"CBRT: wrote {len(ev)} upcoming decisions (next {ev[0]['date']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
