"""Export calendar.html's hand-verified EVENTS object to
data-calendar-manual.json, so send_calendar_alerts.py can actually see
the hand-curated dates (currently only inside a hardcoded JS object in
the page itself) -- see the "DATA GAP" note in send_calendar_alerts.py.

Run:  python3 export_manual_calendar_events.py
Requires Node (already used for verification elsewhere in this repo's
workflow) -- the EVENTS block is a real JS object literal, not valid
JSON on its own (unquoted keys, JS comments possible), so this uses
Node itself to evaluate it and dump real JSON, rather than a regex
JSON-ifier that could quietly mishandle an edge case.

This is meant to be re-run by hand each time calendar.html's EVENTS
object is hand-edited (e.g. when new hand-verified dates get added for
a new month) -- it is NOT wired into the daily fetch workflow, since
the source of truth here is a person editing calendar.html directly,
not a live fetch.
"""

import json
import re
import subprocess
import sys

CALENDAR_HTML = "calendar.html"
OUTPUT_FILE = "data-calendar-manual.json"


def main():
    try:
        html = open(CALENDAR_HTML, encoding="utf-8").read()
    except OSError as e:
        print(f"ERROR: couldn't read {CALENDAR_HTML}: {e}", file=sys.stderr)
        sys.exit(1)

    m = re.search(r"var EVENTS = (\{.*?\n\});", html, re.S)
    if not m:
        print(f"ERROR: couldn't find 'var EVENTS = {{...}};' in {CALENDAR_HTML} -- "
              "has the variable been renamed?", file=sys.stderr)
        sys.exit(1)
    events_js = m.group(1)

    # Real JS eval via Node, not a regex-based JSON-ifier -- the object
    # has unquoted keys and would need real JS parsing to handle
    # correctly and safely.
    node_script = f"const EVENTS = {events_js}; console.log(JSON.stringify(EVENTS));"
    result = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: Node couldn't evaluate the EVENTS object: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    events_by_date = json.loads(result.stdout)

    # Flatten calendar.html's {date: [event, ...]} shape into the same
    # flat {events: [...]} shape every fetch_calendar_*.py script
    # produces, so send_calendar_alerts.py can treat every source file
    # identically without a special case for this one.
    flat_events = []
    for iso_date, events in events_by_date.items():
        for ev in events:
            flat_events.append({
                "date": iso_date,
                "country": ev.get("country"),
                "concept": ev.get("concept"),
                "name": ev.get("name"),
                "source": ev.get("src"),
                "time": ev.get("time"),
            })

    out = {"generated": "manual", "country": "multiple", "events": flat_events}
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(flat_events)} hand-verified events to {OUTPUT_FILE}.")


if __name__ == "__main__":
    main()
