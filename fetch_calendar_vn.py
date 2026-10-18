"""Fetch Vietnam's official release dates and write data-calendar-vn.json (v1.8.14).

One official source: the National Statistics Office's release calendar
(nso.gov.vn/en/release-calendar-3/), which embeds the whole list in the page as
`var events=[{"title":..., "status":..., "date":"YYYY-MM-DD", "format":...}, ...]`
(482 entries in the probe of 18 Oct 2026; some carry a quarter such as
"4th quarter of 2025" instead of a day and are skipped).

Served: the NSO's monthly "socio-economic situation report" is the release that
carries the month's CPI and trade figures, so each one is listed as cpi and trade;
quarterly and 6-/9-month reports also carry GDP and are listed as gdp as well. The
event name keeps the report's own title with the concept in brackets, so nothing is
claimed beyond what the report is called. Other titles (yearbooks, special surveys)
are left out. Not served: State Bank of Vietnam decisions (no published schedule).

If the calendar page has moved (its slug has a numeric suffix), the homepage is read
for the current release-calendar link. A failure keeps the existing file.
"""
from __future__ import annotations

import json
import re
import sys

from calendar_common import clean_name, run_single

OUT = "data-calendar-vn.json"
URLS = ["https://www.nso.gov.vn/en/release-calendar-3/"]
HOME = "https://www.nso.gov.vn/en/homepage/"
SRC = "nso.gov.vn release calendar (official National Statistics Office of Vietnam calendar)"
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse(page: str) -> tuple[list[dict] | None, list[str]]:
    """Events from the embedded array; (None, []) when the page carries none."""
    m = re.search(r"var\s+events\s*=\s*", page)
    if not m:
        return None, []
    try:
        arr, _ = json.JSONDecoder().raw_decode(page, m.end())
    except ValueError as e:
        return None, [f"embedded events are not valid JSON: {e}"]
    if not isinstance(arr, list) or not arr:
        return None, ["embedded events list is empty"]
    out, reports = [], 0
    for it in arr:
        day, title = str(it.get("date", "")), str(it.get("title", ""))
        if not ISO.match(day):
            continue
        t = title.lower()
        if "socio" in t and "situation report" in t:
            reports += 1
            periodic = ("quarter" in t or "first 6 months" in t or "first 9 months" in t
                        or "first six months" in t or "first nine months" in t)
            base = clean_name(title)
            kinds = [("gdp", "GDP")] if periodic else []
            kinds += [("cpi", "CPI"), ("trade", "trade")]
            for concept, label in kinds:
                out.append({"date": day, "country": "Vietnam", "concept": concept,
                            "name": f"{base} ({label})", "source": SRC, "time": None})
    problems = [] if reports else ["no socio-economic situation reports among the events"]
    return out, problems


def fetch_events(s, today: str) -> list[dict]:
    urls = list(URLS)
    last = ""
    for i in range(2):
        for u in urls:
            r = s.get(u, timeout=40)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            ev, problems = parse(r.text)
            if problems:
                raise ValueError("; ".join(problems))
            if ev is not None:
                return ev
            last = u
        if i == 0:                       # the slug may have moved: read the homepage
            h = s.get(HOME, timeout=40)
            h.raise_for_status()
            urls = [u for u in re.findall(r'href="(https://www\.nso\.gov\.vn/en/release-calendar[^"]*)"', h.text)
                    if u not in urls] or urls
    raise ValueError(f"no embedded events list found (last page tried: {last or 'none'})")


def main() -> int:
    return run_single(OUT, "Vietnam", fetch_events, "Vietnam")


if __name__ == "__main__":
    sys.exit(main())
