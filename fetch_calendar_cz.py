"""Fetch Czechia's official release dates and write data-calendar-cz.json.

Two official sources, merged (as Malaysia's calendar):
  - CNB: the Bank Board page (cnb.cz/en/about_cnb/bank-board/) lists the
    year's Bank Board meetings in a table; monetary policy meetings are
    labelled "Bank Board meeting on monetary policy". The CNB publishes each
    decision at 2.30 p.m. Prague time (CNB notice of the 2026 meeting dates).
    The page is stable across years; the yearly news items change slug when
    updated, so they are not used.
  - CZSO: the events API behind csu.gov.cz/calendar-of-events
    (/api/web-externi/udalosti, category rychle-informace = news releases),
    found in the page's widget bundle on 8 Oct 2026. Public, no token, JSON;
    every news release is at 9:00 a.m. Prague time.
Served: rate_decision (CNB); cpi (CPI and the CPI flash estimate), gdp
(preliminary estimate and resources and uses), jobs (rates of employment,
unemployment and economic activity), trade (international trade in goods,
change of ownership), ppi (producer price indices). Not served: other CZSO
releases (retail, industry, fiscal notifications), as on other calendars.

Integrity: CNB rows must be real dates on weekdays; CZSO events must carry
the news-release category, a +01:00 or +02:00 offset (Prague), and at least
one CPI release must be found. If one source fails, its previously published
upcoming events are carried forward (and the log says so); if both fail, or
nothing parses, the existing file is left untouched. Built v1.7.33.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

OUT = "data-calendar-cz.json"
CNB_URL = "https://www.cnb.cz/en/about_cnb/bank-board/"
CZSO_URL = ("https://csu.gov.cz/api/web-externi/udalosti?datumOd={start}&pocetDni={days}"
            "&webKod=produkty,statistika,rychle-informace&kodJazyk=en&kategorieKod=rychle-informace")
CZSO_DAYS = 120
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "en"}
CNB_SRC = "cnb.cz Bank Board meeting schedule (official)"
CZSO_SRC = "csu.gov.cz calendar of events, news releases (official CZSO release calendar)"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
CNB_ROW_RE = re.compile(r"<td[^>]*>\s*(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})\s*</td>\s*<td[^>]*>(.*?)</td>",
                        re.S | re.I)

# CZSO title, normalised to lower-case words, by prefix -> concept, event name
CZSO_TITLES = [
    ("flash estimate of cpi", "cpi", "CPI flash estimate"),
    ("consumer price indices inflation", "cpi", "Consumer price indices"),
    ("gdp preliminary estimate", "gdp", "GDP preliminary estimate"),
    ("gdp resources and uses", "gdp", "GDP resources and uses"),
    ("rates of employment unemployment and economic activity", "jobs", "Rates of employment and unemployment"),
    ("international trade in goods change of ownership", "trade", "International trade in goods"),
    ("producer price indices", "ppi", "Producer price indices"),
]


def norm(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def period_of(title: str) -> str:
    """The text after the last ' - ' (CZSO puts the reference period there)."""
    parts = re.split(r"\s+-\s+|\s+-(?=\S)", title.strip())
    return parts[-1].strip() if len(parts) > 1 else ""


def parse_cnb(page: str) -> tuple[list[dict], list[str]]:
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    events, problems, rows = [], [], 0
    for d, mon, y, agenda in CNB_ROW_RE.findall(page):
        rows += 1
        try:
            day = date(int(y), MONTHS.index(mon) + 1, int(d))
        except ValueError:
            problems.append(f"impossible date {d} {mon} {y}")
            continue
        text = re.sub(r"<[^>]+>|\s+", " ", html.unescape(agenda)).strip()
        if "monetary policy" not in text.lower():
            continue
        if day.weekday() > 4:
            problems.append(f"{day} ({day:%A}) is not a weekday")
            continue
        events.append({"date": day.isoformat(), "country": "Czechia", "concept": "rate_decision",
                       "name": "CNB Bank Board monetary policy decision", "source": CNB_SRC,
                       "time": "2:30pm Prague time"})
    if rows == 0:
        problems.append("no Bank Board meeting table found on the page")
    elif not events:
        problems.append("no monetary policy meeting in the Bank Board table")
    per_year = {}
    for e in events:
        per_year[e["date"][:4]] = per_year.get(e["date"][:4], 0) + 1
    for y, n in per_year.items():
        if n > 12:
            problems.append(f"{n} monetary policy meetings in {y}: not a schedule the CNB keeps")
    return events, problems


def parse_czso(payload) -> tuple[list[dict], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("seznam"), list):
        return [], ["CZSO response is not the events list (shape changed or error page?)"]
    events, problems = [], []
    for day in payload["seznam"]:
        for ev in day.get("udalosti") or []:
            title = ev.get("nazev") or ""
            n = norm(title)
            hit = next((t for t in CZSO_TITLES if n.startswith(t[0])), None)
            if not hit:
                continue
            kods = {k.get("kod") for k in ev.get("kategorie") or []}
            if "rychle-informace" not in kods:
                problems.append(f"{title}: not in the news-release category ({sorted(kods)})")
                continue
            m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):\d{2}([+-]\d{2}:\d{2})", ev.get("zacatek") or "")
            if not m:
                problems.append(f"{title}: unreadable start {ev.get('zacatek')!r}")
                continue
            ymd, hh, mm, off = m.groups()
            if off not in ("+01:00", "+02:00"):
                problems.append(f"{title}: start not in Prague time ({off})")
                continue
            h = int(hh)
            period = period_of(title)
            _, concept, name = hit
            events.append({"date": ymd, "country": "Czechia", "concept": concept,
                           "name": f"{name} ({period})" if period else name, "source": CZSO_SRC,
                           "time": f"{(h - 1) % 12 + 1}:{mm}{'am' if h < 12 else 'pm'} Prague time"})
    if not any(e["concept"] == "cpi" for e in events):
        problems.append("no consumer price release in the CZSO calendar")
    return events, problems


def main(today: date | None = None, get=None) -> int:
    get = get or requests.get
    today = today or datetime.now(timezone.utc).date()
    prev = []
    if Path(OUT).exists():
        try:
            prev = json.loads(Path(OUT).read_text()).get("events", [])
        except ValueError:
            prev = []
    events, failed = [], []
    try:
        r = get(CNB_URL, timeout=40, headers=UA)
        r.raise_for_status()
        ev, problems = parse_cnb(r.content.decode("utf-8", "replace"))
        if problems:
            raise ValueError("; ".join(problems))
        events += [e for e in ev if e["date"] >= today.isoformat()]
    except (requests.RequestException, ValueError) as e:
        failed.append("CNB")
        print(f"WARNING CNB: {e}; carrying forward previous CNB events", file=sys.stderr)
        events += [e for e in prev if e.get("source") == CNB_SRC and e["date"] >= today.isoformat()]
    try:
        r = get(CZSO_URL.format(start=today.isoformat(), days=CZSO_DAYS), timeout=40,
                headers=dict(UA, Accept="application/json"))
        r.raise_for_status()
        ev, problems = parse_czso(r.json())
        if problems:
            raise ValueError("; ".join(problems))
        events += [e for e in ev if e["date"] >= today.isoformat()]
    except (requests.RequestException, ValueError) as e:
        failed.append("CZSO")
        print(f"WARNING CZSO: {e}; carrying forward previous CZSO events", file=sys.stderr)
        events += [e for e in prev if e.get("source") == CZSO_SRC and e["date"] >= today.isoformat()]
    if len(failed) == 2:
        print("ERROR: both sources failed; existing file kept.", file=sys.stderr)
        return 1
    events = sorted({(e["date"], e["concept"], e["name"]): e for e in events}.values(),
                    key=lambda e: (e["date"], e["concept"], e["name"]))
    if not events:
        print("ERROR: zero upcoming Czechia events; existing file kept.", file=sys.stderr)
        return 1
    with open(OUT, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": "Czechia",
                   "events": events}, f, indent=2)
    print(f"Wrote {len(events)} Czechia calendar events" + (f" ({', '.join(failed)} carried forward)" if failed else "") + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
