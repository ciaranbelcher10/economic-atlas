"""MAS (Singapore) Monetary Policy Statement dates -> data-calendar-sg.json.

Run:  python3 fetch_calendar_sg.py

v1.9.59, new. Read from the MAS Advance Release Calendar. Its "Monetary Policy Statement"
block is followed by a long blackout note, the frequency ("Quarterly"), then one or more
pairs: a date line and a "Statement for <Mon YYYY>" line. MAS often gives the date as
"NLT 29 Jan 2027" (no later than), so the event name says so and no time is given: the
site shows the date as the latest day, never as a confirmed day.

If the page cannot be read, fails a check, or leaves no upcoming date, the existing
data-calendar-sg.json (if any) is left as it is and a "WARNING MAS: ..." line is printed.
The run never fails the workflow.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone

import requests

from calendar_common import UA, page_lines

URL = "https://www.mas.gov.sg/monetary-policy/advance-release-calendar"
OUT = "data-calendar-sg.json"
NAME = "MAS Monetary Policy Statement"
NAME_NLT = "MAS Monetary Policy Statement (no later than this date)"
SRC = "mas.gov.sg Advance Release Calendar"
MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DATE_RE = re.compile(r"(NLT )?(\d{1,2}) (" + "|".join(MON[1:]) + r") (\d{4})")


def parse(markup: str) -> tuple[list[dict], list[str]]:
    lines = page_lines(markup)
    try:
        start = next(i for i, l in enumerate(lines)
                     if l == "Monetary Policy Statement" and i + 2 < len(lines) and lines[i + 2] == "Quarterly")
    except StopIteration:
        return [], ["no 'Monetary Policy Statement ... Quarterly' block (bot wall or a changed page?)"]
    events, problems, i = [], [], start + 3
    while i + 1 < len(lines):
        m = DATE_RE.fullmatch(lines[i])
        if not m:
            break
        if not re.fullmatch(r"Statement for (" + "|".join(MON[1:]) + r") \d{4}", lines[i + 1]):
            problems.append(f"date {lines[i]!r} is not followed by 'Statement for <Mon YYYY>': {lines[i + 1]!r}")
            break
        try:
            d = date(int(m.group(4)), MON.index(m.group(3)), int(m.group(2)))
        except ValueError:
            problems.append(f"impossible date {lines[i]!r}")
            break
        events.append({"date": d.isoformat(), "country": "Singapore", "concept": "rate_decision",
                       "name": NAME_NLT if m.group(1) else NAME, "source": SRC, "time": None})
        i += 2
    if not events and not problems:
        problems.append(f"no date under the Monetary Policy Statement heading (next line: {lines[start + 3:start + 4]})")
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
            raise ValueError("no upcoming statement date")
    except Exception as e:
        print(f"WARNING MAS: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Singapore", "events": ev}, f, indent=2)
    print(f"MAS: wrote {len(ev)} upcoming statement dates (next {ev[0]['date']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
