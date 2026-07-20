"""Fetch the Bank of England's official MPC voting-history spreadsheet and
write data-uk-mpc-votes.json: per-meeting vote breakdowns (how many members
backed the decision vs. each alternative), for the Inflation tab's MPC
vote-record module.

Run:  python3 fetch_boe_mpc.py
No API key needed -- this is a public file download, no auth.

SOURCE: https://www.bankofengland.co.uk/-/media/boe/files/monetary-policy-
summary-and-minutes/mpcvoting.xlsx

CONFIRMED LIVE (2026-07-20, after two rounds of diagnostic dumps -- this
sandbox can't reach bankofengland.co.uk directly, so the real layout could
only be read via log output from a live GitHub Actions run, not inspected
locally). The workbook has 4 sheets; the first, "Bank Rate Decisions", is
laid out like this:

  Row with "Current members" (col C) -> member-name header row. Columns
    D onward are each CURRENT committee member's name, up to (but not
    including) the column holding "Past members", where past members'
    names continue.
  Rows 6-9 below that: a LIFETIME summary per member (career totals of
    votes to increase/maintain/reduce, and total meetings) -- not used
    here, this script wants per-meeting data.
  Row with "Bank Rate" (col C) -> section anchor. The row right after it
    is a baseline rate with no date (skipped automatically since it has
    no date). Every row after THAT is one meeting:
      col B = meeting date (a real datetime cell)
      col C = the decided Bank Rate for that meeting, as a decimal
        fraction (0.0625 = 6.25%) -- multiply by 100 for a percentage
      cols D onward (same columns as the member-header row) = that
        member's individually voted-for rate, same fraction format,
        blank if they weren't sitting on the committee at that meeting

None of the past-members' columns are read -- this only uses the
"current members" block, which is sufficient for recent meetings (every
sitting member's tenure started 2017 or later; anyone who left before
that is already out of scope for "recent meetings" anyway). Meetings
during a committee transition (i.e. right as an old member is replaced by
a new one, if the departing member isn't in the current-members block)
may show one fewer vote than the true total for that single meeting --
a known, minor, accepted edge case rather than something worth building
a full past-members crosswalk for.

WHY NO NAMED INDIVIDUAL VOTES IN THE OUTPUT (yet): the source data does
give each member's individual vote, but before publishing real people's
individual votes, the parsed output should be spot-checked against the
Bank's own published Monetary Policy Summary text (which independently
states the same majority breakdown) at least once, given how much worse
misattributing a real, identifiable person's vote is than an
approximation elsewhere on the site. This cut only emits AGGREGATE counts
per meeting (hold/hike/cut), cross-checkable against that published text.
Names can be added once that spot-check happens.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone

import requests

VOTING_XLSX_URL = ("https://www.bankofengland.co.uk/-/media/boe/files/"
                    "monetary-policy-summary-and-minutes/mpcvoting.xlsx")

SHEET_NAME = "Bank Rate Decisions"
HISTORY_LIMIT = 400  # generous cap, not a real limit -- the spreadsheet's full
# history goes back to 1997 (~300-350 meetings depending on frequency changes
# over time); this just guards against something going wrong and returning
# an absurd number. The frontend decides how much to actually show (2 years
# by default, "show more" to reveal the rest) -- this script's job is to
# hand over everything available.


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _find_anchor(ws, target: str) -> tuple[int, int] | None:
    """Find the (row, col) of a cell whose value equals `target` exactly
    (after stripping whitespace), scanning the whole sheet. Used instead
    of hardcoding row/col numbers so a future reshuffle of the sheet
    (extra row inserted, etc.) doesn't silently break this."""
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip() == target:
                return cell.row, cell.column
    return None


