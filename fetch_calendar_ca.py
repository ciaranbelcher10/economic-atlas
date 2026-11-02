"""Bank of Canada interest rate announcement dates -> data-calendar-ca.json.

Run:  python3 fetch_calendar_ca.py

v1.9.59: read live from the Bank's key interest rate page, replacing the hand-typed 2026
list. That page has one table per year, captioned "Schedule for <year>", each row a date
("January 28", "March&nbsp;3") and its publications ("Interest rate announcement" with or
without the Monetary Policy Report). Only rows naming an interest rate announcement are used.

The time comes from the Bank's upcoming-events page ("Interest Rate Announcement" followed
by "09:45 (ET)"). If that page cannot be read, the dates still go on without a time.

If the schedule page cannot be read, fails a check, or leaves no upcoming date, the existing
data-calendar-ca.json is left as it is and a "WARNING BoC: ..." line is printed. The run
never fails the workflow.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone

import requests

from calendar_common import UA, page_lines

URL = "https://www.bankofcanada.ca/core-functions/monetary-policy/key-interest-rate/"
TIME_URL = "https://www.bankofcanada.ca/press/upcoming-events/"
OUT = "data-calendar-ca.json"
NAME = "Bank of Canada interest rate announcement"
SRC = "bankofcanada.ca key interest rate page, published announcement schedule"
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def cell(c: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")).strip()


def boc_time(markup: str) -> str:
    """'9:45am ET' from the upcoming-events page, or '' if it is not there."""
    lines = page_lines(markup)
    for i, l in enumerate(lines):
        if re.fullmatch(r"Interest Rate Announcement", l, re.I):
            m = re.match(r"(\d{1,2}):(\d{2}) \(ET\)", " ".join(lines[i + 1:i + 2]))
            if m:
                h, mi = int(m.group(1)), m.group(2)
                return f"{h % 12 or 12}:{mi}{'am' if h < 12 else 'pm'} ET"
    return ""


def parse(markup: str, time_label: str = "") -> tuple[list[dict], list[str]]:
    tables = re.findall(r"<table[\s\S]*?</table>", markup, re.I)
    years = []
    for t in tables:
        cap = re.search(r"<caption[^>]*>([\s\S]*?)</caption>", t, re.I)
        m = re.fullmatch(r"Schedule for (\d{4})", cell(cap.group(1))) if cap else None
        if m:
            years.append((int(m.group(1)), t))
    if not years:
        return [], ["no 'Schedule for <year>' table (bot wall or a changed page?)"]
    events, problems = [], []
    for y, t in years:
        n = 0
        for row in re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", t, re.I):
            tds = [cell(c) for c in re.findall(r"<td[^>]*>([\s\S]*?)</td>", row, re.I)]
            if len(tds) < 2 or "interest rate announcement" not in tds[1].lower():
                continue
            m = re.fullmatch(r"(" + "|".join(MONTHS[1:]) + r") (\d{1,2})", tds[0])
            if not m:
                problems.append(f"{y}: date cell not read: {tds[0]!r}")
                continue
            try:
                d = date(y, MONTHS.index(m.group(1)), int(m.group(2)))
            except ValueError:
                problems.append(f"{y}: impossible date {tds[0]!r}")
                continue
            n += 1
            ev = {"date": d.isoformat(), "country": "Canada", "concept": "rate_decision", "name": NAME, "source": SRC}
            if time_label:
                ev["time"] = time_label
            events.append(ev)
        if not 6 <= n <= 10:
            problems.append(f"{y}: {n} announcements; the Bank holds 8 a year")
    return events, problems


def main() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        s = requests.Session()
        s.headers.update(UA)
        r = s.get(URL, timeout=40)
        r.raise_for_status()
        page = r.content.decode("utf-8", "replace")
        try:
            t = s.get(TIME_URL, timeout=40)
            label = boc_time(t.content.decode("utf-8", "replace")) if t.status_code == 200 else ""
        except requests.RequestException:
            label = ""
        ev, pr = parse(page, label)
        if pr:
            raise ValueError("; ".join(pr[:3]) + f" | sample: {re.sub(r'\s+', ' ', page[:200])}")
        ev = [e for e in ev if e["date"] >= today]
        if not ev:
            raise ValueError("no upcoming announcement date")
    except Exception as e:
        print(f"WARNING BoC: {type(e).__name__}: {str(e)[:300]}; existing {OUT} kept", file=sys.stderr)
        return 0
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Canada", "events": ev}, f, indent=2)
    note = "" if label else " (time not found on the upcoming-events page; dates only)"
    print(f"BoC: wrote {len(ev)} upcoming announcements (next {ev[0]['date']}){note}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
