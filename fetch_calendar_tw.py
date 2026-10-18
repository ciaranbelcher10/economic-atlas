"""Fetch Taiwan's official release dates and write data-calendar-tw.json (v1.8.16).

One official source: the National Statistics (DGBAS) advance release calendar,
eng.stat.gov.tw/News_NoticeCalendar_EN.aspx?n=4011. The table is drawn by Vue from an
embedded variable, `VueData = {"list":[{"name","category","timedatas",...}], "year", "month", ...}`.
Each indicator's `timedatas` holds 12 months, the first being VueData's own year and
month (probe of 19 Oct 2026: the default view was year 2026, month 10; asking for
month 11 moved every list along by one, and year 2027 started in January). Each month
is a list of {"date": "23", "time": "16:00", "notice": "(Sep 2026)"}: the day of the
release, its time (Taiwan time) and the reference period it covers. A day written
"NLT 30" means "not later than the 30th", which is how DGBAS dates its full GDP
release; those events say so in their name.

The page lists ten indicators at a time (the site's own links add &page=N&PageSize=10),
so pages are read until one adds nothing new. Served: the Manpower Survey (jobs), the
advance GDP estimate and the full GDP release (gdp), and any consumer price index entry
(cpi). The rest are counted and their names printed for the Actions log.

Not served: Central Bank of the Republic of China rate decisions. Its English pages
redirect to a Chinese page of operations notices with no board-meeting schedule
(probe of 19 Oct 2026), so none is guessed.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date

import requests
import urllib3

from calendar_common import clean_name, run_single

OUT = "data-calendar-tw.json"
URL = "https://eng.stat.gov.tw/News_NoticeCalendar_EN.aspx?n=4011&sms=0&page={p}&PageSize=10"
SRC = "eng.stat.gov.tw advance release calendar (official DGBAS release calendar)"
MAX_PAGES = 8
DAY_RE = re.compile(r"^(NLT)?\s*(\d{1,2})$", re.I)


def classify(name: str) -> tuple[str, str] | None:
    n = name.strip().lower()
    if n.startswith(("labor force", "labour force")):
        return "jobs", "Manpower survey: unemployment rate"
    if n.startswith("advance gdp"):
        return "gdp", "Advance GDP estimate"
    if n.startswith("gross domestic product"):
        return "gdp", "GDP, national income and deflator"
    if "consumer price" in n:
        return "cpi", "Consumer price index"
    return None


def vue_data(page: str) -> dict | None:
    m = re.search(r"VueData\s*=\s*", page)
    if not m:
        return None
    try:
        return json.JSONDecoder().raw_decode(page, m.end())[0]
    except ValueError:
        return None


def clock(t: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", (t or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), m.group(2)
    return f"{(h % 12) or 12}:{mi}{'pm' if h >= 12 else 'am'} Taiwan time"


def parse(page: str) -> tuple[list[dict], list[str], list[str]]:
    """(events, problems, names of the indicators on this page)."""
    d = vue_data(page)
    if d is None or not isinstance(d.get("list"), list):
        return [], ["no VueData calendar list in the page (bot wall or a changed page?)"], []
    try:
        y0, m0 = int(d["year"]), int(d["month"])
    except (KeyError, TypeError, ValueError):
        return [], ["VueData has no year/month, so the months cannot be placed"], []
    events, problems, names = [], [], []
    for it in d["list"]:
        name = str(it.get("name", "")).strip()
        names.append(name)
        kind = classify(name)
        if kind is None:
            continue
        concept, label = kind
        td = it.get("timedatas") or []
        if len(td) > 12:
            problems.append(f"{name[:40]}: {len(td)} months listed, expected 12 or fewer")
            continue
        for i, entries in enumerate(td):
            y, mo = y0 + (m0 - 1 + i) // 12, (m0 - 1 + i) % 12 + 1
            for e in entries:
                m = DAY_RE.match(str(e.get("date", "")).strip())
                if not m:
                    problems.append(f"{name[:40]}: day {e.get('date')!r} is not a day number")
                    continue
                try:
                    d_ = date(y, mo, int(m.group(2)))
                except ValueError:
                    problems.append(f"{name[:40]}: {y}-{mo:02d}-{m.group(2)} is not a date")
                    continue
                note = str(e.get("notice", "")).strip()
                text = f"{label} {note}".strip() + (" (published by this date at the latest)" if m.group(1) else "")
                events.append({"date": d_.isoformat(), "country": "Taiwan", "concept": concept,
                               "name": clean_name(text), "source": SRC, "time": clock(e.get("time", ""))})
    return events, problems, names


# CONFIRMED on the first Actions run (2026-10-18): eng.stat.gov.tw does not send its
# intermediate certificate, so the runner rejects it ("unable to get local issuer
# certificate"); every Taiwanese government page in the 18-19 Oct probes needed the same.
# The site is not self-signed, it is just missing the link to a root that the runner's
# certificate bundle lacks. Same shape as the MoSPI exception in fetch_in.py: a normal
# verified request is always tried first, verification is switched off only after that
# fails with an SSL error, only for this one host (URL above), and the log says so on every
# run. The page is then accepted only if it parses to the expected calendar structure
# (a VueData list with 12-month entries and a labor force indicator).
def fetch_events(s, today: str) -> list[dict]:
    events, seen_names, unserved = [], set(), []
    verify = True
    for p in range(1, MAX_PAGES + 1):
        try:
            r = s.get(URL.format(p=p), timeout=60, verify=verify)
        except requests.exceptions.SSLError:
            if not verify:
                raise
            verify = False
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            print("note Taiwan: eng.stat.gov.tw certificate chain does not verify on this runner "
                  "(missing intermediate); reading this one host with verification off")
            r = s.get(URL.format(p=p), timeout=60, verify=False)
        r.raise_for_status()
        ev, problems, names = parse(r.text)
        if problems:
            raise ValueError("; ".join(problems))
        new = [n for n in names if n not in seen_names]
        if not new:
            break
        seen_names.update(new)
        events += ev
        unserved += [n for n in new if classify(n) is None]
    if not any(e["concept"] == "jobs" for e in events):
        raise ValueError("no Manpower Survey (labor force) entry found among the indicators")
    if unserved:
        print(f"note Taiwan: {len(unserved)} of {len(seen_names)} indicators not served: "
              + "; ".join(sorted({n[:60] for n in unserved})))
    return events


def main() -> int:
    return run_single(OUT, "Taiwan", fetch_events, "Taiwan")


if __name__ == "__main__":
    sys.exit(main())
