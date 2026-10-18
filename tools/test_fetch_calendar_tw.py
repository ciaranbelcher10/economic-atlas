"""Tests for fetch_calendar_tw.py (v1.8.16).

    python3 tools/test_fetch_calendar_tw.py   -> "N ok, 0 failed"

The fixture is a VueData object built from the probes of 19 Oct 2026: the labor force,
Manpower Utilization, advance GDP, full GDP and economic forecast entries are verbatim
for the months the probe showed; the remaining months are filled in (CONSTRUCTED), and the
consumer price index entry on page 2 is CONSTRUCTED to exercise paging and the cpi rule.
Offline, in a temp dir; the live data-calendar-tw.json is never touched.
"""
import hashlib, io, json, os, sys, tempfile, contextlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_common as C
import fetch_calendar_tw as T

LIVE = ROOT / "data-calendar-tw.json"
H0 = hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

def e(day, note, t="16:00"): return {"date": day, "time": t, "notice": note}
def months(first, extra=()):          # 12 months, first entries given, the rest empty
    m = [list(x) for x in first] + [[] for _ in range(12 - len(first))]
    for i, ents in extra: m[i] = ents
    return m

LABOR = {"name": "Labor force, number of employed persons, number of unemployed persons, not in the labor force, unemployment rate, labor force participation rate",
         "category": "Manpower Statistics ", "IsControlled": True,
         "timedatas": months([[e("23", "(Sep 2026)")], [e("23", "(Oct 2026)")], [e("22", "(Nov 2026)")], [e("25", "(Dec 2026)")], [e("25", "(Jan 2027)")]])}
UTIL = {"name": "Manpower Utilization Survey Results", "category": "Manpower Statistics", "timedatas": months([[e("23", "(May 2026)")]])}
ADV = {"name": "Advance GDP Estimates", "category": "National Accounts Statistics", "timedatas": months([[e("30", "(Q3 2026)")]])}
GDP = {"name": "Gross domestic product, national income, economic growth rate and deflator", "category": "National Accounts Statistics",
       "timedatas": months([[], [e("NLT30", "(2024 ~ Q3 2026)")]])}
FCST = {"name": "Economic forecast", "category": "Aggregate Resource Supply and Demand Forecasts", "timedatas": months([[], [e("NLT30", "(Q4 2026~2027)")]])}
CPI = {"name": "Consumer price index, wholesale price index and import price index", "category": "Price Statistics",       # CONSTRUCTED
       "timedatas": months([[e("7", "(Sep 2026)")], [e("9", "(Oct 2026)")]])}

def page(items, year=2026, month=10):
    vd = {"list": items, "isdefalt": True, "showtype": 0, "year": year, "month": month, "today": {"month": 10, "day": 19}}
    return "<html><script>window.x=1; VueData = " + json.dumps(vd) + "; new Vue({el:'#result'});</script></html>"

P1 = page([LABOR, UTIL, ADV, GDP, FCST]); P2 = page([CPI])
ev, pr, names = T.parse(P1)
got = {(x["date"], x["concept"]) for x in ev}
check(pr == [] and len(names) == 5, f"page 1 parses cleanly: {pr} {names[:2]}")
check({("2026-10-23", "jobs"), ("2026-11-23", "jobs"), ("2026-12-22", "jobs"), ("2027-01-25", "jobs"), ("2027-02-25", "jobs")} <= got,
      "labor force: Oct, Nov, Dec 2026 and the year wraps to Jan, Feb 2027")
check(("2026-10-30", "gdp") in got and ("2026-11-30", "gdp") in got, "advance GDP 30 Oct and full GDP 30 Nov")
check(not any(x["date"] == "2026-10-23" and "Utilization" in x["name"] for x in ev), "Manpower Utilization and Economic forecast not served")
check(len([x for x in ev if x["concept"] == "gdp"]) == 2, "exactly two GDP events (advance and full)")
nlt = next(x for x in ev if x["date"] == "2026-11-30")
check("published by this date at the latest" in nlt["name"] and nlt["name"].startswith("GDP, national income and deflator"), f"NLT day says so in the name: {nlt['name']}")
check(next(x for x in ev if x["date"] == "2026-10-23")["name"] == "Manpower survey: unemployment rate (Sep 2026)", "reference period kept in the name")
check(all(x["time"] == "4:00pm Taiwan time" for x in ev), "16:00 shown as 4:00pm Taiwan time")
check(T.clock("09:30") == "9:30am Taiwan time" and T.clock("12:00") == "12:00pm Taiwan time" and T.clock("") is None, "clock formatting")
check(T.parse("<html>Incapsula incident</html>")[1] != [], "planted fault caught: bot wall")
check(any("year/month" in p for p in T.parse(P1.replace('"year": 2026, ', ""))[1]), "planted fault caught: no year")
bad_day = page([{"name": LABOR["name"], "timedatas": months([[e("xx", "(Sep 2026)")]])}])
check(any("not a day" in p for p in T.parse(bad_day)[1]), "planted fault caught: day is not a number")
feb = page([{"name": LABOR["name"], "timedatas": months([[], [], [], [], [e("31", "(Jan 2027)")]])}])
check(any("not a date" in p for p in T.parse(feb)[1]), "planted fault caught: 31 February")
check(any("expected 12" in p for p in T.parse(page([{"name": LABOR["name"], "timedatas": [[]] * 14}]))[1]), "planted fault caught: more than 12 months")
check(T.classify("Consumer price index, wholesale price index and import price index") == ("cpi", "Consumer price index"), "cpi rule")

