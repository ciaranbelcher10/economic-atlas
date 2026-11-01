"""Tests for fetch_calendar_au.py (v1.9.41).

    python3 tools/test_fetch_calendar_au.py   -> "N ok, 0 failed"

Fixtures: abs_202701.html (the ABS January 2027 monthly calendar: release titles,
periods, days and 11:30am times as on the live page of 1 Nov 2026, laid out as one
row of day numbers then one row of releases per week, plus two releases placed on
February's days in the last week) and abs_202701_onecell.html (same content with
the day number inside each release cell). Offline; data-calendar-au.json untouched.
"""
import hashlib, sys
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import fetch_calendar_au as A

F = ROOT / "tools" / "fixtures" / "calendar"
LIVE = ROOT / "data-calendar-au.json"
H0 = hashlib.sha256(LIVE.read_bytes()).hexdigest()
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

WANT = {("2027-01-06", "cpi"), ("2027-01-11", "trade"), ("2027-01-21", "jobs"),
        ("2027-01-27", "cpi"), ("2027-01-29", "ppi")}
for fx in ["abs_202701.html", "abs_202701_onecell.html"]:
    ev, pr = A.parse_month((F / fx).read_text(), 2027, 1)
    got = {(e["date"], e["concept"]) for e in ev}
    check(pr == [], f"{fx}: parses cleanly {pr}")
    check(got == WANT, f"{fx}: exactly the served January releases, got {sorted(got)}")
    check(len(ev) == len(WANT), f"{fx}: no duplicates (Detailed and Updated information skipped), {len(ev)}")
    check(all(e["date"].startswith("2027-01") for e in ev), f"{fx}: February's days never dated in January")
    names = {e["concept"]: e["name"] for e in ev}
    check(names.get("ppi") == "Producer Price Indexes (December Quarter 2026)", f"{fx}: quarterly period kept: {names.get('ppi')}")
    check(all(e["time"] == "11:30am Canberra time" and e["country"] == "Australia" and e["source"].startswith("abs.gov.au") for e in ev), f"{fx}: time, country, source")
    check(not any("\u2014" in e["name"] or "--" in e["name"] for e in ev), f"{fx}: no em dashes")

page = (F / "abs_202701.html").read_text()
ev, pr = A.parse_month(page, 2027, 2)
check(ev == [] and pr and "not an ABS release-calendar page" in pr[0], "a page for the wrong month is refused")
ev, pr = A.parse_month("<html>Access denied</html>", 2027, 1)
check(ev == [] and pr, "a bot wall page is refused")
ev, pr = A.parse_month(page.split("<table")[0] + "release-calendar</body></html>", 2027, 1)
check(ev == [] and pr and "no calendar table" in pr[0], "a page with no table is refused")
check(A.releases_in("Labour Force, Australia, Detailed December 2026 - 11:30am") == [], "Labour Force Detailed not served")
check(A.releases_in("Updated information Consumer Price Index, Australia March 2027 - 11:30am") == [], "updated information skipped")
check(len(A.releases_in("International Trade in Goods and Services, Australia March 2027 - 11:30am")) == 0, "a longer title is not mistaken for a served one")
check(A.month_list(date(2026, 11, 1), 6) == [(2026,11),(2026,12),(2027,1),(2027,2),(2027,3),(2027,4)], "six months, across the year end")

# main(): keeps the old file when the site is unreachable or wrong, writes when good
import requests, json, os, tempfile
class R:
    def __init__(s, text, code=200): s.content = text.encode(); s.status_code = code
    def raise_for_status(s):
        if s.status_code >= 400: raise requests.HTTPError(str(s.status_code))
def run(get):
    cwd = os.getcwd(); d = tempfile.mkdtemp(); os.chdir(d)
    Path(A.OUT).write_text('{"events": ["old"]}')
    orig = requests.Session.get; requests.Session.get = lambda self, url, **k: get(url)
    real_dt = A.datetime
    class FakeDT(real_dt):
        @classmethod
        def now(cls, tz=None): return real_dt(2027, 1, 2, tzinfo=tz)
    A.datetime = FakeDT
    try:
        rc = A.main(); out = json.loads(Path(A.OUT).read_text())
    finally:
        requests.Session.get = orig; A.datetime = real_dt; os.chdir(cwd)
    return rc, out
def jan_only(url):
    return R(page) if url.endswith("202701") else R(page.replace("January 2027", "Other").replace("<table", "<div"))
rc, out = run(lambda u: R("blocked", 403))
check(rc == 1 and out == {"events": ["old"]}, "fetch error: existing file kept")
rc, out = run(lambda u: R("<html>JavaScript is blocked</html>"))
check(rc == 1 and out == {"events": ["old"]}, "wrong page: existing file kept")
rc, out = run(lambda u: R(page) if u.endswith("202701") else R("x", 404))
check(rc == 1 and out == {"events": ["old"]}, "a required month missing: existing file kept")
rc, out = run(lambda u: R(page) if u.endswith("202701") else R("<html>JavaScript is blocked</html>"))
check(rc == 1 and out == {"events": ["old"]}, "a required month answered with a bot wall: existing file kept")
def good(u):
    ym = u[-6:]
    if ym == "202701": return R(page)
    y, m = int(ym[:4]), int(ym[4:])
    return R(f"<html>release-calendar {A.MONTHS[m]} {y}<table><tr><td>1</td></tr><tr><td></td></tr></table></html>")
rc, out = run(good)
check(rc == 0 and {(e["date"], e["concept"]) for e in out["events"]} == WANT, f"good run writes the January releases: {rc}")
# v1.9.56: the RBA dates are merged into the file main() writes, next to the ABS releases
FX = Path(__file__).resolve().parent / "fixtures" / "calendar"
RBA_S = (FX / "rba_board_meeting_schedules_202611.html").read_text()
RBA_T = (FX / "rba_int_rate_decisions_202611.html").read_text()
rc, out = run(lambda u: R(RBA_S) if u == A.RBA_URL else R(RBA_T) if u == A.RBA_TIME_URL else good(u))
rba = [e for e in out.get("events", []) if isinstance(e, dict) and e.get("concept") == "rate_decision"]
check(rc == 0 and [e["date"] for e in rba] == ["2027-02-09", "2027-03-23", "2027-05-04", "2027-06-22", "2027-08-10",
      "2027-09-28", "2027-11-02", "2027-12-14"] and rba[0]["time"] == "2:30pm Sydney time",
      f"RBA decisions after 2 Jan 2027 are written with the ABS releases: {[e['date'] for e in rba]}")
check(any(e.get("concept") == "cpi" for e in out.get("events", []) if isinstance(e, dict)), "ABS releases still written alongside")
check(out.get("country") == "Australia" and "generated" in out, "file shape")
check(hashlib.sha256(LIVE.read_bytes()).hexdigest() == H0, "live data-calendar-au.json untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
