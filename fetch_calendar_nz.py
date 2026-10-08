"""Fetch New Zealand's official release dates and write data-calendar-nz.json.

Source: Stats NZ's release calendar export, an iCal file of every scheduled
release (https://www.stats.govt.nz/release-calendar/calendar-export, about
150 events, all at 10:45am New Zealand time). Found by the probes of 8 Oct
2026; the HTML calendar page only holds the "Other" information-release table.

Served (by the release title before the colon):
  cpi   Consumers price index (quarterly)
  gdp   Gross domestic product (quarterly)
  jobs  Labour market statistics (quarterly: unemployment, employment)
  trade Overseas merchandise trade (monthly)
  ppi   Business price indexes (quarterly: PPI)
Not served: RBNZ OCR decisions. The RBNZ's pages are Cloudflare-blocked to
scripts and its news feed does not carry the decision schedule, so the dates
are not on the calendar rather than hand-entered.

Integrity: the response must be an iCal file; every event's start must be in
Pacific/Auckland time; at least one CPI release must be scheduled. Otherwise,
or on any fetch error (Stats NZ sits behind Incapsula), the existing file is
left untouched. Built v1.7.32.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

import requests

URL = "https://www.stats.govt.nz/release-calendar/calendar-export"
OUT = "data-calendar-nz.json"
SRC = "stats.govt.nz release calendar export (official iCal, all scheduled releases)"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
TITLES = {
    "Consumers price index": ("cpi", "Consumers price index"),
    "Gross domestic product": ("gdp", "Gross domestic product"),
    "Labour market statistics": ("jobs", "Labour market statistics"),
    "Overseas merchandise trade": ("trade", "Overseas merchandise trade"),
    "Business price indexes": ("ppi", "Business price indexes"),
}
START_RE = re.compile(r"^DTSTART(?:;TZID=([^:;]+))?:(\d{8})T(\d{2})(\d{2})\d{2}$")


def unfold(ics: str) -> list[str]:
    """RFC 5545 lines: a line starting with a space or tab continues the previous one."""
    out = []
    for line in ics.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse(ics: str) -> tuple[list[dict], list[str]]:
    if "BEGIN:VCALENDAR" not in ics:
        return [], ["response is not an iCal file (bot wall or error page?)"]
    events, problems, cur = [], [], None
    for line in unfold(ics):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            summ, start = cur.get("summary", ""), cur.get("start")
            head, _, period = summ.partition(":")
            if head.strip() in TITLES and start:
                tz, ymd, hh, mm = start
                if tz != "Pacific/Auckland":
                    problems.append(f"{summ}: start not in Pacific/Auckland time ({tz})")
                else:
                    concept, name = TITLES[head.strip()]
                    h = int(hh)
                    time = f"{(h - 1) % 12 + 1}:{mm}{'am' if h < 12 else 'pm'} NZ time"
                    events.append({"date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}", "country": "New Zealand",
                                   "concept": concept, "name": f"{name} ({period.strip()})" if period.strip() else name,
                                   "source": SRC, "time": time})
            cur = None
        elif cur is not None:
            if line.startswith("SUMMARY"):
                cur["summary"] = line.split(":", 1)[1].strip()
            elif line.startswith("DTSTART"):
                m = START_RE.match(line)
                if m:
                    cur["start"] = m.groups()
                else:
                    problems.append(f"unreadable start line: {line}")
    if not any(e["concept"] == "cpi" for e in events):
        problems.append("no Consumers price index release in the export")
    return events, problems


def main() -> int:
    try:
        r = requests.get(URL, timeout=40, headers=UA)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching Stats NZ calendar export: {e}; existing file kept.", file=sys.stderr)
        return 1
    events, problems = parse(r.content.decode("utf-8", "replace"))
    if problems:
        for p in problems:
            print(f"ERROR {p}", file=sys.stderr)
        print("Not writing: the export did not parse cleanly; existing file kept.", file=sys.stderr)
        return 1
    today = datetime.now(timezone.utc).date().isoformat()
    events = sorted({(e["date"], e["concept"]): e for e in events if e["date"] >= today}.values(),
                    key=lambda e: (e["date"], e["concept"]))
    if not events:
        print("ERROR: zero upcoming New Zealand releases; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "New Zealand",
                   "events": events}, f, indent=2)
    print(f"Wrote {len(events)} New Zealand calendar events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
