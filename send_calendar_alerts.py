"""Daily calendar email alerts.

Runs once a day (see send-calendar-alerts.yml), after the calendar data
refresh itself. For every user with calendar_email_alerts enabled in
their profile preferences, checks whether anything in their tracked
countries/metrics is coming up in the next ALERT_WINDOW_DAYS, and if
so, sends one summary email via Resend -- reusing send_pipeline_alert.py's
exact, already-verified send_alert() pattern (same Resend account, same
verified sending domain), not a new integration.

REQUIRES A NEW SECRET THAT DOESN'T EXIST YET:
  SUPABASE_SERVICE_ROLE_KEY -- profiles has row-level security enabled,
  so reading every user's preferences (not just "the current logged in
  user's own row", which is meaningless for a script) needs the
  service_role key specifically, not the anon key already used
  client-side. Get this from the Supabase dashboard: Project Settings
  -> API -> service_role (the "secret" key, not "anon"/"public"). This
  key bypasses row-level security entirely, so treat it like any other
  production secret -- GitHub Actions secret only, never in a file, and
  never logged.

NOT YET RUN LIVE -- this needs the new secret added before it can query
anything, and hasn't sent a real email. The individual pieces (the
Supabase REST query shape, the Resend call) are each confirmed patterns
already working elsewhere in this codebase (client-side JS for the
Supabase piece via the same profiles table; send_pipeline_alert.py for
the Resend piece), but they haven't been exercised together, from
Python, end to end, for this specific purpose.

DATA GAP WORTH KNOWING ABOUT: this script reads the same
data-calendar-*.json files the fetch_calendar_*.py scripts produce --
but calendar.html's hand-verified September 2026 events live only as a
hardcoded JS object inside that page, not in any JSON file, so this
script currently CANNOT see them. Concretely: right now, this script
would correctly alert on live-fetched October-onward events, but would
never alert on anything in September even though the calendar page
itself shows plenty there. Real fix: export that hardcoded EVENTS
object to its own data-calendar-manual.json (a one-off script could do
this, or it could be hand-maintained alongside the JS) and add it to
the ALL_CALENDAR_FILES list below. Not done here -- flagged rather than
silently left as a surprise gap.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
SUPABASE_URL = "https://skluvrxnuibkordzgtmu.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ALERT_FROM = "alerts@theeconomicatlas.com"

ALERT_WINDOW_DAYS = 7  # how far ahead counts as "coming up"

# Every data-calendar-*.json file a fetch script can produce. Missing
# files (a script that errored before writing, e.g. Poland/Morocco/
# Israel on a bad day) are skipped, not treated as a hard failure --
# same continue-on-error spirit as the fetch workflow itself.
ALL_CALENDAR_FILES = [
    "data-calendar-us.json", "data-calendar-uk.json", "data-calendar-ez.json",
    "data-calendar-jp.json", "data-calendar-jp-stats.json", "data-calendar-ca.json",
    "data-calendar-ca-stats.json", "data-calendar-au.json", "data-calendar-se.json",
    "data-calendar-no.json", "data-calendar-pl.json", "data-calendar-il.json",
    "data-calendar-cl.json", "data-calendar-ma.json", "data-calendar-id.json",
    "data-calendar-br.json", "data-calendar-tr.json",
    # Not created by any fetch script yet -- see module docstring's "DATA
    # GAP" section. Included here so it starts working the moment that
    # export exists, without needing this script touched again.
    "data-calendar-manual.json",
]

# Same normalisation calendar.html does client-side -- keeps "fomc" and
# "rate_decision" (and similarly-named aliases from other scripts)
# counted as the same trackable concept for matching against a user's
# preferences, rather than silently never matching because of a raw
# concept-string mismatch.
RATE_CONCEPT_ALIASES = {"fomc", "rate_decision"}


def normalise_concept(concept: str) -> str:
    return "rate_decision" if concept in RATE_CONCEPT_ALIASES else concept


def load_all_events() -> list[dict]:
    events = []
    for path in ALL_CALENDAR_FILES:
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: couldn't read {path}: {e}", file=sys.stderr)
            continue
        for ev in data.get("events", []):
            ev = dict(ev)
            ev["concept"] = normalise_concept(ev.get("concept", ""))
            events.append(ev)
    return events


def fetch_alert_subscribers() -> list[dict]:
    """Every profile with calendar_email_alerts truthy in preferences,
    via the Supabase REST API using the service_role key (bypasses RLS
    -- required, an anon key can't read other users' rows)."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("SUPABASE_SERVICE_ROLE_KEY not set -- cannot query subscribers, "
              "see module docstring for how to add it.", file=sys.stderr)
        return []
    url = (f"{SUPABASE_URL}/rest/v1/profiles"
           f"?select=id,email,preferences"
           f"&preferences->>calendar_email_alerts=eq.true")
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "User-Agent": "EconomicAtlas-CalendarAlerts/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Failed to fetch subscribers: HTTP {exc.code} {exc.reason} -- {detail}",
              file=sys.stderr)
        return []
    except Exception as exc:
        print(f"Failed to fetch subscribers: {exc}", file=sys.stderr)
        return []


