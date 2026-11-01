"""Keep past calendar events (v1.9.42).

Every fetch_calendar_*.py writes only upcoming events, so a release dropped off
the calendar the day after it happened. This runs after all the fetchers, before
the commit, and puts back each past event the calendar had already shown, taken
from the committed versions of the same data-calendar-*.json file in git.

Which events are kept. "Due" means dated on or before tomorrow (UTC): several
sources drop a release from their feed a few hours before its date in UTC (Stats NZ
publishes at 10:45am New Zealand time, the previous evening in UTC), so waiting for
the date to pass would lose them.
  - Each run: a due event in the newest committed version that the fetcher no longer
    lists is kept, unless it looks moved: the fetcher now lists the same country and
    release type within 14 days that the committed version did not have.
  - Backfill: a due event is kept if it was in the last committed version at least
    two days before its date (or, for a file younger than that, in the first version
    that holds it), and it does not look moved against the current file.
    A backfilled event must also be of a release type and source the fetcher still
    produces, so dates written by an earlier, since-fixed version of a fetcher stay out.
  - Events older than KEEP_DAYS are dropped, to keep the files small.
Upcoming events beyond tomorrow are never touched: the fetcher's list stands. An
event the fetcher still lists is left exactly as the fetcher wrote it.

Run:  python3 calendar_history.py              after the fetchers (the workflow step)
      python3 calendar_history.py --backfill   once, in a full clone, to bring back
                                               the events already lost (reads every
                                               committed version, not just HEAD)
Writes nothing when nothing changes. Never fails the run: any problem with one file
is printed and that file is left as the fetcher wrote it.
"""
from __future__ import annotations

import glob
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

KEEP_DAYS = 3 * 366
FIELDS = ("date", "country", "concept", "name")


def key(e: dict) -> tuple:
    return tuple(e.get(f) for f in FIELDS)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def committed_versions(path: str, full: bool) -> list[tuple[str, list[dict]]]:
    """[(commit date YYYY-MM-DD, events)] oldest first; just HEAD unless full."""
    if full:
        log = git("log", "--reverse", "--format=%H %cs", "--", path).split("\n")
        commits = [l.split() for l in log if l.strip()]
    else:
        try:
            commits = [[git("rev-parse", "HEAD").strip(), git("log", "-1", "--format=%cs", "HEAD").strip()]]
        except subprocess.CalledProcessError:
            return []
    out = []
    for sha, cdate in commits:
        try:
            out.append((cdate, json.loads(git("show", f"{sha}:{path}")).get("events", [])))
        except (subprocess.CalledProcessError, json.JSONDecodeError, AttributeError):
            continue    # the file did not exist yet at that commit, or was unreadable then
    return out


def _shift(day: str, n: int) -> str:
    return (datetime.fromisoformat(day) + timedelta(days=n)).date().isoformat()


def source_family(src) -> str:
    """The publisher and feed, without the per-release page: "ons.gov.uk/releases/cpi...
    (official ONS feed)" and "ons.gov.uk/releases/gdp... (official ONS feed)" match."""
    s = str(src or "")
    domain = re.split(r"[/\s,]", s.strip(), 1)[0].lower()
    paren = re.findall(r"\(([^()]*)\)", s)
    return domain + "|" + (paren[-1].strip().lower() if paren else "")


def looks_moved(e: dict, current: list[dict], before: set[tuple]) -> bool:
    """The fetcher now lists the same release type for the same country within 14 days,
    and that listing is new: the event was most likely rescheduled, not held."""
    lo, hi = _shift(e["date"], -14), _shift(e["date"], 14)
    for c in current:
        if (isinstance(c, dict) and c.get("country") == e.get("country") and c.get("concept") == e.get("concept")
                and isinstance(c.get("date"), str) and lo <= c["date"] <= hi and key(c) not in before):
            return True
    return False


def past_to_keep(versions: list[tuple[str, list[dict]]], current: list[dict], today: str,
                 full: bool) -> dict[tuple, dict]:
    oldest_ok, horizon = _shift(today, -KEEP_DAYS), _shift(today, 1)
    have = {key(e) for e in current if isinstance(e, dict)}
    due = lambda e: isinstance(e, dict) and isinstance(e.get("date"), str) and oldest_ok <= e["date"] <= horizon
    keep = {}
    if not versions:
        return keep
    if not full:
        head = {key(e) for e in versions[-1][1] if isinstance(e, dict)}
        for e in versions[-1][1]:
            if due(e) and key(e) not in have and not looks_moved(e, current, head):
                keep[key(e)] = e
        return keep
    seen: dict[tuple, dict] = {}
    for _, evs in versions:
        for e in evs:
            if due(e):
                seen[key(e)] = e
    # only what today's fetcher still produces: (release type, source) pairs that earlier,
    # since-fixed versions of a fetcher wrote (FRED's "FOMC Press Release" dates) stay gone
    live_pairs = {(c.get("concept"), source_family(c.get("source"))) for c in current if isinstance(c, dict)}
    for k, e in seen.items():
        if k in have or (e.get("concept"), source_family(e.get("source"))) not in live_pairs:
            continue
        ref = [evs for cdate, evs in versions if cdate <= _shift(e["date"], -2)]
        if not ref:
            ref = [next(evs for _, evs in versions if k in {key(x) for x in evs if isinstance(x, dict)})]
        ref_keys = {key(x) for x in ref[-1] if isinstance(x, dict)}
        if k in ref_keys and not looks_moved(e, current, ref_keys):
            keep[k] = e
    return keep


def merge_file(path: str, today: str, full: bool) -> int:
    """Number of past events added back to path."""
    with open(path) as f:
        cur = json.load(f)
    events = cur.get("events")
    if not isinstance(events, list):
        return 0
    have = {key(e) for e in events if isinstance(e, dict)}
    keep = past_to_keep(committed_versions(path, full), events, today, full)
    add = [e for k, e in keep.items() if k not in have]
    if not add:
        return 0
    cur["events"] = sorted(events + add, key=lambda e: (e.get("date", ""), e.get("concept", ""), e.get("name", "")))
    with open(path, "w") as f:
        json.dump(cur, f, indent=2)
    return len(add)


def main(argv: list[str]) -> int:
    full = "--backfill" in argv
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0
    for path in sorted(glob.glob("data-calendar-*.json")):
        try:
            n = merge_file(path, today, full)
        except Exception as e:      # never break the calendar commit over history
            print(f"WARNING {path}: past events not merged ({type(e).__name__}: {e})")
            continue
        if n:
            print(f"{path}: kept {n} past event{'s' if n != 1 else ''}")
        total += n
    print(f"calendar_history: {total} past events kept{' (backfill from full history)' if full else ''}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