def fetch_and_parse() -> list[dict] | None:
    try:
        r = requests.get(VOTING_XLSX_URL, timeout=60,
                         headers={"User-Agent": "economic-atlas/0.1"})
        print(f"  [boe-mpc] status={r.status_code}")
        r.raise_for_status()
    except Exception as exc:
        print(f"  [boe-mpc] request failed: {exc}")
        return None

    try:
        import openpyxl
    except ImportError:
        print("  [boe-mpc] openpyxl not installed — skipping")
        return None

    try:
        wb = openpyxl.load_workbook(io.BytesIO(r.content), data_only=True)
    except Exception as exc:
        print(f"  [boe-mpc] couldn't open as xlsx: {exc}")
        return None

    if SHEET_NAME not in wb.sheetnames:
        print(f"  [boe-mpc] sheet '{SHEET_NAME}' not found; sheets present: {wb.sheetnames}")
        return None
    ws = wb[SHEET_NAME]
    print(f"  [boe-mpc] sheet '{ws.title}': {ws.max_row} rows x {ws.max_column} cols")

    member_anchor = _find_anchor(ws, "Current members")
    past_anchor = _find_anchor(ws, "Past members")
    rate_anchor = _find_anchor(ws, "Bank Rate")
    if not member_anchor or not rate_anchor:
        print(f"  [boe-mpc] couldn't find expected anchors "
              f"(Current members={member_anchor}, Bank Rate={rate_anchor}) — layout changed")
        return None

    member_row, member_start_col = member_anchor
    member_end_col = past_anchor[1] if past_anchor else ws.max_column + 1
    member_cols = list(range(member_start_col + 1, member_end_col))
    member_names = [ws.cell(row=member_row, column=c).value for c in member_cols]
    print(f"  [boe-mpc] {len(member_cols)} current members: {member_names}")

    rate_row, rate_col = rate_anchor
    date_col = rate_col - 1
    data_start_row = rate_row + 1  # the row right after is a no-date baseline, skipped naturally
    print(f"  [boe-mpc] date col={date_col}, rate col={rate_col}, data starts row {data_start_row}")

    meetings = []
    for row_idx in range(data_start_row, ws.max_row + 1):
        raw_date = ws.cell(row=row_idx, column=date_col).value
        if not hasattr(raw_date, "strftime"):
            continue
        decision = _to_float(ws.cell(row=row_idx, column=rate_col).value)
        if decision is None:
            continue
        decision_pct = round(decision * 100, 4)

        hold = hike = cut = 0
        for c in member_cols:
            voted = _to_float(ws.cell(row=row_idx, column=c).value)
            if voted is None:
                continue
            voted_pct = voted * 100
            if abs(voted_pct - decision_pct) < 1e-6:
                hold += 1
            elif voted_pct > decision_pct:
                hike += 1
            else:
                cut += 1
        total_votes = hold + hike + cut
        if total_votes == 0:
            continue  # no current-member data for this (likely older) meeting

        meetings.append({
            "date": raw_date.strftime("%Y-%m-%d"), "decision_rate": decision_pct,
            "hold": hold, "hike": hike, "cut": cut, "total_votes": total_votes,
        })

    if not meetings:
        print("  [boe-mpc] found anchors but parsed 0 meetings with current-member vote data")
        return None

    meetings.sort(key=lambda m: m["date"], reverse=True)
    for i, m in enumerate(meetings):
        m["previous_rate"] = meetings[i + 1]["decision_rate"] if i + 1 < len(meetings) else None

    latest = meetings[0]
    print(f"  [boe-mpc] {len(meetings)} meetings parsed, latest {latest['date']} "
          f"({latest['hold']}-{latest['hike']}-{latest['cut']}, rate {latest['decision_rate']}%)")
    return meetings[:HISTORY_LIMIT]


def main() -> int:
    meetings = fetch_and_parse()
    if not meetings:
        print("FAIL  boe-mpc  no usable data — leaving any previously-fetched file in place")
        return 0

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Bank of England, official MPC voting-history spreadsheet",
        "meetings": meetings,
    }
    with open("data-uk-mpc-votes.json", "w") as f:
        json.dump(out, f)
    print(f"  ok  boe-mpc  wrote {len(meetings)} meetings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