def matching_upcoming_events(all_events: list[dict], preferences: dict,
                              today: date, window_end: date) -> list[dict]:
    tracked_countries = set(preferences.get("calendar_tracked_countries") or [])
    tracked_metrics = set(preferences.get("calendar_tracked_metrics") or [])
    if not tracked_countries or not tracked_metrics:
        return []  # never explicitly set preferences -- nothing to alert on
    matches = []
    for ev in all_events:
        try:
            ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if not (today <= ev_date <= window_end):
            continue
        if ev.get("country") not in tracked_countries:
            continue
        if ev.get("concept") not in tracked_metrics:
            continue
        matches.append(ev)
    matches.sort(key=lambda e: e["date"])
    return matches


def build_email_body(matches: list[dict]) -> str:
    lines = ["Coming up in the next week, from your tracked countries and metrics on The Economic Atlas Calendar:", ""]
    for ev in matches:
        lines.append(f"{ev['date']}  {ev.get('country', '?')} - {ev.get('name', 'Release')}")
        if ev.get("time"):
            lines.append(f"    {ev['time']}")
    lines.append("")
    lines.append("Manage what you track: https://theeconomicatlas.com/calendar")
    return "\n".join(lines)


def send_alert_email(to_email: str, body: str):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY not set -- skipping email.", file=sys.stderr)
        return
    payload = json.dumps({
        "from": f"The Economic Atlas Calendar <{ALERT_FROM}>",
        "to": [to_email],
        "subject": "Your tracked releases this week",
        "text": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "EconomicAtlas-CalendarAlerts/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Alert sent to {to_email}, Resend status {resp.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"Failed to send to {to_email}: HTTP {exc.code} {exc.reason} -- {detail}",
              file=sys.stderr)
    except Exception as exc:
        print(f"Failed to send to {to_email}: {exc}", file=sys.stderr)


def main():
    today = datetime.now(timezone.utc).date()
    window_end = today + timedelta(days=ALERT_WINDOW_DAYS)

    all_events = load_all_events()
    print(f"Loaded {len(all_events)} total events from {len(ALL_CALENDAR_FILES)} possible files.")

    subscribers = fetch_alert_subscribers()
    print(f"Found {len(subscribers)} profiles with calendar_email_alerts enabled.")

    sent, skipped_no_prefs, skipped_no_matches = 0, 0, 0
    for profile in subscribers:
        email = profile.get("email")
        preferences = profile.get("preferences") or {}
        if not email:
            continue
        matches = matching_upcoming_events(all_events, preferences, today, window_end)
        if not preferences.get("calendar_tracked_countries") or not preferences.get("calendar_tracked_metrics"):
            skipped_no_prefs += 1
            continue
        if not matches:
            skipped_no_matches += 1
            continue
        body = build_email_body(matches)
        send_alert_email(email, body)
        sent += 1

    print(f"Done. Sent: {sent}, skipped (no preferences set): {skipped_no_prefs}, "
          f"skipped (no matches in next {ALERT_WINDOW_DAYS} days): {skipped_no_matches}.")


if __name__ == "__main__":
    main()