# ---- end to end, offline
class R:
    def __init__(self, body="", status=200): self.status_code, self.text = status, body
    def raise_for_status(self):
        if self.status_code >= 400: raise C.requests.HTTPError(str(self.status_code))
class S:
    def __init__(self, pages, bad_tls=False): self.pages, self.headers, self.calls, self.bad_tls, self.verifies = pages, {}, [], bad_tls, []
    def get(self, url, timeout=0, verify=True):
        self.calls.append(url); self.verifies.append(verify)
        if self.bad_tls and verify:
            raise C.requests.exceptions.SSLError("certificate verify failed: unable to get local issuer certificate")
        p = int(url.split("page=")[1].split("&")[0]); v = self.pages.get(p)
        return R(status=404) if v is None else (v if isinstance(v, R) else R(v))
class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
C.datetime = FixedDT
old = os.getcwd(); os.chdir(tempfile.mkdtemp())
try:
    sess = S({1: P1, 2: P2, 3: P2})
    C.requests.Session = lambda: sess
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = T.main()
    out = json.loads(Path(T.OUT).read_text())
    kinds = {x["concept"] for x in out["events"]}
    check(rc == 0 and out["country"] == "Taiwan" and kinds == {"jobs", "gdp", "cpi"}, f"Taiwan end to end: rc {rc}, {sorted(kinds)}")
    check(len(sess.calls) == 3, f"paging stops when a page adds nothing new: {len(sess.calls)} requests")
    check("not served" in buf.getvalue() and "Manpower Utilization" in buf.getvalue(), "log names the indicators not served")
    check(all(x["date"] >= "2026-10-18" for x in out["events"]), "only upcoming events kept")
    # missing-intermediate certificate: verified request fails first, then this one host is read unverified
    sess = S({1: P1, 2: P2, 3: P2}, bad_tls=True); C.requests.Session = lambda: sess
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): rc = T.main()
    check(rc == 0 and sess.verifies[0] is True and sess.verifies[1] is False and all(v is False for v in sess.verifies[1:]),
          f"SSL failure: verified attempt first, then unverified for this host only: {sess.verifies}")
    check(buf.getvalue().count("verification off") == 1, "the log notes the exception exactly once per run")
    check(json.loads(Path(T.OUT).read_text())["country"] == "Taiwan", "file still written after the fallback")
    class AlwaysBad(S):
        def get(self, url, timeout=0, verify=True): raise C.requests.exceptions.SSLError("still bad")
    C.requests.Session = lambda: AlwaysBad({})
    before = Path(T.OUT).read_text()
    check(T.main() == 1 and Path(T.OUT).read_text() == before, "SSL error even unverified: file untouched")
    class Reset(S):
        def get(self, url, timeout=0, verify=True): raise C.requests.exceptions.ConnectionError("reset")
    C.requests.Session = lambda: Reset({})
    check(T.main() == 1 and Path(T.OUT).read_text() == before, "other network errors do not trigger the unverified path")
    C.requests.Session = lambda: S({1: "<html>Incapsula incident</html>"})
    check(T.main() == 1 and Path(T.OUT).read_text() == before, "bot wall: file untouched")
    C.requests.Session = lambda: S({1: R("", 403)})
    check(T.main() == 1 and Path(T.OUT).read_text() == before, "403: file untouched")
    C.requests.Session = lambda: S({1: page([UTIL, ADV])})
    check(T.main() == 1 and Path(T.OUT).read_text() == before, "no labor force entry: file untouched")
finally:
    os.chdir(old)
h = hashlib.sha256(LIVE.read_bytes()).hexdigest() if LIVE.exists() else None
check(h == H0, "live data-calendar-tw.json untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
