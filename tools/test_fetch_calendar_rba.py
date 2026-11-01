"""v1.9.56: RBA Monetary Policy Board decision dates on the Australia calendar.

    python3 tools/test_fetch_calendar_rba.py   -> "N ok, 0 failed"

Fixtures are the live RBA markup from probes rba1 and rba2 (1 Nov 2026). Offline; the live
data-calendar-au.json is never touched.
"""
import hashlib, io, json, os, sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_calendar_au as AU  # noqa: E402
import requests  # noqa: E402

F = ROOT / "tools" / "fixtures" / "calendar"
SCHED = (F / "rba_board_meeting_schedules_202611.html").read_text()
TIMEP = (F / "rba_int_rate_decisions_202611.html").read_text()
LIVE = hashlib.sha256((ROOT / "data-calendar-au.json").read_bytes()).hexdigest()
ok = bad = 0
def check(c, n):
    global ok, bad
    if c: ok += 1
    else: bad += 1; print("FAIL", n)

label = AU.rba_time(TIMEP)
check(label == "2:30pm Sydney time", f"time read from the RBA's own sentence: {label!r}")
check(AU.rba_time("<p>Nothing about times here.</p>") == "", "no sentence, no time")

ev, pr = AU.parse_rba(SCHED, label)
dates = [e["date"] for e in ev]
want = ["2026-02-03", "2026-03-17", "2026-05-05", "2026-06-16", "2026-08-11", "2026-09-29", "2026-11-03", "2026-12-08",
        "2027-02-09", "2027-03-23", "2027-05-04", "2027-06-22", "2027-08-10", "2027-09-28", "2027-11-02", "2027-12-14"]
check(pr == [], f"parses cleanly: {pr}")
check(dates == want, f"16 decisions, each on the meeting's second day: {dates}")
check("2026-11-03" in dates and "2026-12-08" in dates, "Jess's 3 November and 8 December are there")
check(not {"2026-03-05", "2026-06-04", "2026-11-19", "2027-02-24"} & set(dates), "Payments System Board meetings are left out")
check(all(e["concept"] == "rate_decision" and e["country"] == "Australia" and e["time"] == "2:30pm Sydney time"
          and e["source"] == AU.RBA_SRC for e in ev), "event fields")
check(all("\u2014" not in e["name"] for e in ev), "no em dashes")
ev2, _ = AU.parse_rba(SCHED, "")
check(all("time" not in e for e in ev2), "without a time sentence, dates only")

# what the checks catch
check(AU.parse_rba("<html>JavaScript is blocked</html>")[1], "a wall page is a problem")
check(any("not 'Monetary Policy Board'" in p for p in AU.parse_rba(SCHED.replace(">Monetary Policy Board<", ">Payments System Board<"))[1]),
      "swapped columns are caught")
check(any("not in its row's month" in p for p in AU.parse_rba(SCHED.replace("<td>2&ndash;3 November</td>", "<td>2&ndash;3 December</td>"))[1]),
      "a meeting in the wrong row is caught")
check(any("not read" in p for p in AU.parse_rba(SCHED.replace("<td>7&ndash;8 December</td>", "<td>TBC</td>"))[1]),
      "an unreadable cell is caught")
few = SCHED
for c in ["2&ndash;3 February", "16&ndash;17 March", "4&ndash;5 May"]:
    few = few.replace(f"<td>{c}</td>", "<td></td>", 1)
check(any("meetings; the RBA holds 8" in p for p in AU.parse_rba(few)[1]), "a year with too few meetings is caught")
check(AU.parse_rba(SCHED.replace("<td>2&ndash;3 November</td>", "<td>31 October&ndash;1 November</td>"))[1] == [],
      "a meeting spanning two months is read by its end date")

# a month with only a Payments System Board meeting is skipped, not an error
psb_only = SCHED.replace("<td>8&ndash;9 February</td>", "<td></td>")
ev3, pr3 = AU.parse_rba(psb_only)
check(pr3 == [] and "2027-02-09" not in [e["date"] for e in ev3] and len(ev3) == 15, f"empty board cell skipped cleanly: {pr3}")

# fetch_rba: never raises, keeps what is on file when the RBA cannot be read
class R:
    def __init__(s, text, code=200): s.content, s.status_code, s.ok = text.encode(), code, code == 200
    def raise_for_status(s):
        if s.status_code != 200: raise requests.HTTPError(str(s.status_code))
class S:
    def __init__(s, sched, timep): s.map = {AU.RBA_URL: sched, AU.RBA_TIME_URL: timep}
    def get(s, url, timeout=None):
        v = s.map[url]
        if isinstance(v, Exception): raise v
        return v
prev = [{"date": "2026-12-08", "concept": "rate_decision", "name": "old"}, {"date": "2026-09-29", "concept": "rate_decision"},
        {"date": "2026-11-19", "concept": "jobs"}]
got, note = AU.fetch_rba(S(R(SCHED), R(TIMEP)), prev, "2026-11-01")
check(len(got) == 16 and note.startswith("RBA: 10 upcoming"), f"live read: {note}")
got, note = AU.fetch_rba(S(R("", 403), R(TIMEP)), prev, "2026-11-01")
check([e["name"] for e in got] == ["old"] and note.startswith("WARNING RBA: HTTPError"), f"403: keeps future RBA dates on file only: {note}")
got, note = AU.fetch_rba(S(R("<html>JavaScript is blocked</html>"), R(TIMEP)), prev, "2026-11-01")
check(len(got) == 1 and "bot wall" in note and "sample" in note, f"wall page: kept, and the log shows what came back")
got, note = AU.fetch_rba(S(R(SCHED), requests.ConnectionError("x")), prev, "2026-11-01")
check(len(got) == 16 and "time" not in got[0] and "dates only" in note, "time page down: dates still go on")

got, note = AU.fetch_rba(S(R("", 403), R(TIMEP)), ["junk", 3, None, {"date": 5}], "2026-11-01")
check(got == [] and note.startswith("WARNING RBA"), "a malformed saved file cannot break the run")
got, note = AU.fetch_rba(S(R("", 403), R(TIMEP)), {"not": "a list"}, "2026-11-01")
check(got == [], "a saved file that is not a list is ignored")

# main(): ABS behaviour unchanged, RBA merged in, ABS failure still writes nothing
src = open(ROOT / "fetch_calendar_au.py", encoding="utf-8").read()
main = src[src.index("def main()"):]
check(main.index("if problems:") < main.index("fetch_rba(s, previous, t0)") < main.index("json.dump("),
      "RBA is read after the ABS checks pass and before the file is written")
check("Not served: RBA" not in src, "the old 'not served' note is gone")
check(hashlib.sha256((ROOT / "data-calendar-au.json").read_bytes()).hexdigest() == LIVE, "live calendar file untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
