"""Rotate OECD requests across three country groups, one group per run
(by GitHub run number since v1.6.44; by clock hour when run locally).

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
    "fetch_be.py": "A",   # one light OECD call (BCI), like Austria; A was the smallest group
    "fetch_fi.py": "A",   # one light OECD call (BCI), like Belgium; A and B tied at 12, A now 13
    "fetch_cz.py": "A",   # two light OECD calls (BCI, national CPI); A, B, C tied at 13, A now 14
    "fetch_hu.py": "B",   # two light OECD calls (BCI, national CPI); B and C tied at 13, B now 14
    "fetch_ro.py": "C",   # one light OECD call (BCI); C 13, now 14
    "fetch_sa.py": "A",   # two OECD calls (QNA, CPI index); A, B, C tied at 14, A now 15
    # B
    "fetch_ch.py": "B", "fetch_id.py": "B", "fetch_in.py": "B",
    "fetch_il.py": "B", "fetch_mx.py": "B", "fetch_ie.py": "B",
    "fetch_th.py": "B", "fetch_de.py": "B", "fetch_fr.py": "B",
    "fetch_it.py": "B", "fetch_es.py": "B",
    "fetch_sk.py": "C",
    "fetch_hr.py": "B",   # one light OECD call (BCI, may not exist for a non-member); B was the smallest group (A15/B14/C15)   # one light OECD call (BCI), like Portugal; C was a smallest group
    "fetch_bg.py": "A",   # one light OECD call (BCI, may not exist for a non-member); A/B/C tied at 15, A now 16
    "fetch_lt.py": "B",   # one light OECD call (BCI), like Bulgaria; B was the smallest group (A16/B15/C15), B now 16
    "fetch_ee.py": "C",   # makes no OECD calls (BCI dropped: OECD series stopped 2026-04); C was the smallest group (A16/B16/C15), C now 16
    "fetch_lv.py": "A",   # one light OECD call (BCI); A/B/C tied at 16, A now 17
    "fetch_si.py": "B",   # one light OECD call (BCI); B was a smallest group (A17/B16/C16), B now 17
    "fetch_lu.py": "C",   # one light OECD call (BCI); C was the smallest group (A17/B17/C16), C now 17
    "fetch_cy.py": "A",   # makes no OECD calls (not an OECD member); A/B/C tied at 17, A now 18
    "fetch_mt.py": "B",   # makes no OECD calls (not an OECD member); B was a smallest group (A18/B17/C17), B now 18
    "fetch_ph.py": "C",   # makes no OECD calls (not an OECD member); C was the smallest group (A18/B18/C17), C now 18
    "fetch_tw.py": "A",   # makes no OECD calls; A and B were the smallest (A18/B18/C18), A now 19
    "fetch_vn.py": "B",   # makes no OECD calls; B now 19
    "fetch_ng.py": "C",   # makes no OECD calls (not an OECD member); C was the smallest group (A19/B19/C18), C now 19
    "fetch_eg.py": "A",   # makes no OECD calls (not an OECD member); A/B/C tied at 19, A now 20
    "fetch_is.py": "B",   # OECD-heavy (QNA, LFS, CPI index): B and C were the smallest (A20/B19/C19), B now 20
    "fetch_pe.py": "C",   # makes no OECD calls (not an OECD member); C was the smallest (A20/B20/C19), C now 20
    "fetch_hk.py": "A",   # makes no OECD calls (not an OECD member); A/B/C tied at 20, A now 21
    "fetch_pk.py": "B",   # makes no OECD calls (not an OECD member); B and C were the smallest (A21/B20/C20), B now 21
    "fetch_pt.py": "B",   # one light OECD call (BCI), like Belgium; B was the smallest group
    "fetch_gr.py": "B",   # one light OECD call (BCI), like Finland; B was the smallest group (12 vs A 13)
    # C
    "fetch_no.py": "C", "fetch_za.py": "C", "fetch_kr.py": "C",
    "fetch_tr.py": "C", "fetch_pl.py": "C", "fetch_se.py": "C",
    "fetch_nl.py": "C", "fetch_at.py": "C", "fetch_ar.py": "C",
    "fetch_ma.py": "C", "fetch_cn.py": "C",
    "fetch_my.py": "C",   # makes no OECD calls (Malaysia is not covered); mapped so the roster test holds
    "fetch_nz.py": "C",   # OECD-heavy (CPI, QNA, LFS, IRLT, BCI): C had four heavy countries, now five each
}
ORDER = ("A", "B", "C")


class NotThisHour(Exception):
    """Raised by an OECD fetcher outside its group's hour.

    Not a failure: the previous series is kept, and no fallback provider is
    tried. The message says which group this hour serves so the log reads
    as a deliberate skip rather than an error.
    """


def current_group(now: datetime | None = None) -> str:
    """The group whose OECD requests run in this run.

    ``OECD_TURN_GROUP`` overrides the clock, so a specific group can be
    forced for a test or a manual catch-up run; ``OECD_TURN_GROUP=ALL``
    disables the rotation entirely.
    """
    forced = os.environ.get("OECD_TURN_GROUP", "").strip().upper()
    if forced in ORDER or forced == "ALL":
        return forced
    # One group per RUN, not per clock hour (v1.6.44). A refresh takes about
    # six minutes, so a run starting at :57 used to change group part-way:
    # on 4 Oct 2026 fetch_kr ran at 14:59 (group C) but fetch_tr at 15:01
    # (group A), and Turkey, Poland, Sweden and Austria lost their turn.
    # GitHub sets GITHUB_RUN_NUMBER identically in every step of a run and
    # increments it each run, so every script agrees and runs still rotate
    # A -> B -> C. An explicit ``now`` (tests) or no run number (a local
    # run) uses the clock as before.
    run_no = os.environ.get("GITHUB_RUN_NUMBER", "").strip()
    if now is None and run_no.isdigit():
        return ORDER[int(run_no) % len(ORDER)]
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
        print(f"  [oecd-turn] this run serves group {serving}; this script is group "
              f"{mine}, so its OECD series are kept from their last fetch")
        _announced = True
    raise NotThisHour(f"OECD turn is group {mine} (this run: group {serving}); "
                      f"kept previous data, not a failure")


# ---------------------------------------------------------------- v1.8.0
# Retry OECD 429s with backoff. The rotation above keeps each hour's OECD load
# to a third, but the scripts late in a group's hour still hit 429 (16 Oct:
# Iceland's five OECD series, then HR, LT, SI, GR, HU). A 429 used to fail
# the series at once. Now a request to sdmx.oecd.org that gets 429 is retried
# after the server's Retry-After (or 20 s, then 40 s), at most twice. The
# whole process may spend at most OECD_429_BUDGET seconds (default 120)
# waiting; once that is used up, or the host has refused twice in a row after
# waiting, later 429s fail immediately as before, so a host that is shut for
# the hour cannot stretch the job. Every other host is untouched.
import time as _time

try:
    import requests as _requests
except Exception:  # pragma: no cover - requests is always installed in CI
    _requests = None

_BUDGET = float(os.environ.get("OECD_429_BUDGET", "120"))
_state = {"spent": 0.0, "dead": False}


def _wait_for(resp, attempt):
    ra = resp.headers.get("Retry-After", "") if resp is not None else ""
    try:
        w = float(ra)
    except ValueError:
        w = 20.0 * (2 ** attempt)
    return max(1.0, min(w, 60.0))


def _wrap(get):
    if getattr(get, "_oecd_429", False):
        return get

    def get_with_retry(url, *args, **kwargs):
        resp = get(url, *args, **kwargs)
        if "sdmx.oecd.org" not in str(url):
            return resp
        for attempt in range(2):
            if getattr(resp, "status_code", None) != 429 or _state["dead"]:
                return resp
            w = _wait_for(resp, attempt)
            if _state["spent"] + w > _BUDGET:
                print(f"  [oecd-429] retry budget used ({_state['spent']:.0f}s); not waiting")
                _state["dead"] = True
                return resp
            print(f"  [oecd-429] rate-limited; waiting {w:.0f}s, retry {attempt + 1}/2")
            _time.sleep(w)
            _state["spent"] += w
            resp = get(url, *args, **kwargs)
        if getattr(resp, "status_code", None) == 429:
            print("  [oecd-429] still refused after two waits; later 429s fail at once")
            _state["dead"] = True
        return resp

    get_with_retry._oecd_429 = True
    return get_with_retry


if _requests is not None:
    _requests.get = _wrap(_requests.get)
