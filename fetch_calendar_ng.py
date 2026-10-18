"""Fetch Nigeria's official release dates and write data-calendar-ng.json (v1.8.14).

One official source: the National Bureau of Statistics homepage (nigerianstat.gov.ng),
whose release calendar is a fullcalendar widget fed by an embedded array
`[{"id":"819","title":"CPI and Inflation Report December 2025","start":"2026-01-15"}, ...]`
(about 170 entries for 2026 in the probe of 18 Oct 2026, plus years of past releases and one placeholder dated 1970; the first Actions run listed 826 titles that are not served, so the log now names only the upcoming ones).

Served: "CPI and Inflation Report ..." (cpi), GDP reports (gdp), foreign trade in goods
(trade) and labour force / unemployment reports (jobs). Weekly price watches, transport
fares, FAAC disbursements and the like are left out. The titles that were seen but not
served are printed (first few) so the mapping can be widened from the Actions log.

Not served: Central Bank of Nigeria MPC dates. The CBN publishes decisions after each
meeting but no forward schedule page was found (probe of 18 Oct 2026), so none is guessed.
"""
from __future__ import annotations

import json
import re
import sys

from calendar_common import clean_name, run_single

OUT = "data-calendar-ng.json"
URL = "https://nigerianstat.gov.ng/"
SRC = "nigerianstat.gov.ng release calendar (official National Bureau of Statistics calendar)"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def classify(title: str) -> str | None:
    t = title.lower()
    if t.startswith("cpi and inflation report"):
        return "cpi"
    if re.search(r"\bgdp\b|gross domestic product", t) and "report" in t:
        return "gdp"
    if "foreign trade" in t:
        return "trade"
    if "labour force" in t or "labor force" in t or "unemployment" in t:
        return "jobs"
    return None


def parse(page: str, today: str | None = None) -> tuple[list[dict], list[str]]:
    m = re.search(r'\[\s*\{"id":"\d+","title":', page)
    if not m:
        return [], ["no embedded calendar events array found"]
    try:
        arr, _ = json.JSONDecoder().raw_decode(page, m.start())
    except ValueError as e:
        return [], [f"embedded events are not valid JSON: {e}"]
    out, skipped = [], []
    for it in arr:
        day, title = str(it.get("start", "")), str(it.get("title", ""))
        if not ISO.match(day) or day.startswith("1970"):
            continue
        concept = classify(title)
        if concept is None:
            if today is None or day >= today:       # the array also holds years of past releases
                skipped.append(title)
            continue
        out.append({"date": day, "country": "Nigeria", "concept": concept,
                    "name": clean_name(title), "source": SRC, "time": None})
    if skipped:
        stems = sorted({re.sub(r"\s+(?:\w+ )?20\d\d.*$", "", t) for t in skipped})
        print(f"note Nigeria: {len(skipped)} upcoming events not served: {stems[:25]}")
    problems = [] if any(e["concept"] == "cpi" for e in out) else ["no CPI and Inflation Report among the events"]
    return out, problems


def fetch_events(s, today: str) -> list[dict]:
    r = s.get(URL, timeout=40)
    r.raise_for_status()
    ev, problems = parse(r.text, today)
    if problems:
        raise ValueError("; ".join(problems))
    return ev


def main() -> int:
    return run_single(OUT, "Nigeria", fetch_events, "Nigeria")


if __name__ == "__main__":
    sys.exit(main())
