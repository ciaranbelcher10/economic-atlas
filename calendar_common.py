"""Shared helpers for the calendar scripts added in v1.8.14 (Iceland, Hong Kong,
Vietnam, Nigeria). Each script holds its own parser and mapping; this holds only the
parts that must behave identically: reading a page as text lines, and the
write-or-keep-the-old-file rule used by every calendar script.

Rule (same as fetch_calendar_nz.py): if the source fails, parses to nothing, or
leaves no upcoming event, the existing data-calendar-XX.json is left untouched and
the run returns 1, so the Actions log shows it and visitors keep the last good file.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "en"}


def page_lines(markup: str) -> list[str]:
    """Visible text as lines; table cells in a row are joined with ' | '."""
    h = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", markup)
    h = re.sub(r"(?i)</t[dh]>\s*<t[dh][^>]*>", " | ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(tr|li|p|div|h[1-6]|section|article)>", "\n", h)
    h = html.unescape(re.sub(r"<[^>]+>", " ", h))
    return [re.sub(r"\s+", " ", l).strip() for l in h.split("\n") if l.strip()]


def clean_name(s: str) -> str:
    """Reader-facing text: single spaces, 'socio - economic' style dashes closed,
    and never an em dash or double hyphen (sitewide copy rule)."""
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+-\s+(?=[a-z])", "-", s)
    s = s.replace("\u2014", ",").replace("--", "-")
    return re.sub(r"\s+,", ",", s)


def run_single(out: str, country: str, fetch_events, tag: str) -> int:
    """fetch_events(session, today) -> list of event dicts; raise on any problem."""
    s = requests.Session()
    s.headers.update(UA)
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        events = [e for e in fetch_events(s, today) if e["date"] >= today]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        print(f"ERROR {tag}: {type(e).__name__}: {e}; existing file kept.", file=sys.stderr)
        return 1
    events = sorted({(e["date"], e["concept"], e["name"]): e for e in events}.values(),
                    key=lambda e: (e["date"], e["concept"], e["name"]))
    if not events:
        print(f"ERROR {tag}: zero upcoming {country} events; existing file kept.", file=sys.stderr)
        return 1
    with open(out, "w") as f:
        json.dump({"generated": datetime.now(timezone.utc).isoformat(), "country": country,
                   "events": events}, f, indent=2)
    kinds = {}
    for e in events:
        kinds[e["concept"]] = kinds.get(e["concept"], 0) + 1
    print(f"Wrote {len(events)} {country} calendar events ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}).")
    return 0
