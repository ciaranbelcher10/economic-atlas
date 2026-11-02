"""SBP (Pakistan) Monetary Policy Committee meeting dates -> data-calendar-pk.json.

Run:  python3 fetch_calendar_pk.py

v1.9.60, new. The SBP monetary policy page carries, in its plain HTML, a table headed
"Advance Calendar of Monetary Policy Committee (MPC) Meetings & Communications". Its first
column, "MPC Meeting Date", is the decision day (the Monetary Policy Statement is released
the same day). Dates are written "14-Dec-26". The other columns (analyst briefing, press
conference, minutes, report) are publications and are left out. The page gives no time.

If the page cannot be read, fails a check, or leaves no upcoming date, the existing
data-calendar-pk.json (if any) is left as it is and a "WARNING SBP: ..." line is printed.
The run never fails the workflow.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone

import requests

from calendar_common import UA

URL = "https://www.sbp.org.pk/our-operations/monetary-policy"
OUT = "data-calendar-pk.json"
NAME = "SBP Monetary Policy Committee decision"
SRC = "sbp.org.pk Advance Calendar of MPC Meetings"
MON = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def cell(c: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")).strip()


def parse(markup: str) -> tuple[list[dict], list[str]]:
    m = re.search(r"Advance Calendar of Monetary Policy Committee[\s\S]*?(<table[\s\S]*?</table>)", markup, re.I)
    if not m:
        return [], ["no 'Advance Calendar of Monetary Policy Committee' table (bot wall or a changed page?)"]
    t = m.group(1)
    head = re.search(r"<thead[\s\S]*?</thead>", t, re.I)
    cols = [cell(c) for c in re.findall(r"<th[^>]*>([\s\S]*?)</th>", head.group(0) if head else "", re.I)]
    if not cols or cols[0] != "MPC Meeting Date":
        return [], [f"first column is {cols[:1]}, not 'MPC Meeting Date'"]
    body = re.search(r"<tbody[\s\S]*?</tbody>", t, re.I)
    events, problems = [], []
    for row in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", body.group(0) if body else "", re.I):
        tds = [cell(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)]
        if not tds or not tds[0]:
            continue
        d = re.fullmatch(r"(\d{1,2})-(" + "|".join(MON[1:]) + r")-(\d{2})", tds[0])
        if not d:
            problems.append(f"meeting cell not read: {tds[0]!r}")
            continue
        try:
            day = date(2000 + int(d.group(3)), MON.index(d.group(2)), int(d.group(1)))
        except ValueError:
            problems.append(f"impossible date {tds[0]!r}")
            continue
        events.append({"date": day.isoformat(), "country": "Pakistan", "concept": "rate_decision",
                       "name": NAME, "source": SRC, "time": None})
    if not events and not problems:
        problems.append("the table has no meeting dates")
    dates = [e["date"] for e in events]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        problems.append("meeting dates are out of order or repeated")
    if len(events) > 12:
        problems.append(f"{len(events)} meetings in one advance calendar; the SBP lists about 8")
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
            raise ValueError("no upcoming meeting date in the table")
    except Exception as e:
        print(f"WARNING SBP: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Pakistan", "events": ev}, f, indent=2)
    print(f"SBP: wrote {len(ev)} upcoming decisions (next {ev[0]['date']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
