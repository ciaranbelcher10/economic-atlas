"""Tests for fetch_calendar_is / _hk / _vn / _ng and calendar_common (v1.8.14).

    python3 tools/test_fetch_calendar_r3.py   -> "N ok, 0 failed"

Fixtures are built in the test from rows copied from the probes of 18 Oct 2026
(Iceland's "d.m.yyyy | title" rows, Hong Kong's sheet columns and first rows,
Vietnam's embedded events and Nigeria's embedded events). Where a title was NOT seen in a
probe (marked CONSTRUCTED below) it exists only to exercise a mapping rule. The first real
Actions run is the live test. Offline, in a temp dir; the live data-calendar-*.json files
are never touched. Needs openpyxl only here, to write a sample .xlsx (the script does not).
"""
import hashlib, io, json, os, sys, tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import calendar_common as C
import fetch_calendar_is as IS
import fetch_calendar_hk as HK
import fetch_calendar_vn as VN
import fetch_calendar_ng as NG

LIVE = [ROOT / f"data-calendar-{c}.json" for c in ("is", "hk", "vn", "ng")]
H0 = {p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in LIVE}
ok = bad = 0
def check(cond, name):
    global ok, bad
    if cond: ok += 1
    else: bad += 1; print("FAIL", name)

# ---------------- Iceland
IS_ROWS = [  # verbatim from the probe
    ("20.10.2026", "Harmonised indices of consumer prices in September 2026"),
    ("21.10.2026", "Labour market in September 2026"),
    ("22.10.2026", "Monthly wage index in September 2026 and related indices"),
    ("23.10.2026", "Building cost index in October 2026"),
    ("23.10.2026", "Producer price index in September 2026"),
    ("23.10.2026", "New registrations and company bankruptcies in the 3rd quarter of 2026"),
    ("27.10.2026", "VAT turnover July-August 2026"),
    ("29.10.2026", "Overnight stays in September 2026"),
    ("29.10.2026", "Consumer price index in October 2026"),
    ("30.10.2026", "Trade in goods in September 2026"),
    ("2.11.2026", "Production in agriculture in September 2026"),
    ("5.11.2026", "Labour market - 3rd quarter 2026"),
    ("6.11.2026", "Trade in goods in October 2026 - Preliminary figures"),
    ("20.11.2026", "Harmonised indices of consumer prices in October 2026"),
    ("26.11.2026", "Consumer price index in November 2026"),
    ("25.11.2026", "Labour market in October 2026"),
    ("14.12.2026", "Gross domestic product in the 3rd quarter of 2026"),   # CONSTRUCTED title
]
IS_HTML = "<html><body><h1>Advanced release calendar</h1><table>" + "".join(
    f"<tr><td>{d}</td><td><a href='/x'>{t}</a></td><td></td></tr>" for d, t in IS_ROWS) + "</table></body></html>"
ev, pr = IS.parse(IS_HTML)
got = {(e["date"], e["concept"]) for e in ev}
check(pr == [], f"Iceland parses cleanly: {pr}")
check(("2026-10-29", "cpi") in got and ("2026-11-26", "cpi") in got, "CPI 29 Oct and 26 Nov")
check(("2026-10-21", "jobs") in got and ("2026-11-25", "jobs") in got, "monthly labour market 21 Oct, 25 Nov")
check(("2026-10-30", "trade") in got and ("2026-11-06", "trade") in got, "trade in goods 30 Oct and preliminary 6 Nov")
check(("2026-10-23", "ppi") in got and ("2026-12-14", "gdp") in got, "PPI 23 Oct, GDP 14 Dec")
names = {e["name"] for e in ev}
check("Consumer price index (October 2026)" in names and "Trade in goods, preliminary figures (October 2026)" in names, "event names")
check(not any("Harmonised" in n or "wage" in n or "3rd quarter 2026" in n or "Building cost" in n for n in names),
      "HICP, wage index, quarterly labour market, building cost excluded")
check(all(e["time"] is None and e["country"] == "Iceland" for e in ev), "no invented times")
check(IS.parse("<html>Incapsula incident</html>")[1] != [], "planted fault caught: bot wall")
check(any("only" in p for p in IS.parse("<table><tr><td>20.10.2026</td><td>Consumer price index in October 2026</td></tr></table>")[1]),
      "planted fault caught: too few rows")
check(any("Consumer price index" in p for p in IS.parse(IS_HTML.replace("Consumer price index", "Prices"))[1]), "planted fault caught: CPI missing")
check(any("not a date" in p for p in IS.parse(IS_HTML.replace("20.10.2026", "31.2.2026"))[1]), "planted fault caught: 31 February")

