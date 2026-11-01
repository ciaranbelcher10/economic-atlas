"""Tests for calendar_history.py (v1.9.42): past calendar events are kept.

    python3 tools/test_calendar_history.py   -> "N ok, 0 failed"

Builds throwaway git repos with dated commits of a data-calendar file, then runs
the merge as the workflow does (HEAD only) and as the one-off backfill (all
versions). Offline; the live data-calendar-*.json files are never touched.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_history as H

ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

SRC = "stats.example/releases/x (official feed)"
def ev(d, c="cpi", name=None, src=SRC, country="Testland"):
    return {"date": d, "country": country, "concept": c, "name": name or f"{c} release", "source": src, "time": "9:00am"}

class Repo:
    def __init__(self):
        self.dir = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.dir)
        self.git("init", "-q"); self.git("config", "user.email", "t@t"); self.git("config", "user.name", "t")
    def git(self, *a, date=None):
        env = dict(os.environ)
        if date: env.update(GIT_COMMITTER_DATE=f"{date}T06:00:00", GIT_AUTHOR_DATE=f"{date}T06:00:00")
        subprocess.run(["git", *a], check=True, capture_output=True, env=env)
    def commit(self, date, events, path="data-calendar-tt.json"):
        Path(path).write_text(json.dumps({"generated": date, "country": "Testland", "events": events}))
        self.git("add", path); self.git("commit", "-qm", date, date=date)
    def write(self, events, path="data-calendar-tt.json"):
        Path(path).write_text(json.dumps({"generated": "now", "country": "Testland", "events": events}))
    def events(self, path="data-calendar-tt.json"):
        return json.loads(Path(path).read_text())["events"]
    def done(self): os.chdir(self.cwd)
keys = lambda evs: sorted((e["date"], e["concept"]) for e in evs)
T = "2026-11-10"

# ---- the daily run (HEAD only)
r = Repo()
r.commit("2026-11-09", [ev("2026-11-09"), ev("2026-11-11", "jobs"), ev("2026-11-15", "gdp"), ev("2026-12-01", "trade")])
r.write([ev("2026-12-01", "trade")])        # the fetcher now lists only what is still ahead
n = H.merge_file("data-calendar-tt.json", T, False)
got = keys(r.events())
check(("2026-11-09", "cpi") in got, "yesterday's release kept")
check(("2026-11-11", "jobs") in got, "tomorrow's release kept when the source drops it early (Stats NZ case)")
check(("2026-11-15", "gdp") not in got, "a release five days ahead that the source dropped is not kept")
check(("2026-12-01", "trade") in got and n == 2, f"fetcher's list kept, two added ({n})")
check(got == sorted(got), "events sorted by date")
before = Path("data-calendar-tt.json").read_text()
check(H.merge_file("data-calendar-tt.json", T, False) == 0 and Path("data-calendar-tt.json").read_text() == before, "second run changes nothing")
r.commit("2026-11-10", r.events())
r.write([ev("2026-12-01", "trade")])
H.merge_file("data-calendar-tt.json", "2026-11-25", False)
check(("2026-11-09", "cpi") in keys(r.events()), "a kept event stays kept on later runs")
r.done()

r = Repo()
r.commit("2026-11-09", [ev("2026-11-10"), ev("2026-11-09", "jobs")])
r.write([ev("2026-11-13"), ev("2026-11-09", "jobs", name="jobs release (revised wording)")])
H.merge_file("data-calendar-tt.json", T, False)
got = r.events()
check(("2026-11-10", "cpi") not in keys(got), "a release moved a few days later is not kept on its old date")
check(sum(1 for e in got if e["concept"] == "jobs") == 1, "an event the fetcher still lists is not duplicated")
r.done()

r = Repo()
r.commit("2026-11-09", [ev("2023-01-05"), ev("2026-11-09")])
r.write([])
H.merge_file("data-calendar-tt.json", T, False)
check(keys(r.events()) == [("2026-11-09", "cpi")], "events older than three years are dropped")
r.done()

r = Repo()
r.commit("2026-11-09", [ev("2026-11-09")])
r.write([ev("2026-11-09", name="cpi release")])
raw = Path("data-calendar-tt.json").read_text()
check(H.merge_file("data-calendar-tt.json", T, False) == 0, "nothing added when the fetcher already has it")
check(Path("data-calendar-tt.json").read_text() == raw, "the file is not rewritten when nothing changes")
r.done()

# ---- backfill (all committed versions)
r = Repo()
FRED = "fred.stlouisfed.org (FRED Releases API)"
r.commit("2026-10-01", [ev("2026-10-14"), ev("2026-10-20", "gdp"), ev("2026-10-05", "fomc", src=FRED), ev("2026-10-25", "ppi")])
r.commit("2026-10-12", [ev("2026-10-14"), ev("2026-10-25", "ppi")])     # gdp withdrawn eight days ahead
r.commit("2026-10-13", [ev("2026-10-14"), ev("2026-10-25", "ppi")])
r.commit("2026-10-14", [ev("2026-10-25", "ppi")])                        # cpi dropped on its own day
r.commit("2026-10-24", [ev("2026-11-20")])                               # ppi dropped the day before (UTC)
r.write([ev("2026-11-20"), ev("2026-11-25", "gdp"), ev("2026-12-02", "ppi"), ev("2026-12-09", "fomc", src="federalreserve.gov, published schedule")])
H.merge_file("data-calendar-tt.json", T, True)
got = keys(r.events())
check(("2026-10-14", "cpi") in got, "backfill: a release dropped on its day comes back")
check(("2026-10-25", "ppi") in got, "backfill: a release dropped the evening before comes back")
check(("2026-10-20", "gdp") not in got, "backfill: a release withdrawn a week ahead does not")
check(("2026-10-05", "fomc") not in got, "backfill: dates from a since-fixed source (FRED FOMC) stay out")
check(H.source_family("ons.gov.uk/releases/cpioct (official ONS feed)") == H.source_family("ons.gov.uk/releases/gdpsep (official ONS feed)"), "per-release pages of one feed count as one source")
check(H.source_family(FRED) != H.source_family("federalreserve.gov, published schedule"), "different publishers differ")
r.done()

# ---- never breaks the run
r = Repo()
r.commit("2026-11-09", [ev("2026-11-09")])
r.write([])
Path("data-calendar-bad.json").write_text("{not json")
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = H.main([])
check(rc == 0 and "WARNING data-calendar-bad.json" in buf.getvalue(), "an unreadable file is reported and skipped")
check(Path("data-calendar-bad.json").read_text() == "{not json", "the unreadable file is left alone")
r.done()
d = tempfile.mkdtemp(); cwd = os.getcwd(); os.chdir(d)
Path("data-calendar-tt.json").write_text(json.dumps({"events": [ev("2026-12-01")]}))
with contextlib.redirect_stdout(io.StringIO()):
    rc = H.main([])
check(rc == 0 and json.loads(Path("data-calendar-tt.json").read_text())["events"] == [ev("2026-12-01")], "outside a git repo: nothing changes, no error")
os.chdir(cwd)

print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
