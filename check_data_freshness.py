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

Also flags series that have been TRUNCATED (still present, but holding
much less history than last run) and series that have DISAPPEARED entirely
since the previous
commit -- a distinct failure mode from staleness. A rate-limited fetch
with no carry-over fallback doesn't leave stale data behind for the
staleness check to eventually catch; the key is just gone from the JSON
the moment it fails, with nothing to compare an "age" against. This is
what happened to Ireland's and Norway's cpi during the Aug 2026 429
cascade -- invisible to the staleness check above, since there was no
stale-but-present data to flag, just an absent key. Detected by diffing
each country's current series keys against the immediately preceding
commit (git show HEAD~1:<file>) -- requires running inside the same git
checkout the commit step just ran in; if git or history isn't
available, this check is skipped rather than erroring the whole run.

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
import subprocess
from datetime import datetime, timezone

# All 32 country data files the visitor-facing pages read. Deliberately
# excludes trade-partner files and the UK-specific breakdown files
# (MPC votes, spending COFOG, inactivity reasons, age breakdown) --
# those have their own structure and update cadence, not the simple
# {label, unit, freq, points} series shape this check is built around.
#
# Extended from the original 18 to the full 32 (Aug 2026 data-quality
# sweep) -- the 14 added below were the same batch that was also
# missing from sitemap.xml at the time: they'd been wired into the
# visitor-facing site but never added to this operator-side monitor,
# so a silently-broken fetch for any of them would have gone
# undetected indefinitely. Keep this list in sync with FILES in
# compare.html / dashboard.html whenever a new country is added --
# see the "New-country build checklist" for the full wiring list.
DATA_FILES = {
    "UK": "data.json", "US": "data-us.json", "Eurozone": "data-ez.json", "Japan": "data-jp.json",
    "India": "data-in.json", "Canada": "data-ca.json", "Australia": "data-au.json", "South Korea": "data-kr.json",
    "Israel": "data-il.json", "Mexico": "data-mx.json", "Brazil": "data-br.json", "South Africa": "data-za.json",
    "Morocco": "data-ma.json", "Germany": "data-de.json", "France": "data-fr.json", "Italy": "data-it.json",
    "Spain": "data-es.json", "Netherlands": "data-nl.json",
    "Argentina": "data-ar.json", "Austria": "data-at.json", "Chile": "data-cl.json", "Colombia": "data-co.json",
    "Denmark": "data-dk.json", "Indonesia": "data-id.json", "Ireland": "data-ie.json", "Norway": "data-no.json",
    "Poland": "data-pl.json", "Singapore": "data-sg.json", "Sweden": "data-se.json", "Switzerland": "data-ch.json",
    "Thailand": "data-th.json", "Turkey": "data-tr.json",
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


def previous_series_points(base_dir, filename):
    """Series keys, and how many points each held, in this file as of the
    immediately preceding
    commit (before the "Refresh data" commit this run just made). Returns
    None (not an empty set) if that can't be determined -- an empty repo,
    a shallow checkout with no HEAD~1, git not on PATH, etc. -- so the
    caller can skip the comparison rather than treating "can't tell" as
    "nothing was there before"."""
    try:
        result = subprocess.run(
            ["git", "show", "HEAD~1:{}".format(filename)],
            cwd=base_dir, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        payload = json.loads(result.stdout)
        return {k: len((v or {}).get("points") or [])
                for k, v in (payload.get("series") or {}).items()}
    except Exception:
        return None


def check_disappeared_series(base_dir, country, filename, current_series):
    """Returns a list of alert dicts, one per series key that was present
    last commit and is completely absent now -- distinct from staleness:
    there's no data left at all for check_series() to even evaluate."""
    prev = previous_series_points(base_dir, filename)
    if prev is None:
        return []
    vanished = set(prev.keys()) - set(current_series.keys())
    return [
        {"country": country, "key": k, "file": filename}
        for k in sorted(vanished)
    ]


# A series can lose most of its history without disappearing: a provider
# migrates a dataflow, a fallback engages, and a decade of points is
# replaced by a handful of recent ones. Nothing above catches that, because
# the series is still present and its newest point is still fresh. This does.
TRUNCATION_RATIO = 0.75      # kept fraction below which we alert
TRUNCATION_MIN_LOSS = 5      # ignore tiny drops from ordinary revisions


def check_truncated_series(base_dir, country, filename, current_series):
    """Returns a list of alert dicts, one per series that still exists but
    holds materially fewer points than it did last commit."""
    prev = previous_series_points(base_dir, filename)
    if prev is None:
        return []
    out = []
    for key, series in current_series.items():
        was = prev.get(key)
        if not was:
            continue
        now = len((series or {}).get("points") or [])
        if now >= was * TRUNCATION_RATIO or was - now < TRUNCATION_MIN_LOSS:
            continue
        points = (series or {}).get("points") or []
        out.append({
            "country": country,
            "key": key,
            "file": filename,
            "label": (series or {}).get("label", key),
            "points_before": was,
            "points_now": now,
            "lost": was - now,
            "now_covers": "{} to {}".format(points[0][0], points[-1][0]) if points else "",
        })
    return sorted(out, key=lambda a: -a["lost"])


def run(base_dir="."):
    alerts = []
    missing_files = []
    disappeared = []
    truncated = []
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
        current_series = payload.get("series") or {}
        for key, series in current_series.items():
            alert = check_series(country, key, series)
            if alert:
                alerts.append(alert)
        disappeared.extend(check_disappeared_series(base_dir, country, filename, current_series))
        truncated.extend(check_truncated_series(base_dir, country, filename, current_series))

    alerts.sort(key=lambda a: -a["age_days"])
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
        "missing_or_unreadable_files": missing_files,
        "disappeared_series": disappeared,
        "truncated_series": truncated,
    }

    with open(os.path.join(base_dir, "freshness_alerts.json"), "w") as f:
        json.dump(result, f, indent=2)

    summary_lines = []
    if alerts or missing_files or disappeared or truncated:
        summary_lines.append("### \U0001F534 Data freshness check: {} issue(s) found\n".format(
            len(alerts) + len(missing_files) + len(disappeared) + len(truncated)))
        if truncated:
            summary_lines.append("### Series that lost most of their history this run")
            summary_lines.append("| Country | Series | Points before | Points now | Now covers |")
            summary_lines.append("|---|---|---|---|---|")
            for t in truncated:
                summary_lines.append("| {} | {} | {} | {} | {} |".format(
                    t["country"], t["label"], t["points_before"], t["points_now"], t["now_covers"]))
            summary_lines.append("")
        if disappeared:
            summary_lines.append("### Series present last run, completely gone this run")
            summary_lines.append("| Country | Series | File |")
            summary_lines.append("|---|---|---|")
            for d in disappeared:
                summary_lines.append("| {} | {} | {} |".format(
                    d["country"], d["key"], d["file"]))
            summary_lines.append("")
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