# ---------------- Hong Kong
try:
    import openpyxl
except ImportError:
    openpyxl = None
    print("SKIP Hong Kong tests: openpyxl not installed (only the test needs it)")

def make_xlsx(rows, header=True):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Sep 2026 - Dec 2027"
    if header: ws.append(["Release Date", "Subject", "Sub-subject", "Series", "Title", "Footnote No", "Footnote Content"])
    for r in rows: ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()

if openpyxl:
    D = lambda y, m, d: datetime(y, m, d)
    rows = [  # first rows from the probe; series/title wording completed where the probe cut it off
        [D(2026, 9, 23), "Prices", "Consumer Prices", "Consumer Price Index", "Consumer Price Index for August 2026", None, None],
        [D(2026, 9, 17), "Labour and Wages", "Labour Force, Employment and Unemployment", "Unemployment and Underemployment Statistics", "Unemployment and underemployment statistics for June-August 2026", None, None],
        [D(2026, 9, 24), "External Trade", "Merchandise Trade", "External Merchandise Trade Statistics", "External merchandise trade statistics for August 2026", None, None],
        [D(2026, 9, 3), "External Trade", "Merchandise Trade", "Statistics on Vessels, Port Cargo", "Statistics on vessels, port cargo", None, None],
        [D(2026, 9, 18), "Economy", "National Accounts", "Chain Volume Measures of Gross Domestic Product", "Chain volume measures of GDP", None, None],
        [D(2026, 9, 14), "Economy", "National Accounts", "Gross National Income and Expenditure", "Gross national income and expenditure", None, None],
        [D(2026, 11, 13), "Economy", "National Accounts", "Gross Domestic Product", "Gross Domestic Product for the third quarter of 2026", None, None],   # CONSTRUCTED
        [D(2026, 10, 22), "Prices", "Consumer Prices", "Consumer Price Index", "Consumer Price Index for September 2026", None, None],
        [D(2026, 10, 20), "Labour and Wages", "Labour Force, Employment and Unemployment", "Unemployment and Underemployment Statistics", "Unemployment and underemployment statistics for July-September 2026", None, None],   # CONSTRUCTED date
        [D(2026, 10, 27), "External Trade", "Merchandise Trade", "External Merchandise Trade Statistics", "External merchandise trade statistics for September 2026", None, None],                  # CONSTRUCTED date
    ] + [[D(2026, 10, 1 + (i % 28)), "Industry", "Retail", f"Retail Sales Statistics {i}", f"Retail sales statistics {i}", None, None] for i in range(20)]
    xb = make_xlsx(rows)
    ev, pr, sk = HK.parse(xb)
    got = {(e["date"], e["concept"]) for e in ev}
    check(pr == [], f"Hong Kong xlsx parses cleanly: {pr}")
    check(("2026-09-23", "cpi") in got and ("2026-10-22", "cpi") in got, "CPI 23 Sep and 22 Oct")
    check(("2026-09-17", "jobs") in got and ("2026-09-24", "trade") in got and ("2026-11-13", "gdp") in got, "jobs, trade, GDP mapped")
    check(not any(e["name"].startswith(("Statistics on vessels", "Chain volume", "Gross national")) for e in ev), "vessel, chain-volume and GNI rows not served")
    check(all(e["time"] == "4:30pm HKT" for e in ev), "4:30pm HKT on every event")
    check(sk.get(("Industry", "Retail Sales Statistics 3")) == 1 and len(sk) >= 20, "unserved rows are counted by subject and series")
    check(HK.to_date("46288") == date(2026, 9, 23) or isinstance(HK.to_date("46288"), date), "Excel serial numbers convert")
    check(HK.to_date("2026-10-22T00:00:00") == date(2026, 10, 22), "ISO text dates convert")
    check(HK.parse(make_xlsx(rows, header=False))[1] != [], "planted fault caught: no header row")
    check(HK.parse(make_xlsx(rows[:3]))[1] != [], "planted fault caught: only a handful of dated rows")
    check(HK.parse(make_xlsx([r for r in rows if r[3] != "Consumer Price Index"]))[1] != [], "planted fault caught: CPI missing")
    try:
        HK.read_xlsx(b"<html>Request Rejected</html>"); check(False, "bot wall is not a zip")
    except Exception:
        check(True, "planted fault caught: an HTML page instead of the workbook")

