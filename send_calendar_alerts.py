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


def build_email_text(matches: list[dict]) -> str:
    """Plain-text fallback -- kept for clients that reject/strip HTML."""
    lines = ["Coming up in the next week, from your tracked countries and metrics on The Economic Atlas Calendar:", ""]
    for ev in matches:
        lines.append(f"{ev['date']}  {ev.get('country', '?')} - {ev.get('name', 'Release')}")
        if ev.get("time"):
            lines.append(f"    {ev['time']}")
    lines.append("")
    lines.append("Manage what you track: https://theeconomicatlas.com/calendar")
    return "\n".join(lines)


def _html_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# The site's own font stack, taken verbatim from style.css (line 31) --
# not the Helvetica/Arial ChartMaker deliberately uses for its own
# canvas text. Unlike ChartMaker, this email has no reason to diverge
# from the site's real typography, so it should actually match it.
SITE_FONT = "\"Avenir Next\",\"Avenir\",\"Nunito Sans\",system-ui,sans-serif"

# Event country strings (see ALL_CALENDAR_FILES's source data) to their
# page slug, so each event can link straight to that country's page.
# Covers every country name/abbreviation currently in use across the
# calendar fetch scripts, not just the ones with events today, so a
# newly-added country doesn't silently go unlinked.
COUNTRY_SLUGS = {
    "UK": "uk", "US": "us", "Eurozone": "eurozone", "Japan": "japan",
    "Canada": "canada", "Australia": "australia", "India": "india",
    "South Korea": "southkorea", "Israel": "israel", "Mexico": "mexico",
    "Brazil": "brazil", "South Africa": "southafrica", "Morocco": "morocco",
    "Germany": "germany", "France": "france", "Italy": "italy",
    "Spain": "spain", "Netherlands": "netherlands", "Denmark": "denmark",
    "Ireland": "ireland", "Norway": "norway", "Chile": "chile",
    "Colombia": "colombia", "Turkey": "turkey", "Indonesia": "indonesia",
    "Poland": "poland", "Switzerland": "switzerland", "Argentina": "argentina",
    "Sweden": "sweden", "Singapore": "singapore", "Austria": "austria",
    "Thailand": "thailand",
}


def _format_day_heading(d: date) -> str:
    # e.g. "Tuesday, 8 September" -- no year, this is always a near-term window.
    return d.strftime("%A, %-d %B")


def build_email_html(matches: list[dict]) -> str:
    """Grouped-by-date HTML email: a day heading, then each event as a
    row with the metric name and its release time laid out clearly,
    rather than the flat repeated-date plain-text list."""
    # Group in-order (matches already sorted by date) without re-sorting,
    # so ties within a day keep their original relative order.
    days: list[tuple[date, list[dict]]] = []
    for ev in matches:
        ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
        if days and days[-1][0] == ev_date:
            days[-1][1].append(ev)
        else:
            days.append((ev_date, [ev]))

    day_blocks = []
    for ev_date, day_events in days:
        rows = []
        for ev in day_events:
            country_raw = ev.get("country", "?")
            country = _html_escape(country_raw)
            name = _html_escape(ev.get("name", "Release"))
            time_str = _html_escape(ev["time"]) if ev.get("time") else ""
            slug = COUNTRY_SLUGS.get(country_raw)
            country_html = (
                f"<a href=\"https://theeconomicatlas.com/{slug}\" style=\"color:#AD1E1E;font-weight:bold;text-decoration:none;\">{country}</a>"
                if slug else f"<span style=\"color:#AD1E1E;font-weight:bold;\">{country}</span>"
            )
            rows.append(f"""
              <tr>
                <td style="padding:10px 0;border-top:1px solid #E7E2D8;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="font-size:15px;color:#1A1A1A;font-family:{SITE_FONT};">
                        {country_html}
                        &nbsp;&mdash;&nbsp;{name}
                      </td>
                      <td align="right" style="font-size:13px;color:#6B6B6B;font-family:{SITE_FONT};white-space:nowrap;padding-left:12px;">
                        {time_str}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>""")
        day_blocks.append(f"""
          <tr>
            <td style="padding:22px 0 0 0;">
              <div style="font-family:{SITE_FONT};font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:#8A8375;font-weight:bold;">
                {_html_escape(_format_day_heading(ev_date))}
              </div>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {''.join(rows)}
              </table>
            </td>
          </tr>""")

    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background-color:#F4F1EA;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#F4F1EA;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background-color:#FFFFFF;border:1px solid #E7E2D8;border-radius:6px;">
            <tr>
              <td style="padding:28px 32px 20px 32px;border-bottom:2px solid #1A1A1A;">
                <table role="presentation" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="padding-right:10px;">
                      <img src="https://theeconomicatlas.com/logo-64.png" width="28" height="28" alt="" style="display:block;border-radius:50%;">
                    </td>
                    <td style="font-family:{SITE_FONT};font-size:19px;color:#1A1A1A;font-weight:bold;">
                      The Economic Atlas Calendar
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 4px 32px;font-family:{SITE_FONT};font-size:13px;color:#6B6B6B;">
                Coming up in the next week, from your tracked countries and metrics:
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 8px 32px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  {''.join(day_blocks)}
                </table>
              </td>
            </tr>
            <tr>
              <td align="center" style="padding:28px 32px 32px 32px;border-top:1px solid #E7E2D8;">
                <a href="https://theeconomicatlas.com/calendar" style="display:inline-block;font-family:{SITE_FONT};font-size:15px;font-weight:bold;color:#FFFFFF;background-color:#1A1A1A;text-decoration:none;padding:12px 28px;border-radius:5px;">View full calendar &rarr;</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def send_alert_email(to_email: str, text_body: str, html_body: str):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY not set -- skipping email.", file=sys.stderr)
        return
    payload = json.dumps({
        "from": f"The Economic Atlas Calendar <{ALERT_FROM}>",
        "to": [to_email],
        "subject": "Your tracked releases this week",
        "text": text_body,
        "html": html_body,
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
        text_body = build_email_text(matches)
        html_body = build_email_html(matches)
        send_alert_email(email, text_body, html_body)
        sent += 1

    print(f"Done. Sent: {sent}, skipped (no preferences set): {skipped_no_prefs}, "
          f"skipped (no matches in next {ALERT_WINDOW_DAYS} days): {skipped_no_matches}.")


if __name__ == "__main__":
    main()
