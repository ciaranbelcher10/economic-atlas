"""Rotate OECD requests across three country groups, one group per hour.

Why. The OECD rate-limits by requests per window, and a single hourly run
asks for far more than the window allows: in the 20 September 18:51 run the
first eleven countries succeeded and every OECD call after that returned
HTTP 429 for the rest of the job. Which countries lost data was decided by
nothing more than their position in the run order.

What this does. Every fetch script still runs every hour, and everything it
fetches from FRED, ONS, Eurostat, the IMF, the World Bank and the rest is
fetched every hour exactly as before. Only the OECD requests rotate: a
country's OECD series are fetched in its group's hour and kept at their last
values in the other two. So each run makes roughly a third of the OECD
requests it used to, and OECD data -- monthly or slower anyway -- is at most
three hours old.

How a skipped series is kept. ``check()`` raises ``NotThisHour`` at the top of
an OECD fetcher. The series therefore never enters the run's output, and
``series_guard.apply_guard`` carries the previous version forward, as it
already does for any series absent from a run. Raising (rather than
returning nothing) matters: several scripts fall back to another provider
when the OECD returns nothing -- Chile and South Africa drop to World Bank
annual CPI -- and an exception passes straight by that fallback, so a
skipped hour never triggers it.

Groups are balanced by OECD request load, not by country count: the scripts
that fetch CPI, month-on-month and business confidence from the OECD are
spread five, five and four across the groups.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

__all__ = ["NotThisHour", "check", "current_group", "script_group", "GROUPS"]

# Keyed by script file, not by country code: a script knows its own name
# without having to know which OECD area code its fetchers use, and one
# script (fetch_data.py) serves two countries.
GROUPS = {
    # A
    "fetch_au.py": "A", "fetch_br.py": "A", "fetch_ca.py": "A",
    "fetch_cl.py": "A", "fetch_co.py": "A", "fetch_dk.py": "A",
    "fetch_sg.py": "A", "fetch_data.py": "A", "fetch_us.py": "A",
    "fetch_ez.py": "A", "fetch_jp.py": "A",
    # B
    "fetch_ch.py": "B", "fetch_id.py": "B", "fetch_in.py": "B",
    "fetch_il.py": "B", "fetch_mx.py": "B", "fetch_ie.py": "B",
    "fetch_th.py": "B", "fetch_de.py": "B", "fetch_fr.py": "B",
    "fetch_it.py": "B", "fetch_es.py": "B",
    # C
    "fetch_no.py": "C", "fetch_za.py": "C", "fetch_kr.py": "C",
    "fetch_tr.py": "C", "fetch_pl.py": "C", "fetch_se.py": "C",
    "fetch_nl.py": "C", "fetch_at.py": "C", "fetch_ar.py": "C",
    "fetch_ma.py": "C",
}
ORDER = ("A", "B", "C")


class NotThisHour(Exception):
    """Raised by an OECD fetcher outside its group's hour.

    Not a failure: the previous series is kept, and no fallback provider is
    tried. The message says which group this hour serves so the log reads
    as a deliberate skip rather than an error.
    """


def current_group(now: datetime | None = None) -> str:
    """The group whose OECD requests run this hour.

    ``OECD_TURN_GROUP`` overrides the clock, so a specific group can be
    forced for a test or a manual catch-up run; ``OECD_TURN_GROUP=ALL``
    disables the rotation entirely.
    """
    forced = os.environ.get("OECD_TURN_GROUP", "").strip().upper()
    if forced in ORDER or forced == "ALL":
        return forced
    now = now or datetime.now(timezone.utc)
    return ORDER[now.hour % len(ORDER)]


def script_group(script: str | None = None) -> str | None:
    """The group for the script being run, or None if it is not mapped."""
    name = os.path.basename(script or (sys.argv[0] if sys.argv else ""))
    return GROUPS.get(name)


_announced = False


def check(script: str | None = None, now: datetime | None = None) -> None:
    """Raise NotThisHour unless this script's OECD turn is now.

    Fails open: a script missing from GROUPS always fetches. An unmapped
    script silently losing its OECD data would be far worse than it making
    a few extra requests, and a new country added without a group entry
    should keep working.
    """
    global _announced
    mine = script_group(script)
    serving = current_group(now)
    if mine is None or serving == "ALL" or mine == serving:
        return
    if not _announced:
        print(f"  [oecd-turn] this hour serves group {serving}; this script is group "
              f"{mine}, so its OECD series are kept from their last fetch")
        _announced = True
    raise NotThisHour(f"OECD turn is group {mine} (this hour: group {serving}); "
                      f"kept previous data, not a failure")