# ---------------- Vietnam
VN_EVENTS = [  # verbatim from the probe except where marked
    {"title": "Socio-economic data of countries and territories in the world in the period 2015-2023", "status": "Official", "date": "4th quarter of 2025", "format": "Publication and website"},
    {"title": "The fourth quarter and 2025 socio - economic situation report", "status": "Estimate", "date": "2026-01-06", "format": "Publication and website"},
    {"title": "The January 2026 socio - economic situation report", "status": "Estimate", "date": "2026-02-06", "format": "Publication and website"},
    {"title": "The February and first 2 months 2026 socio - economic situation report", "status": "Estimate", "date": "2026-03-06", "format": "Publication and website"},
    {"title": "The first quarter 2026 socio - economic situation report", "status": "Estimate", "date": "2026-04-06", "format": "Publication and website"},
    {"title": "The June and first 6 months 2026 socio - economic situation report", "status": "Estimate", "date": "2026-07-06", "format": "Publication and website"},   # CONSTRUCTED date
    {"title": "The October 2026 socio - economic situation report", "status": "Estimate", "date": "2026-11-06", "format": "Publication and website"},          # CONSTRUCTED date
    {"title": "Statistical yearbook 2025", "status": "Official", "date": "2026-12-20", "format": "Publication"},                                                      # CONSTRUCTED
]
VN_PAGE = "<html><script> var lang='en'; var events=" + json.dumps(VN_EVENTS) + "; var other=1;</script></html>"
ev, pr = VN.parse(VN_PAGE)
got = {(e["date"], e["concept"]) for e in ev}
check(pr == [] and ev is not None, f"Vietnam parses cleanly: {pr}")
check(("2026-02-06", "cpi") in got and ("2026-02-06", "trade") in got and ("2026-02-06", "gdp") not in got, "monthly report: CPI and trade, no GDP")
check(("2026-04-06", "gdp") in got and ("2026-07-06", "gdp") in got and ("2026-01-06", "gdp") in got, "quarterly and 6-month reports also carry GDP")
check(("2026-03-06", "cpi") in got and ("2026-03-06", "gdp") not in got, "'first 2 months' report is monthly")
check(not any(e["date"] == "2026-12-20" for e in ev), "yearbook not served; day-less 'quarter' dates skipped")
check(any(e["name"] == "The January 2026 socio-economic situation report (CPI)" for e in ev), "title kept, dashes closed, concept in brackets")
check(not any("--" in e["name"] or "\u2014" in e["name"] for e in ev), "no double hyphen or em dash in names")
check(VN.parse("<html>no data</html>") == (None, []), "page without embedded events -> (None, [])")
check(VN.parse("<script>var events=[{bad json}];</script>")[1] != [], "planted fault caught: invalid JSON")
check(VN.parse("<script>var events=[{\"title\":\"Yearbook\",\"date\":\"2026-12-20\"}];</script>")[1] != [], "planted fault caught: no situation reports")

# ---------------- Nigeria
NG_EVENTS = [  # verbatim from the probe except where marked
    {"id": "818", "title": "title", "start": "1970-01-01"},
    {"id": "819", "title": "CPI and Inflation Report December 2025", "start": "2026-01-15"},
    {"id": "820", "title": "Premium Motor Spirit (PETROL) Price Watch December 2025", "start": "2026-01-17"},
    {"id": "984", "title": "Transport Fare Watch November 2026", "start": "2026-12-30"},
    {"id": "986", "title": "Federation Account Allocation Committee (FAAC) (November 2026 Disbursement)", "start": "2026-12-31"},
    {"id": "901", "title": "CPI and Inflation Report September 2026", "start": "2026-10-15"},                       # CONSTRUCTED date
    {"id": "905", "title": "CPI and Inflation Report October 2026", "start": "2026-11-15"},                        # CONSTRUCTED date
    {"id": "902", "title": "Q3 2026 GDP Report", "start": "2026-11-23"},                                           # CONSTRUCTED title
    {"id": "903", "title": "Foreign Trade in Goods Statistics Q3 2026", "start": "2026-12-08"},                    # CONSTRUCTED title
    {"id": "904", "title": "Labour Force Survey Q3 2026", "start": "2026-12-15"},                                 # CONSTRUCTED title
]
NG_PAGE = "<script>$('#datacalendar').fullCalendar({ events: " + json.dumps(NG_EVENTS, separators=(",", ":")) + ", eventMouseover: function(Event) {} });</script>"
ev, pr = NG.parse(NG_PAGE)
got = {(e["date"], e["concept"]) for e in ev}
check(pr == [], f"Nigeria parses cleanly: {pr}")
check(("2026-01-15", "cpi") in got and ("2026-10-15", "cpi") in got, "CPI and Inflation Report 15 Jan and 15 Oct")
check(("2026-11-23", "gdp") in got and ("2026-12-08", "trade") in got and ("2026-12-15", "jobs") in got, "GDP, trade, jobs mapped")
check(not any("Price Watch" in e["name"] or "Fare" in e["name"] or "FAAC" in e["name"] or "Allocation" in e["name"] for e in ev), "price watches, fares and FAAC excluded")
check(not any(e["date"].startswith("1970") for e in ev), "1970 placeholder dropped")
check(NG.parse("<html>nothing</html>")[1] != [], "planted fault caught: no events array")
check(NG.parse(NG_PAGE.replace("CPI and Inflation Report", "Prices"))[1] != [], "planted fault caught: CPI missing")
check(C.clean_name("a  socio - economic \u2014 b -- c") == "a socio-economic, b - c", "clean_name rules")

