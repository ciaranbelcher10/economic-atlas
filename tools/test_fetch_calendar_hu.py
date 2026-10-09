"""Offline tests for fetch_calendar_hu.py (v1.7.35) against the MNB Monetary
Council page exactly as served on 9 Oct 2026 (tools/fixtures/calendar/
mnb_monetary_council.html). Run: python3 tools/test_fetch_calendar_hu.py"""
from __future__ import annotations

import hashlib, io, json, os, sys, tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LIVE = ROOT / "data-calendar-hu.json"
H0 = hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None
import fetch_calendar_hu as F  # noqa: E402

OK, BAD = [0], []
def check(c, m):
    if c: OK[0] += 1
    else: BAD.append(m); print("FAIL", m)

PAGE = (ROOT / "tools" / "fixtures" / "calendar" / "mnb_monetary_council.html").read_text(encoding="utf-8")
ev, prob = F.parse_mnb(PAGE)
d = sorted(e["date"] for e in ev)
check(not prob, f"page parses cleanly: {prob}")
check([x for x in d if x.startswith("2026")] == ["2026-01-27", "2026-02-24", "2026-03-24", "2026-04-28", "2026-05-26", "2026-06-23",
      "2026-07-21", "2026-08-25", "2026-09-22", "2026-10-20", "2026-11-17", "2026-12-15"], f"2026: the twelve policy meetings: {d}")
check([x for x in d if x.startswith("2027")] == ["2027-02-16", "2027-03-23", "2027-05-04", "2027-06-22", "2027-08-03",
      "2027-09-21", "2027-11-09", "2027-12-14"], "2027: the eight policy meetings")
check(not any(x in d for x in ("2026-01-13", "2026-10-06", "2027-01-19")), "non-policy (NP) meetings left out")
check(not any(x.startswith("2025") for x in d), "the minutes table (with 2025 meetings) is not read as a schedule")
check(all(e["time"] == "2:00pm Budapest time" and e["concept"] == "rate_decision" for e in ev), "2pm rate decisions")
_, p = F.parse_mnb("<html>moved</html>")
check(p and "no 'scheduled meetings" in p[0], "a page without the schedule is refused")
_, p = F.parse_mnb(PAGE.replace("17 November (P)", "21 November (P)"))
check(any("not a weekday" in x for x in p), "a weekend date is refused")
_, p = F.parse_mnb(PAGE.replace("(P)", "(X)"))
check(any("policy meetings found" in x for x in p), "a schedule with no policy meetings is refused")

class R:
    def __init__(s, body=b"", code=200): s.content, s.status_code = body, code
    def raise_for_status(s):
        if s.status_code >= 400: raise F.requests.HTTPError(str(s.status_code))
def run(prev=None, ok=True):
    tmp = tempfile.mkdtemp(); cwd = os.getcwd()
    try:
        os.chdir(tmp)
        if prev: Path(F.OUT).write_text(json.dumps(prev))
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = F.main(today=date(2026, 10, 9), get=lambda u, **k: R(PAGE.encode()) if ok else R(code=403))
        return rc, (json.loads(Path(F.OUT).read_text()) if Path(F.OUT).exists() else None)
    finally:
        os.chdir(cwd)
rc, out = run()
check(rc == 0 and [e["date"] for e in out["events"]][:3] == ["2026-10-20", "2026-11-17", "2026-12-15"] and len(out["events"]) == 11,
      f"upcoming only, 3 left in 2026 plus 8 in 2027: {len(out['events']) if out else None}")
rc2, out2 = run(prev={"events": [{"date": "2026-11-17", "name": "keep"}]}, ok=False)
check(rc2 == 1 and out2["events"][0]["name"] == "keep", "blocked: exits 1, existing file untouched")
check((hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None) == H0, "live file untouched")
print(f"{OK[0]} ok, {len(BAD)} failed")
sys.exit(1 if BAD else 0)
