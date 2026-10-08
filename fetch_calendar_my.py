"""Fetch Malaysia's official release dates and write data-calendar-my.json.

Two official sources, merged:
  - BNM: "Schedule of Monetary Policy Decisions and Statements for <year>",
    a table in each November Monetary Policy Statement (statement at 3:00pm
    MYT). The URL of the statement holding next year's schedule follows from
    this year's last meeting date (monetary-policy-statement-DDMMYYYY), so the
    chain moves on each year without editing. Every row's weekday must match
    its date ("5 November 2026 (Thursday)"), or the run fails.
  - OpenDOSM publications calendar (open.dosm.gov.my/publications/upcoming),
    the DOSM release calendar for the current month. The portal pages at
    dosm.gov.my returned 500 in the probe of 8 Oct 2026; OpenDOSM is DOSM's
    own open-data site.
Served: rate_decision (BNM), cpi, gdp (advance and full GDP), jobs (Labour
Force Survey), trade (External Trade, headline and full), ppi.
If one source fails, its previously published upcoming events are carried
forward (and the log says so); if both fail, or nothing parses, the existing
file is left untouched. Built v1.7.30; OpenDOSM read from its embedded JSON (cal_pubs) from v1.7.32,
with the rendered grid as a fallback.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

OUT = "data-calendar-my.json"
BNM_SEED = "https://www.bnm.gov.my/-/monetary-policy-statement-06112025"   # holds the 2026 schedule
BNM_URL = "https://www.bnm.gov.my/-/monetary-policy-statement-{d:%d%m%Y}"
DOSM_URL = "https://open.dosm.gov.my/publications/upcoming"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BNM_ROW_RE = re.compile(r"(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4}) \((\w+day)\)")
BNM_SRC = "bnm.gov.my Monetary Policy Statement: Schedule of Monetary Policy Decisions and Statements (official)"
DOSM_SRC = "open.dosm.gov.my publications calendar (official DOSM release calendar)"

# OpenDOSM pill title (before the colon) -> concept, event name
DOSM_TITLES = {
    "Consumer Price Index": ("cpi", "Consumer Price Index"),
    "Advance Gross Domestic Product": ("gdp", "Advance GDP estimate"),
    "Gross Domestic Product": ("gdp", "GDP"),
    "Labour Force Survey": ("jobs", "Labour Force Survey"),
    "External Trade (Headline)": ("trade", "External trade (headline)"),
    "External Trade": ("trade", "External trade"),
    "Producer Price Index": ("ppi", "Producer Price Index"),
}
MONTH_LABEL_RE = re.compile(r">(" + "|".join(MONTHS) + r") (20\d\d)<")
TOKEN_RE = re.compile(r'<span class="([^"]*)">\s*(\d{1,2})\s*</span>|<p class="h-6 w-full truncate[^"]*">([^<]+)</p>')


def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>|\s+", " ", s)).strip()


def parse_bnm(page: str) -> tuple[list[date], list[str]]:
    """Meeting dates from a statement's schedule table, and problems."""
    i = page.find("Schedule of Monetary Policy Decisions and Statements")
    if i < 0:
        return [], []                     # this statement carries no schedule
    table = re.search(r"<table.*?</table>", page[i:], re.S | re.I)
    if not table:
        return [], ["schedule heading without a table"]
    dates, problems = [], []
    for day, month, year, wd in BNM_ROW_RE.findall(text(table.group(0))):
        d = date(int(year), MONTHS.index(month) + 1, int(day))
        if WEEKDAYS[d.weekday()] != wd:
            problems.append(f"BNM {d}: table says {wd}, the date is a {WEEKDAYS[d.weekday()]}")
        else:
            dates.append(d)
    if not dates and not problems:
        problems.append("schedule table has no dated rows")
    return dates, problems


def parse_dosm(page: str) -> tuple[list[dict], list[str]]:
    """Releases in OpenDOSM's month grid. Dim day numbers belong to the
    neighbouring months: before the 1st, the previous month; after, the next."""
    # Normalise the way React serves the page: <!-- --> markers inside text
    # nodes and runs of whitespace (the v1.7.30 fixture had both removed, so
    # the live page did not match; fixed v1.7.31).
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    page = re.sub(r"\s+", " ", page)
    m = MONTH_LABEL_RE.search(html.unescape(page))
    if not m:
        return [], ["no month label (e.g. 'October 2026') found"]
    month, year = MONTHS.index(m.group(1)) + 1, int(m.group(2))
    events, cur, seen_first = [], None, False
    for cls, day, title in TOKEN_RE.findall(page):
        if day:
            dim = "text-dim" in cls
            if not dim:
                seen_first = True
                cur = date(year, month, int(day))
            else:
                y, mo = (year, month - 1) if not seen_first else (year, month + 1)
                if mo == 0: y, mo = y - 1, 12
                if mo == 13: y, mo = y + 1, 1
                try:
                    cur = date(y, mo, int(day))
                except ValueError:
                    cur = None
            continue
        if cur is None:
            continue
        title = html.unescape(title).strip()
        head, _, period = title.partition(":")
        if head.strip() in DOSM_TITLES:
            concept, name = DOSM_TITLES[head.strip()]
            events.append({"date": cur.isoformat(), "country": "Malaysia", "concept": concept,
                           "name": f"{name} ({period.strip()})" if period.strip() else name,
                           "source": DOSM_SRC, "time": None})
    if not seen_first:
        return [], ["no day cells for the labelled month"]
    return events, []


NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def parse_dosm_json(page: str) -> tuple[list[dict] | None, list[str]]:
    """Releases from OpenDOSM's embedded page data (pageProps.cal_pubs, a
    {"YYYY-MM-DD": ["Title: period", ...]} map; v1.7.32). Returns (None, [])
    when the page carries no such data, so the caller can fall back to the grid."""
    m = NEXT_DATA_RE.search(page)
    if not m:
        return None, []
    try:
        cal = json.loads(m.group(1))["props"]["pageProps"]["cal_pubs"]
    except (ValueError, KeyError, TypeError):
        return None, []
    events, problems = [], []
    for day, titles in cal.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            problems.append(f"cal_pubs key is not a date: {day!r}")
            continue
        for title in titles:
            head, _, period = str(title).partition(":")
            if head.strip() in DOSM_TITLES:
                concept, name = DOSM_TITLES[head.strip()]
                events.append({"date": day, "country": "Malaysia", "concept": concept,
                               "name": f"{name} ({period.strip()})" if period.strip() else name,
                               "source": DOSM_SRC, "time": None})
    if not cal:
        problems.append("cal_pubs is empty")
    return events, problems


def fetch(s, url):
    r = s.get(url, timeout=40)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content.decode("utf-8", "replace")


def bnm_events(s, today) -> list[dict]:
    """Follow the chain of November statements from the seed; raise on failure."""
    url, all_dates, hops = BNM_SEED, [], 0
    while url and hops < 6:
        page = fetch(s, url)
        if page is None:
            break                          # next statement not published yet
        dates, problems = parse_bnm(page)
        if problems:
            raise ValueError("; ".join(problems))
        if not dates:
            break
        all_dates += dates
        url, hops = BNM_URL.format(d=max(dates)), hops + 1
    if not all_dates:
        raise ValueError("no BNM schedule found from the seed statement")
    return [{"date": d.isoformat(), "country": "Malaysia", "concept": "rate_decision",
             "name": "Bank Negara Malaysia OPR decision (Monetary Policy Statement)",
             "source": BNM_SRC, "time": "3:00pm MYT"} for d in sorted(set(all_dates)) if d >= today]


def main() -> int:
    s = requests.Session()
    s.headers.update(UA)
    today = datetime.now(timezone.utc).date()
    prev = []
    if Path(OUT).exists():
        try:
            prev = json.loads(Path(OUT).read_text()).get("events", [])
        except ValueError:
            prev = []
    events, failed = [], []
    try:
        events += bnm_events(s, today)
    except (requests.RequestException, ValueError) as e:
        failed.append("BNM")
        print(f"WARNING BNM: {e}; carrying forward previous BNM events", file=sys.stderr)
        events += [e for e in prev if e.get("source") == BNM_SRC and e["date"] >= today.isoformat()]
    try:
        page = fetch(s, DOSM_URL)
        if page is None:
            raise ValueError("OpenDOSM calendar returned 404")
        ev, problems = parse_dosm_json(page)
        if ev is None:                    # no embedded data: read the rendered grid
            ev, problems = parse_dosm(page)
        if problems:
            raise ValueError("; ".join(problems))
        fresh = [e for e in ev if e["date"] >= today.isoformat()]
        # The grid shows one month: keep previously published later-month DOSM events too.
        shown = {e["date"][:7] for e in ev}
        events += fresh + [e for e in prev if e.get("source") == DOSM_SRC
                           and e["date"] >= today.isoformat() and e["date"][:7] not in shown]
    except (requests.RequestException, ValueError) as e:
        failed.append("OpenDOSM")
        print(f"WARNING OpenDOSM: {e}; carrying forward previous DOSM events", file=sys.stderr)
        events += [e for e in prev if e.get("source") == DOSM_SRC and e["date"] >= today.isoformat()]
    if len(failed) == 2:
        print("ERROR: both sources failed; existing file kept.", file=sys.stderr)
        return 1
    events = sorted({(e["date"], e["concept"], e["name"]): e for e in events}.values(),
                    key=lambda e: (e["date"], e["concept"], e["name"]))
    if not events:
        print("ERROR: zero upcoming Malaysia events; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Malaysia",
                   "events": events}, f, indent=2)
    print(f"Wrote {len(events)} Malaysia calendar events" + (f" ({', '.join(failed)} carried forward)" if failed else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