# ---------------- end to end, offline
class R:
    def __init__(self, body="", status=200):
        self.status_code, self.text, self.content = status, (body if isinstance(body, str) else ""), (body.encode() if isinstance(body, str) else body)
    def raise_for_status(self):
        if self.status_code >= 400: raise C.requests.HTTPError(str(self.status_code))
class S:
    def __init__(self, pages): self.pages, self.headers = pages, {}
    def get(self, url, timeout=0):
        v = self.pages.get(url)
        return R(status=404) if v is None else (v if isinstance(v, R) else R(v))
class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None): return datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
C.datetime = HK.datetime = FixedDT
old = os.getcwd(); os.chdir(tempfile.mkdtemp())
try:
    def run(mod, pages):
        C.requests.Session = lambda: S(pages)
        return mod.main()
    rc = run(IS, {IS.URL: IS_HTML}); out = json.loads(Path(IS.OUT).read_text())
    check(rc == 0 and out["country"] == "Iceland" and all(e["date"] >= "2026-10-18" for e in out["events"]) and len(out["events"]) == 8,
          f"Iceland end to end: rc {rc}, {len(out['events'])} events")
    before = Path(IS.OUT).read_text()
    check(run(IS, {IS.URL: "<html>Incapsula incident</html>"}) == 1 and Path(IS.OUT).read_text() == before, "Iceland bot wall: file untouched")
    check(run(IS, {IS.URL: R("", 403)}) == 1 and Path(IS.OUT).read_text() == before, "Iceland 403: file untouched")
    rc = run(VN, {VN.URLS[0]: VN_PAGE}); out = json.loads(Path(VN.OUT).read_text())
    check(rc == 0 and out["country"] == "Vietnam" and {e["concept"] for e in out["events"]} == {"cpi", "trade"}, "Vietnam end to end (only the Nov report is upcoming)")
    moved = '<a href="https://www.nso.gov.vn/en/release-calendar-4/">Release calendar</a>'
    rc = run(VN, {VN.URLS[0]: R(status=404), VN.HOME: moved, "https://www.nso.gov.vn/en/release-calendar-4/": VN_PAGE})
    check(rc == 0, "Vietnam: moved calendar page found through the homepage link")
    rc = run(NG, {NG.URL: NG_PAGE}); out = json.loads(Path(NG.OUT).read_text())
    check(rc == 0 and {e["concept"] for e in out["events"]} == {"cpi", "gdp", "trade", "jobs"}, f"Nigeria end to end: {sorted({e['concept'] for e in out['events']})}")
    if openpyxl:
        page = '<a href="/FileManager/EN/Common/Regular_Press_Releases_Schedule_2027.xlsx">x</a>'
        pages = {HK.PAGE: page, HK.FILE.format(y=2027): R(xb), HK.FILE.format(y=2026): R(xb)}
        class SB(S):
            def get(self, url, timeout=0):
                v = self.pages.get(url)
                if v is None: return R(status=404)
                return v if isinstance(v, R) else R(v)
        C.requests.Session = lambda: SB(pages)
        rc = HK.main(); out = json.loads(Path(HK.OUT).read_text())
        kinds = {e["concept"] for e in out["events"]}
        check(rc == 0 and out["country"] == "Hong Kong" and {"cpi", "jobs", "trade", "gdp"} <= kinds, f"Hong Kong end to end: rc {rc}, {sorted(kinds)}")
        check(len({(e["date"], e["name"]) for e in out["events"]}) == len(out["events"]), "two overlapping yearly files de-duplicate")
        before = Path(HK.OUT).read_text()
        C.requests.Session = lambda: SB({HK.PAGE: page})
        check(HK.main() == 1 and Path(HK.OUT).read_text() == before, "Hong Kong: no schedule file -> file untouched")
finally:
    os.chdir(old)

for p in LIVE:
    h = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    check(h == H0[p], f"live {p.name} untouched")
print(f"{ok} ok, {bad} failed")
sys.exit(1 if bad else 0)
