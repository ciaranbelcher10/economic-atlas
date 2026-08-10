"""
Silent-failure alerting for the data pipeline -- the fetch-script half.

Runs as the final step of the hourly workflow, after check_data_freshness.py.
Combines two independent signals and, if either has something to report,
sends ONE email via Resend so a real failure lands in an inbox instead of
only ever existing as a GitHub Issue nobody's watching in real time:

  1. freshness_alerts.json  -- written by check_data_freshness.py. Genuinely
     stale series (3x past normal cadence): a fetch that's stopped finding
     new data, or is silently falling back to a source that no longer
     updates. This is the same signal already driving the GitHub Issue.

  2. pipeline_log.txt -- the combined stdout/stderr of every fetch step in
     this run (each step now tees its own output into this shared file).
     Two things are pulled out of it:
       - "FAIL  <key>  <exc>" lines: existing per-series soft-failure
         reporting that every fetch script already prints, but which
         previously just scrolled past in the Actions log unread.
       - "Traceback (most recent call last):" blocks: a genuine hard crash
         in a fetch script. Every fetch step now runs with
         continue-on-error: true, specifically so one script crashing
         doesn't silently prevent every later country, the data commit,
         and the freshness check from ever running -- but that means a
         hard crash needs its own explicit surfacing here, since the
         workflow itself will now show green even when one step failed.

This intentionally does NOT alert on the routine "orange light" case (a
series a few days into its normal update window) -- only on the two
genuine-breakage signals above. Exit code is always 0: this is a report,
not a gate, matching check_data_freshness.py's own convention.
"""
import json
import os
import re
import urllib.error
import urllib.request

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
ALERT_FROM = "alerts@theeconomicatlas.com"
ALERT_TO = "ciaranbelcher@gmail.com"

FAIL_LINE_RE = re.compile(r"^FAIL\s+(\S+)\s+(.*)$", re.MULTILINE)
TRACEBACK_RE = re.compile(
    r"Traceback \(most recent call last\):\n(?:.*\n)*?(\S+(?:Error|Exception):.*)"
)
# Which script produced the log lines we're currently reading -- every
# fetch step writes a marker before running so a crash/failure can still
# be attributed to a country even though all steps share one log file.
RUNNING_RE = re.compile(r"^>>> RUNNING (\S+)$", re.MULTILINE)


def load_freshness():
    try:
        with open("freshness_alerts.json") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"alerts": [], "missing_or_unreadable_files": []}


def attribute_to_script(log, pos):
    """Given a character offset into the combined log, find which
    '>>> RUNNING fetch_x.py' marker most recently preceded it."""
    last = None
    for m in RUNNING_RE.finditer(log):
        if m.start() > pos:
            break
        last = m.group(1)
    return last or "unknown script"


def parse_log():
    soft_failures = []
    hard_crashes = []
    try:
        with open("pipeline_log.txt") as f:
            log = f.read()
    except OSError:
        return soft_failures, hard_crashes

    for m in FAIL_LINE_RE.finditer(log):
        soft_failures.append({
            "script": attribute_to_script(log, m.start()),
            "key": m.group(1),
            "reason": m.group(2).strip(),
        })

    for m in TRACEBACK_RE.finditer(log):
        hard_crashes.append({
            "script": attribute_to_script(log, m.start()),
            "error": m.group(1).strip(),
        })

    return soft_failures, hard_crashes


def build_email_body(freshness, soft_failures, hard_crashes):
    lines = []

    if hard_crashes:
        lines.append("HARD CRASHES (script did not complete)")
        for c in hard_crashes:
            lines.append(f"  - {c['script']}: {c['error']}")
        lines.append("")

    if soft_failures:
        lines.append("SOFT FAILURES (per-series, page still rendered)")
        for f in soft_failures:
            lines.append(f"  - {f['script']} / {f['key']}: {f['reason']}")
        lines.append("")

    if freshness.get("alerts"):
        lines.append("GENUINELY STALE SERIES (3x past normal cadence)")
        for a in freshness["alerts"]:
            overdue = a["age_days"] - a["normal_threshold_days"]
            lines.append(
                f"  - {a['country']} / {a['label']}: last published "
                f"{a['last_period']}, {overdue} days overdue"
            )
        lines.append("")

    if freshness.get("missing_or_unreadable_files"):
        lines.append("MISSING OR UNREADABLE DATA FILES")
        for m in freshness["missing_or_unreadable_files"]:
            extra = f": {m['error']}" if m.get("error") else ""
            lines.append(f"  - {m['country']} ({m['file']}){extra}")
        lines.append("")

    lines.append("Full run: check the Actions tab for the complete log and the open data-freshness Issue.")
    return "\n".join(lines)


def send_alert(subject, body):
    if not RESEND_API_KEY:
        print("RESEND_API_KEY not set -- skipping email, see summary above.")
        return
    payload = json.dumps({
        "from": f"Economic Atlas Pipeline <{ALERT_FROM}>",
        "to": [ALERT_TO],
        "subject": subject,
        "text": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "EconomicAtlas-PipelineAlert/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Alert email sent, Resend status {resp.status}")
    except urllib.error.HTTPError as exc:
        # Resend's error responses carry the real reason in the body
        # (bad key, unverified domain, etc.) -- the bare status code
        # alone isn't enough to diagnose a failure from the Actions log.
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = "<could not read response body>"
        print(f"Failed to send alert email: HTTP {exc.code} {exc.reason} -- {detail}")
    except Exception as exc:
        # Deliberately does not raise -- an alerting failure must never
        # fail the workflow itself.
        print(f"Failed to send alert email: {exc}")


def run():
    freshness = load_freshness()
    soft_failures, hard_crashes = parse_log()

    total = (
        len(hard_crashes) + len(soft_failures)
        + len(freshness.get("alerts", []))
        + len(freshness.get("missing_or_unreadable_files", []))
    )

    if total == 0:
        print("Pipeline alert check: nothing to report.")
        return

    severity = "CRASH" if hard_crashes else ("STALE" if freshness.get("alerts") else "WARN")
    subject = f"[{severity}] Economic Atlas pipeline: {total} issue(s) this run"
    body = build_email_body(freshness, soft_failures, hard_crashes)
    print(body)
    send_alert(subject, body)


if __name__ == "__main__":
    run()
