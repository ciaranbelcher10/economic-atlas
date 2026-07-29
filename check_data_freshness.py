"""
Operator-side data freshness check.

Runs as the last step of the hourly Actions workflow, after every fetch
script and the data commit. Scans every country's main data file and
flags any series that's gone properly stale -- not just "past its usual
publication date" (which is normal and already shown to visitors as the
orange light), but 3x past that, which is the same threshold the site's
own freshness() function already uses client-side to distinguish
"awaiting next release" from "Source series stale" in a tooltip. A
series only shows up here if it's crossed that same, already-agreed
line, so this deliberately does NOT fire on every metric that's a few
days into its normal update window -- only on genuine breakage: a fetch
that's silently failing, falling back, or stopped finding new data.

Writes:
  - freshness_alerts.json   machine-readable list of flagged series, for
                             the next workflow step to act on
  - $GITHUB_STEP_SUMMARY    a markdown table, if running in Actions, so
                             every run's summary page shows the current
                             state even when nothing's wrong

Exit code is always 0 -- this never fails the workflow. It's a report,
not a gate.
"""
import json
import os
import re
from datetime import datetime, timezone

# Same 18 country files the visitor-facing pages read. Deliberately
# excludes trade-partner files and the UK-specific breakdown files
# (MPC votes, spending COFOG, inactivity reasons, age breakdown) --
# those have their own structure and update cadence, not the simple
# {label, unit, freq, points} series shape this check is built around.
DATA_FILES = {
    "UK": "data.json", "US": "data-us.json", "Eurozone": "data-ez.json", "Japan": "data-jp.json",
    "India": "data-in.json", "Canada": "data-ca.json", "Australia": "data-au.json", "South Korea": "data-kr.json",
    "Israel": "data-il.json", "Mexico": "data-mx.json", "Brazil": "data-br.json", "South Africa": "data-za.json",
    "Morocco": "data-ma.json", "Germany": "data-de.json", "France": "data-fr.json", "Italy": "data-it.json",
    "Spain": "data-es.json", "Netherlands": "data-nl.json",
}

# Identical to the JS STALE_DAYS used on every country page, Compare,
# and Dashboard -- this is the "expected, routine lag" threshold. The
# operator alert below only fires at 3x this, matching the client's own
# "Source series stale" tooltip cutoff, not this baseline.
STALE_DAYS = {"months": 75, "quarters": 150, "years": 660}
STALE_MULTIPLIER = 3


def period_end(period):
    """Python port of the site's periodEnd(): last calendar day covered
    by a period string like '2026-06', '2026-Q2', or '2026'."""
    m = re.match(r"^(\d{4})-(\d{2})$", period)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        next_month = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=timezone.utc)
        return next_month.replace(day=1)
    m = re.match(r"^(\d{4})-Q(\d)$", period)
    if m:
        year, q = int(m.group(1)), int(m.group(2))
        month = q * 3
        next_month = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=timezone.utc)
        return next_month.replace(day=1)
    m = re.match(r"^(\d{4})$", period)
    if m:
        return datetime(int(m.group(1)) + 1, 1, 1, tzinfo=timezone.utc)
    return None


def check_series(country, key, series):
    """Returns an alert dict if this series is genuinely stale, else None."""
    points = series.get("points") or []
    if not points:
        return None
    freq = series.get("freq", "months")
    threshold_days = STALE_DAYS.get(freq, 90)
    last_period = points[-1][0]
    end = period_end(last_period)
    if end is None:
        return None
    age_days = (datetime.now(timezone.utc) - end).total_seconds() / 86400
    if age_days <= threshold_days * STALE_MULTIPLIER:
        return None
    return {
        "country": country,
        "key": key,
        "label": series.get("label", key),
        "last_period": last_period,
        "age_days": round(age_days),
        "normal_threshold_days": threshold_days,
    }


def run(base_dir="."):
    alerts = []
    missing_files = []
    for country, filename in DATA_FILES.items():
        path = os.path.join(base_dir, filename)
        if not os.path.exists(path):
            missing_files.append({"country": country, "file": filename})
            continue
        try:
            with open(path) as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            missing_files.append({"country": country, "file": filename, "error": str(e)})
            continue
        for key, series in (payload.get("series") or {}).items():
            alert = check_series(country, key, series)
            if alert:
                alerts.append(alert)

    alerts.sort(key=lambda a: -a["age_days"])
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
        "missing_or_unreadable_files": missing_files,
    }

    with open(os.path.join(base_dir, "freshness_alerts.json"), "w") as f:
        json.dump(result, f, indent=2)

    summary_lines = []
    if alerts or missing_files:
        summary_lines.append("### \U0001F534 Data freshness check: {} issue(s) found\n".format(
            len(alerts) + len(missing_files)))
        if alerts:
            summary_lines.append("| Country | Series | Last published | Days overdue |")
            summary_lines.append("|---|---|---|---|")
            for a in alerts:
                overdue = a["age_days"] - a["normal_threshold_days"]
                summary_lines.append("| {} | {} | {} | {} |".format(
                    a["country"], a["label"], a["last_period"], overdue))
        if missing_files:
            summary_lines.append("\n**Missing or unreadable files:** " +
                                  ", ".join(m["file"] for m in missing_files))
    else:
        summary_lines.append("### \u2705 Data freshness check: all series within normal range\n")

    summary = "\n".join(summary_lines)
    print(summary)
    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with open(step_summary_path, "a") as f:
            f.write(summary + "\n")

    return result


if __name__ == "__main__":
    run()
